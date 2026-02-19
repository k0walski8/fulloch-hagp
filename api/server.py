"""OpenAI-compatible API server for Fulloch."""

from __future__ import annotations

import io
import json
import logging
import os
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import soundfile as sf
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse, Response, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class SpeechRequest(BaseModel):
    """Subset of OpenAI speech request parameters used by Home Assistant."""

    model: str = Field(default="gpt-4o-mini-tts")
    input: str
    voice: str = Field(default="alloy")
    response_format: str = Field(default="mp3")
    speed: float = Field(default=1.0)


def create_app(config: Dict[str, Any]) -> FastAPI:
    """Create and configure the API app."""
    from core.api_service import FullochService

    app = FastAPI(title="Fulloch OpenAI-Compatible API", version="1.0.0")
    service = FullochService(config)

    api_config = config.get("api", {})
    configured_key = os.getenv("FULLOCH_API_KEY", str(api_config.get("api_key", ""))).strip()

    auth_scheme = HTTPBearer(auto_error=False)

    async def require_api_key(
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(auth_scheme),
    ) -> None:
        if not configured_key:
            return

        if not credentials or credentials.scheme.lower() != "bearer":
            raise HTTPException(status_code=401, detail="Missing or invalid bearer token")

        if credentials.credentials != configured_key:
            raise HTTPException(status_code=401, detail="Invalid API key")

    @app.get("/health")
    async def health() -> Dict[str, Any]:
        return {
            "status": "ok",
            "service": "fulloch",
            "models": {
                "chat": service.chat_model,
                "stt": service.stt_model,
                "tts": service.tts_model,
            },
        }

    @app.get("/v1/models", dependencies=[Depends(require_api_key)])
    async def list_models() -> Dict[str, Any]:
        return {
            "object": "list",
            "data": service.available_models(),
        }

    @app.post("/v1/chat/completions", dependencies=[Depends(require_api_key)])
    async def chat_completions(payload: Dict[str, Any]) -> Response:
        model = str(payload.get("model") or service.chat_model)
        messages = payload.get("messages") or []
        stream = bool(payload.get("stream", False))

        temperature = float(payload.get("temperature", 0.7))
        max_tokens = int(payload.get("max_tokens", 512))

        answer = service.chat(messages=messages, temperature=temperature, max_tokens=max_tokens)

        created = int(time.time())
        completion_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"

        prompt_tokens = _estimate_tokens(messages)
        completion_tokens = _estimate_tokens(answer)

        if stream:
            async def event_stream():
                first_chunk = {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": model,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"role": "assistant", "content": answer},
                            "finish_reason": None,
                        }
                    ],
                }
                yield f"data: {json.dumps(first_chunk)}\n\n"

                final_chunk = {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": model,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {},
                            "finish_reason": "stop",
                        }
                    ],
                }
                yield f"data: {json.dumps(final_chunk)}\n\n"
                yield "data: [DONE]\n\n"

            return StreamingResponse(event_stream(), media_type="text/event-stream")

        response_payload = {
            "id": completion_id,
            "object": "chat.completion",
            "created": created,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": answer},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }

        return JSONResponse(response_payload)

    @app.post("/v1/responses", dependencies=[Depends(require_api_key)])
    async def responses_api(payload: Dict[str, Any]) -> Dict[str, Any]:
        model = str(payload.get("model") or service.chat_model)
        input_payload = payload.get("input", "")

        messages: List[Dict[str, Any]] = payload.get("messages") or []
        if not messages:
            if isinstance(input_payload, str):
                messages = [{"role": "user", "content": input_payload}]
            elif isinstance(input_payload, list):
                normalized: List[Dict[str, Any]] = []
                for item in input_payload:
                    if isinstance(item, dict) and "role" in item and "content" in item:
                        normalized.append(item)
                    elif isinstance(item, dict) and item.get("type") == "input_text":
                        normalized.append({"role": "user", "content": item.get("text", "")})
                messages = normalized

        temperature = float(payload.get("temperature", 0.7))
        max_tokens = int(payload.get("max_output_tokens", 512))

        answer = service.chat(messages=messages, temperature=temperature, max_tokens=max_tokens)

        response_id = f"resp_{uuid.uuid4().hex[:24]}"
        created = int(time.time())
        return {
            "id": response_id,
            "object": "response",
            "created_at": created,
            "model": model,
            "output": [
                {
                    "id": f"msg_{uuid.uuid4().hex[:12]}",
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "output_text",
                            "text": answer,
                            "annotations": [],
                        }
                    ],
                }
            ],
            "output_text": answer,
        }

    @app.post("/v1/audio/transcriptions", dependencies=[Depends(require_api_key)])
    async def audio_transcriptions(
        file: UploadFile = File(...),
        model: str = Form("whisper-1"),
        language: Optional[str] = Form(default=None),
        prompt: Optional[str] = Form(default=None),
        response_format: str = Form(default="json"),
        temperature: float = Form(default=0.0),
    ) -> Response:
        _ = model, language, prompt, temperature

        audio_bytes = await file.read()
        if not audio_bytes:
            raise HTTPException(status_code=400, detail="Uploaded audio file is empty")

        try:
            audio, sample_rate = _decode_audio_bytes(audio_bytes, filename=file.filename or "audio.bin")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        text = service.transcribe_audio(audio, sample_rate)

        normalized_format = (response_format or "json").strip().lower()
        if normalized_format == "text":
            return PlainTextResponse(text)

        if normalized_format == "verbose_json":
            return JSONResponse(
                {
                    "task": "transcribe",
                    "language": language or "en",
                    "duration": float(len(audio) / sample_rate) if sample_rate else 0.0,
                    "text": text,
                }
            )

        return JSONResponse({"text": text})

    @app.post("/v1/audio/translations", dependencies=[Depends(require_api_key)])
    async def audio_translations(
        file: UploadFile = File(...),
        model: str = Form("whisper-1"),
        response_format: str = Form(default="json"),
    ) -> Response:
        return await audio_transcriptions(
            file=file,
            model=model,
            language="en",
            prompt=None,
            response_format=response_format,
            temperature=0.0,
        )

    @app.post("/v1/audio/speech", dependencies=[Depends(require_api_key)])
    async def audio_speech(payload: SpeechRequest) -> Response:
        _ = payload.model
        speed = max(0.25, min(4.0, float(payload.speed)))

        audio, sample_rate = service.synthesize_speech(
            text=payload.input,
            voice=payload.voice,
            speed=speed,
        )

        try:
            encoded, media_type = _encode_audio(
                audio=audio,
                sample_rate=sample_rate,
                response_format=payload.response_format,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        return Response(content=encoded, media_type=media_type)

    return app


def _estimate_tokens(value: Any) -> int:
    """Very rough token estimate for OpenAI-compatible usage fields."""
    if isinstance(value, list):
        text = json.dumps(value)
    else:
        text = str(value)
    return max(1, len(text) // 4)


def _decode_audio_bytes(data: bytes, filename: str) -> tuple[np.ndarray, int]:
    """Decode uploaded audio bytes into waveform and sample rate."""
    try:
        audio, sample_rate = sf.read(io.BytesIO(data), dtype="float32", always_2d=False)
        return np.asarray(audio), int(sample_rate)
    except Exception:
        pass

    suffix = Path(filename).suffix or ".bin"
    temp_path = ""

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_file.write(data)
            temp_path = temp_file.name

        cmd = [
            "ffmpeg",
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            temp_path,
            "-f",
            "wav",
            "-ac",
            "1",
            "-ar",
            "16000",
            "pipe:1",
        ]

        proc = subprocess.run(cmd, capture_output=True, check=False)
        if proc.returncode != 0:
            raise ValueError(proc.stderr.decode("utf-8", errors="ignore") or "ffmpeg decode failed")

        audio, sample_rate = sf.read(io.BytesIO(proc.stdout), dtype="float32", always_2d=False)
        return np.asarray(audio), int(sample_rate)
    except Exception as exc:
        raise ValueError(f"Unsupported audio format: {exc}") from exc
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)


def _encode_audio(audio: np.ndarray, sample_rate: int, response_format: str) -> tuple[bytes, str]:
    """Encode waveform into OpenAI-compatible TTS response formats."""
    normalized = np.asarray(audio, dtype=np.float32)
    normalized = np.clip(normalized, -1.0, 1.0)

    fmt = (response_format or "mp3").strip().lower()

    if fmt == "pcm":
        pcm = (normalized * 32767.0).astype("<i2")
        return pcm.tobytes(), "application/octet-stream"

    wav_buffer = io.BytesIO()
    sf.write(wav_buffer, normalized, sample_rate, format="WAV", subtype="PCM_16")
    wav_bytes = wav_buffer.getvalue()

    if fmt in {"wav", "wave"}:
        return wav_bytes, "audio/wav"

    if fmt == "flac":
        return _transcode_with_ffmpeg(wav_bytes, output_format="flac", codec=None), "audio/flac"

    if fmt == "aac":
        return _transcode_with_ffmpeg(wav_bytes, output_format="adts", codec="aac"), "audio/aac"

    if fmt == "opus":
        return _transcode_with_ffmpeg(wav_bytes, output_format="opus", codec="libopus"), "audio/opus"

    if fmt == "mp3":
        return _transcode_with_ffmpeg(wav_bytes, output_format="mp3", codec="libmp3lame"), "audio/mpeg"

    raise ValueError(f"Unsupported response_format '{response_format}'")


def _transcode_with_ffmpeg(wav_bytes: bytes, output_format: str, codec: Optional[str]) -> bytes:
    """Transcode WAV bytes to a target format using ffmpeg."""
    cmd = [
        "ffmpeg",
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "wav",
        "-i",
        "pipe:0",
    ]

    if codec:
        cmd.extend(["-c:a", codec])

    cmd.extend(["-f", output_format, "pipe:1"])

    proc = subprocess.run(cmd, input=wav_bytes, capture_output=True, check=False)
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="ignore")
        raise ValueError(f"Failed to encode audio as {output_format}: {stderr or 'unknown ffmpeg error'}")

    return proc.stdout
