"""Shared inference service used by the OpenAI-compatible API."""

from __future__ import annotations

import json
import logging
import threading
from typing import Any, Dict, Iterable, List, Optional

import numpy as np

import utils.intents as intents
from utils.intent_catch import catchAll
from utils.system_prompts import getChatSystemPrompt, getIntentSystemPrompt

logger = logging.getLogger(__name__)


TARGET_SAMPLE_RATE = 16000
OPENAI_STYLE_VOICES = {"alloy", "echo", "fable", "onyx", "nova", "shimmer"}


class FullochService:
    """Lazy-loading orchestrator for ASR, intent routing, chat, and TTS."""

    def __init__(self, config: Dict[str, Any]):
        import tools  # noqa: F401 - imports register configured tools

        self.config = config

        general = config.get("general", {})
        api_config = config.get("api", {})

        self.use_ai = bool(general.get("use_ai", True))
        self.use_tiny_asr = bool(general.get("use_tiny_asr", False))
        self.use_tiny_tts = bool(general.get("use_tiny_tts", False))
        self.voice_clone = str(general.get("voice_clone", "cori"))

        self.chat_model = str(api_config.get("chat_model", "fulloch-qwen3-slm"))
        self.stt_model = str(
            api_config.get(
                "stt_model",
                "moonshine-tiny" if self.use_tiny_asr else "qwen3-asr-1.7b",
            )
        )
        self.tts_model = str(
            api_config.get(
                "tts_model",
                "kokoro-82m" if self.use_tiny_tts else "qwen3-tts-1.7b",
            )
        )

        self._asr_pipe = None
        self._slm_model = None
        self._grammar = None
        self._intent_prompt = None
        self._chat_prompt = None

        self._tts_synthesize = None
        self._remove_emoji = None
        self._set_voice = None
        self._voice_prompt = None
        self._active_voice = self.voice_clone

        self._asr_load_lock = threading.Lock()
        self._slm_load_lock = threading.Lock()
        self._tts_load_lock = threading.Lock()

        self._asr_infer_lock = threading.Lock()
        self._slm_infer_lock = threading.Lock()
        self._tts_infer_lock = threading.Lock()

    def available_models(self) -> List[Dict[str, Any]]:
        """Return model descriptors for /v1/models."""
        return [
            {
                "id": self.chat_model,
                "object": "model",
                "owned_by": "fulloch",
            },
            {
                "id": self.stt_model,
                "object": "model",
                "owned_by": "fulloch",
            },
            {
                "id": self.tts_model,
                "object": "model",
                "owned_by": "fulloch",
            },
        ]

    def transcribe_audio(self, audio: np.ndarray, sample_rate: int) -> str:
        """Transcribe raw waveform audio into text."""
        self._ensure_asr()
        prepared = _prepare_audio(audio, sample_rate, TARGET_SAMPLE_RATE)

        with self._asr_infer_lock:
            result = self._asr_pipe(
                prepared,
                batch_size=1,
                generate_kwargs={"max_new_tokens": 256},
            )

        if isinstance(result, list) and result:
            return str(result[0].get("text", "")).strip()
        if isinstance(result, dict):
            return str(result.get("text", "")).strip()
        return str(result).strip()

    def chat(self, messages: List[Dict[str, Any]], temperature: float = 0.7, max_tokens: int = 512) -> str:
        """Process a conversation and return the assistant response text."""
        normalized_messages = _normalize_messages(messages)
        user_prompt = _latest_user_message(normalized_messages)

        if not user_prompt:
            return "I need a user message to respond."

        intent_answer = self._run_intent_pipeline(user_prompt)
        if intent_answer:
            return self._clean_text(intent_answer)

        if not self.use_ai:
            return "I can handle direct commands, but conversational chat is disabled in configuration."

        self._ensure_slm()

        messages_for_chat = list(normalized_messages)
        if not any(m.get("role") == "system" for m in messages_for_chat):
            messages_for_chat.insert(0, {"role": "system", "content": self._chat_prompt})

        from .slm import generate_slm

        with self._slm_infer_lock:
            answer = generate_slm(
                self._slm_model,
                user_prompt=user_prompt,
                messages=messages_for_chat,
                temperature=temperature,
                max_new_tokens=max_tokens,
            )

        cleaned = self._clean_text(answer)
        if cleaned:
            return cleaned

        return "I couldn't generate a response for that request."

    def synthesize_speech(self, text: str, voice: Optional[str] = None, speed: float = 1.0) -> tuple[np.ndarray, int]:
        """Synthesize text into waveform audio."""
        self._ensure_tts()

        cleaned_text = self._clean_text(text, remove_think=False)
        if not cleaned_text:
            return np.zeros(1, dtype=np.float32), 24000

        requested_voice = (voice or "").strip()
        if not requested_voice:
            requested_voice = self._active_voice or self.voice_clone

        if requested_voice.lower() in OPENAI_STYLE_VOICES:
            requested_voice = "af_bella" if self.use_tiny_tts else (self._active_voice or self.voice_clone)

        with self._tts_infer_lock:
            if not self.use_tiny_tts and requested_voice and requested_voice != self._active_voice:
                try:
                    self._voice_prompt = self._set_voice(requested_voice)
                    self._active_voice = requested_voice
                except Exception as exc:
                    logger.warning(
                        "Could not switch voice clone to '%s': %s. Using '%s'.",
                        requested_voice,
                        exc,
                        self._active_voice,
                    )

            try:
                audio, sample_rate = self._tts_synthesize(
                    cleaned_text,
                    prompt=self._voice_prompt,
                    voice=requested_voice,
                    speed=speed,
                )
            except Exception as exc:
                fallback_voice = self._active_voice or self.voice_clone
                if requested_voice == fallback_voice:
                    raise
                logger.warning(
                    "TTS voice '%s' failed (%s); retrying with '%s'.",
                    requested_voice,
                    exc,
                    fallback_voice,
                )
                audio, sample_rate = self._tts_synthesize(
                    cleaned_text,
                    prompt=self._voice_prompt,
                    voice=fallback_voice,
                    speed=speed,
                )

        return _ensure_float32_mono(audio), int(sample_rate)

    def _run_intent_pipeline(self, user_prompt: str) -> Optional[str]:
        """Run regex and optional AI intent resolution before chat fallback."""
        caught = catchAll(user_prompt)

        if isinstance(caught, dict):
            answer = intents.handle_intent(caught)
            if isinstance(answer, str) and answer.strip():
                return answer

        if not self.use_ai:
            return None

        self._ensure_slm()

        from .slm import generate_slm

        with self._slm_infer_lock:
            ai_intent = generate_slm(
                self._slm_model,
                user_prompt=user_prompt,
                grammar=self._grammar,
                system_prompt=self._intent_prompt,
                max_new_tokens=512,
                temperature=0.2,
            )

        payload = ai_intent.strip().strip('"')
        if not payload:
            return None

        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            logger.debug("Intent payload was not JSON: %s", payload)
            return None

        answer = intents.handle_intent(parsed)
        if not isinstance(answer, str) or not answer.strip():
            return None

        if "User question:" in answer:
            return None

        return answer

    def _clean_text(self, text: Any, remove_think: bool = True) -> str:
        """Normalize text output for user-visible responses."""
        if text is None:
            return ""

        value = str(text).replace('"', "").replace("*", "").strip()
        if not value:
            return ""

        if self._remove_emoji:
            try:
                return self._remove_emoji(value, rem_think=remove_think).strip()
            except TypeError:
                # Some implementations may not support rem_think argument.
                return self._remove_emoji(value).strip()

        return value

    def _ensure_asr(self) -> None:
        """Load ASR backend once."""
        if self._asr_pipe is not None:
            return

        with self._asr_load_lock:
            if self._asr_pipe is not None:
                return

            if self.use_tiny_asr:
                from .asr_tiny import load_asr_model

                logger.info("Using Moonshine Tiny ASR backend")
            else:
                from .asr import load_asr_model

                logger.info("Using Qwen3 ASR backend")

            self._asr_pipe = load_asr_model()

    def _ensure_slm(self) -> None:
        """Load SLM backend and prompts once."""
        if self._slm_model is not None:
            return

        with self._slm_load_lock:
            if self._slm_model is not None:
                return

            from .slm import load_slm

            self._grammar, self._slm_model = load_slm()
            self._intent_prompt = getIntentSystemPrompt()
            self._chat_prompt = getChatSystemPrompt()
            logger.info("Loaded Qwen SLM backend")

    def _ensure_tts(self) -> None:
        """Load TTS backend once."""
        if self._tts_synthesize is not None:
            return

        with self._tts_load_lock:
            if self._tts_synthesize is not None:
                return

            if self.use_tiny_tts:
                from .tts_tiny import remove_emoji, synthesize

                self._tts_synthesize = synthesize
                self._remove_emoji = remove_emoji
                self._set_voice = None
                self._voice_prompt = None
                self._active_voice = "af_bella"
                logger.info("Using Kokoro TTS backend")
            else:
                from .tts import remove_emoji, set_voice, synthesize, warmup_model

                self._remove_emoji = remove_emoji
                self._tts_synthesize = synthesize
                self._set_voice = set_voice
                self._voice_prompt = self._set_voice(self.voice_clone)
                self._active_voice = self.voice_clone
                warmup_model(self._voice_prompt)
                logger.info("Using Qwen3 TTS backend with voice clone '%s'", self.voice_clone)


def _normalize_messages(messages: Optional[Iterable[Dict[str, Any]]]) -> List[Dict[str, str]]:
    """Convert incoming OpenAI messages to role/content string pairs."""
    normalized: List[Dict[str, str]] = []

    if not messages:
        return normalized

    for message in messages:
        role = str(message.get("role", "user")).strip() or "user"
        content = _message_content_to_text(message.get("content"))
        if content:
            normalized.append({"role": role, "content": content})

    return normalized


def _message_content_to_text(content: Any) -> str:
    """Normalize OpenAI content (string or part-list) to plain text."""
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        parts: List[str] = []
        for part in content:
            if isinstance(part, str):
                value = part.strip()
                if value:
                    parts.append(value)
                continue

            if not isinstance(part, dict):
                continue

            kind = str(part.get("type", "")).strip().lower()
            if kind in {"text", "input_text", "output_text"}:
                value = str(part.get("text", "")).strip()
                if value:
                    parts.append(value)

        return "\n".join(parts).strip()

    if content is None:
        return ""

    return str(content).strip()


def _latest_user_message(messages: List[Dict[str, str]]) -> str:
    """Get the latest user message content from a normalized message list."""
    for message in reversed(messages):
        if message.get("role") == "user" and message.get("content"):
            return message["content"]
    return ""


def _ensure_float32_mono(audio: np.ndarray) -> np.ndarray:
    """Ensure mono float32 waveform in [-1, 1]."""
    arr = np.asarray(audio)

    if arr.ndim > 1:
        arr = np.mean(arr, axis=1)

    if arr.dtype != np.float32:
        arr = arr.astype(np.float32)

    max_abs = float(np.max(np.abs(arr))) if arr.size else 0.0
    if max_abs > 1.0:
        arr = arr / max_abs

    return arr


def _prepare_audio(audio: np.ndarray, sample_rate: int, target_sample_rate: int) -> np.ndarray:
    """Convert waveform to mono float32 at the target sample rate."""
    mono = _ensure_float32_mono(audio)
    if sample_rate == target_sample_rate or mono.size == 0:
        return mono

    duration = mono.size / float(sample_rate)
    target_size = max(1, int(round(duration * target_sample_rate)))

    x_old = np.linspace(0.0, duration, num=mono.size, endpoint=False)
    x_new = np.linspace(0.0, duration, num=target_size, endpoint=False)

    resampled = np.interp(x_new, x_old, mono)
    return resampled.astype(np.float32)
