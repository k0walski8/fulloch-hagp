"""Philips Hue lighting control tool."""

from __future__ import annotations

import os

from phue import Bridge

from .tool_registry import tool, tool_registry

HUE_HUB_IP = os.getenv("PHILIPS_HUE_HUB_IP", "").strip()
HUE_CONFIG_PATH = os.getenv("PHILIPS_HUE_CONFIG_PATH", "./data/.python_hue").strip()

_bridge = None


def _get_bridge():
    """Create Hue bridge lazily so imports do not fail when env is missing."""
    global _bridge
    if _bridge is not None:
        return _bridge

    if not HUE_HUB_IP:
        return None

    try:
        _bridge = Bridge(HUE_HUB_IP, config_file_path=HUE_CONFIG_PATH)
        return _bridge
    except Exception:
        return None


def _no_bridge_message() -> str:
    return "Philips Hue is not configured. Set PHILIPS_HUE_HUB_IP."


@tool(
    name="turn_on_lights",
    description="Turn on lights in a specific location",
    aliases=["lights_on", "switch_on_lights", "turn_on"],
)
def turn_on_lights(location: str = "Downlights Office") -> str:
    """Turn on lights in the specified location."""
    bridge = _get_bridge()
    if bridge is None:
        return _no_bridge_message()

    location = location.title()
    if location in bridge.get_light_objects("name").keys():
        bridge.set_light(location, "on", True)
        return f"{location} lights on"

    groups = bridge.get_group()
    group_names = [groups[i]["name"] for i in groups]
    if location in group_names:
        bridge.set_group(location, "on", True)
        return f"{location} on"

    return f"No lights or rooms with name {location}"


@tool(
    name="turn_off_lights",
    description="Turn off lights in a specific location",
    aliases=["lights_off", "switch_off_lights", "turn_off"],
)
def turn_off_lights(location: str = "Downlights Office") -> str:
    """Turn off lights in the specified location."""
    bridge = _get_bridge()
    if bridge is None:
        return _no_bridge_message()

    try:
        location = location.title()
        if location in bridge.get_light_objects("name").keys():
            bridge.set_light(location, "on", False)
            return f"{location} lights off"

        groups = bridge.get_group()
        group_names = [groups[i]["name"] for i in groups]
        if location in group_names:
            bridge.set_group(location, "on", False)
            return f"{location} off"

        return f"No lights or rooms with name {location}"
    except Exception:
        return f"Unable to connect to lights for {location}"


@tool(
    name="set_brightness",
    description="Set brightness level for lights in a specific location",
    aliases=["brightness", "dim_lights", "brighten_lights"],
)
def set_brightness(percent: int = 100, location: str = "Downlights Office") -> str:
    """Set brightness level for lights in the specified location."""
    bridge = _get_bridge()
    if bridge is None:
        return _no_bridge_message()

    try:
        location = location.title()
        level = int((int(percent) / 100) * 254)

        if location in bridge.get_light_objects("name").keys():
            bridge.set_light(location, "on", True)
            bridge.set_light(location, "bri", level)
            return f"{location} lights set to {percent} percent."

        groups = bridge.get_group()
        group_names = [groups[i]["name"] for i in groups]
        if location in group_names:
            bridge.set_group(location, "on", True)
            bridge.set_group(location, "bri", level)
            return f"{location} set to {percent} percent."

        return f"No lights or rooms with name {location}"
    except Exception:
        return f"Unable to connect to lights for {location}"


if __name__ == "__main__":
    print("Philips Hue Lighting Controller")

    print("\nAvailable tools:")
    for schema in tool_registry.get_all_schemas():
        print(f"  {schema.name}: {schema.description}")
        for param in schema.parameters:
            print(f"    - {param.name} ({param.type.value}): {param.description}")

    print("\nTesting function calling:")
    result = tool_registry.execute_tool("turn_on_lights", kwargs={"location": "kitchen"})
    print(f"Result: {result}")
