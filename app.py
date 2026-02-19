#!/usr/bin/env python3
"""Fulloch OpenAI-compatible API server entrypoint."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict

import yaml
from dotenv import load_dotenv

# Reduce noisy transformers generation warnings
logging.getLogger("transformers.generation.utils").setLevel(logging.ERROR)

load_dotenv()


def load_config() -> Dict[str, Any]:
    """Load runtime configuration from config.yml or fallback example."""
    config_path = Path(os.getenv("FULLOCH_CONFIG", "./data/config.yml"))
    example_path = Path("./data/config.example.yml")

    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as config_file:
            return yaml.safe_load(config_file) or {}

    if example_path.exists():
        with example_path.open("r", encoding="utf-8") as example_file:
            return yaml.safe_load(example_file) or {}

    return {}


config = load_config()

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
    api_config = config.get("api", {})

    host = os.getenv("FULLOCH_HOST", str(api_config.get("host", "0.0.0.0")))
    port = int(os.getenv("FULLOCH_PORT", str(api_config.get("port", 8000))))
    log_level = str(api_config.get("log_level", "info")).lower()

    app = create_app(config)

    import uvicorn

    uvicorn.run(app, host=host, port=port, log_level=log_level)


if __name__ == "__main__":
    main()
