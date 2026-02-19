#!/usr/bin/env python3
"""Fulloch OpenAI-compatible API server entrypoint."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv

from utils.env_config import env_bool, env_int, env_str

# Reduce noisy transformers generation warnings
logging.getLogger("transformers.generation.utils").setLevel(logging.ERROR)

load_dotenv()


def load_config_from_env() -> Dict[str, Any]:
    """Build runtime configuration from environment variables only."""
    return {
        "general": {
            "use_ai": env_bool("FULLOCH_USE_AI", True),
            "use_tiny_asr": env_bool("FULLOCH_USE_TINY_ASR", False),
            "use_tiny_tts": env_bool("FULLOCH_USE_TINY_TTS", False),
            "voice_clone": env_str("FULLOCH_VOICE_CLONE", "cori"),
        },
        "api": {
            "host": env_str("FULLOCH_HOST", "0.0.0.0"),
            "port": env_int("FULLOCH_PORT", 8000),
            "log_level": env_str("FULLOCH_LOG_LEVEL", "info"),
            "api_key": env_str("FULLOCH_API_KEY", ""),
            "chat_model": env_str("FULLOCH_CHAT_MODEL", "fulloch-qwen3-slm"),
            "stt_model": env_str("FULLOCH_STT_MODEL", "qwen3-asr-1.7b"),
            "tts_model": env_str("FULLOCH_TTS_MODEL", "qwen3-tts-1.7b"),
        },
    }


config = load_config_from_env()

# Ensure model cache points into mounted data dir
models_dir = Path("./data/models").resolve()
os.environ.setdefault("HF_HOME", str(models_dir))
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("DO_NOT_TRACK", "1")
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
os.environ.setdefault("VLLM_NO_USAGE_STATS", "1")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

from api import create_app


def main() -> None:
    """Start the HTTP API server."""
    api_config = config["api"]

    host = env_str("FULLOCH_HOST", str(api_config.get("host", "0.0.0.0")))
    port = env_int("FULLOCH_PORT", int(api_config.get("port", 8000)))
    log_level = env_str("FULLOCH_LOG_LEVEL", str(api_config.get("log_level", "info"))).lower()

    app = create_app(config)

    import uvicorn

    uvicorn.run(app, host=host, port=port, log_level=log_level)


if __name__ == "__main__":
    main()
