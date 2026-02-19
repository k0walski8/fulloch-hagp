"""ThinQ Connect tool."""

from __future__ import annotations

import asyncio
import logging
import os

from aiohttp import ClientSession
from dotenv import load_dotenv
from thinqconnect.thinq_api import ThinQApi

from .tool_registry import tool, tool_registry

load_dotenv()
logger = logging.getLogger(__name__)

THINQ_ACCESS_TOKEN = os.getenv("THINQ_ACCESS_TOKEN", "").strip()
THINQ_COUNTRY_CODE = os.getenv("THINQ_COUNTRY_CODE", "AU").strip()
THINQ_CLIENT_ID = os.getenv("THINQ_CLIENT_ID", "").strip()


async def _get_dishwasher_info():
    if not (THINQ_ACCESS_TOKEN and THINQ_CLIENT_ID):
        return None, None, None

    async with ClientSession() as session:
        try:
            thinq_api = ThinQApi(
                session=session,
                access_token=THINQ_ACCESS_TOKEN,
                country_code=THINQ_COUNTRY_CODE,
                client_id=THINQ_CLIENT_ID,
            )
        except Exception as exc:
            logger.error(f"Failed to initialize ThinQ API: {exc}")
            return None, None, None

        try:
            device_list = await thinq_api.async_get_device_list()
            if device_list is None:
                return None, None, None

            dishwashers = [
                device for device in device_list if device.get("deviceInfo", {}).get("deviceType") == "DEVICE_DISH_WASHER"
            ]

            if not dishwashers:
                return None, None, None

            for dishwasher in dishwashers:
                device_id = dishwasher.get("deviceId")
                status_response = await thinq_api.async_get_device_status(device_id)

                if status_response:
                    timer_info = status_response.get("timer") or {}
                    state_info = status_response.get("runState") or {}

                    remain_hours = timer_info.get("remainHour")
                    remain_minutes = timer_info.get("remainMinute")
                    run_state = state_info.get("currentState")
                    return run_state, remain_hours, remain_minutes
        except Exception as exc:
            logger.error(f"Error retrieving dishwasher information: {exc}", exc_info=True)
            return None, None, None

    return None, None, None


async def _get_dishwasher_text():
    run_state, remain_hours, remain_minutes = await _get_dishwasher_info()

    if run_state is not None:
        return f"Dishwasher has {remain_hours} hours, {remain_minutes} minutes left. Currently {run_state}."

    if not (THINQ_ACCESS_TOKEN and THINQ_CLIENT_ID):
        return "ThinQ is not configured. Set THINQ_ACCESS_TOKEN and THINQ_CLIENT_ID."

    return "Dishwasher is not running"


@tool(
    name="dishwasher_status",
    description="Get dishwasher status",
    aliases=["time_left_dishwasher", "dishwasher", "is_dishwasher_finished"],
)
def dishwasher_status():
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_get_dishwasher_text())
    else:
        return loop.create_task(_get_dishwasher_text())


if __name__ == "__main__":
    asyncio.run(_get_dishwasher_text())
