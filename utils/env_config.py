"""Environment configuration helpers for Fulloch."""

from __future__ import annotations

import json
import os
from typing import Any, Dict


_TRUE_VALUES = {"1", "true", "yes", "on", "y"}


def env_str(name: str, default: str = "") -> str:
    """Get environment variable as stripped string."""
    return os.getenv(name, default).strip()


def env_bool(name: str, default: bool = False) -> bool:
    """Get environment variable as boolean."""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in _TRUE_VALUES


def env_int(name: str, default: int) -> int:
    """Get environment variable as integer with fallback."""
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw.strip())
    except (TypeError, ValueError):
        return default


def env_float(name: str, default: float) -> float:
    """Get environment variable as float with fallback."""
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw.strip())
    except (TypeError, ValueError):
        return default


def env_json_dict(name: str, default: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Parse environment variable as JSON object."""
    fallback = default or {}
    raw = os.getenv(name)
    if not raw:
        return fallback

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return fallback

    if isinstance(data, dict):
        return data

    return fallback
