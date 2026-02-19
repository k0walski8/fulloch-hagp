"""Tools package for the voice assistant.

Tools are conditionally loaded via environment variables.
"""

from __future__ import annotations

import importlib
import logging

from utils.env_config import env_bool

logger = logging.getLogger(__name__)

# Tool module -> env flag
_TOOL_ENV_MAP = {
    "spotify": ("ENABLE_SPOTIFY", False),
    "lighting": ("ENABLE_PHILIPS_HUE", False),
    "google_calendar": ("ENABLE_GOOGLE_CALENDAR", False),
    "airtouch": ("ENABLE_AIRTOUCH", False),
    "thinq": ("ENABLE_THINQ", False),
    "webos": ("ENABLE_WEBOS", False),
    "search_web": ("ENABLE_SEARCH_WEB", True),
    "pioneer_avr": ("ENABLE_PIONEER_AVR", False),
    "home_assistant": ("ENABLE_HOME_ASSISTANT", False),
}

# Always load weather/time tools unless explicitly disabled
_ALWAYS_LOAD = ["weather_time"] if env_bool("ENABLE_WEATHER_TIME", True) else []

for module_name in _ALWAYS_LOAD:
    try:
        importlib.import_module(f".{module_name}", package=__name__)
        logger.info("Loaded tool: %s", module_name)
    except Exception as exc:
        logger.error("Failed to load tool %s: %s", module_name, exc)

for module_name, (env_var, default_enabled) in _TOOL_ENV_MAP.items():
    if env_bool(env_var, default_enabled):
        try:
            importlib.import_module(f".{module_name}", package=__name__)
            logger.info("Loaded tool: %s (%s=true)", module_name, env_var)
        except Exception as exc:
            logger.error("Failed to load tool %s: %s", module_name, exc)
    else:
        logger.info("Skipping tool %s (%s=false)", module_name, env_var)

from .tool_registry import tool_registry, tool

__all__ = ["tool_registry", "tool"]
