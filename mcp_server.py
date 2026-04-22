"""Casio Controller MCP server.

Exposes the same lights / TV / game / audio handlers used by the MIDI
listener as MCP tools. Runs locally over stdio so Claude Desktop (or
Claude Code) can call them directly — no cloud sandbox in between, which
means it can still reach devices on your LAN.

Works on macOS, Linux, and Windows. Register it in
claude_desktop_config.json:

    macOS:   ~/Library/Application Support/Claude/claude_desktop_config.json
    Windows: %APPDATA%\\Claude\\claude_desktop_config.json

Example config:

    {
      "mcpServers": {
        "casio-controller": {
          "command": "python",
          "args": ["C:\\\\path\\\\to\\\\casiocontroller\\\\mcp_server.py"]
        }
      }
    }

Or with Claude Code:

    claude mcp add casio-controller python /abs/path/to/mcp_server.py
"""

from typing import Literal

from mcp.server.fastmcp import FastMCP

import profiles as profile_store
from modes import lights, tv, game, audio
from modes.tv import APP_IDS


mcp = FastMCP("casio-controller")


# ---- Lights ----------------------------------------------------------------
# The lights handlers accept a `cfg` dict (same shape the MIDI dispatcher
# passes them). `targets` — a list of device names from config.json —
# scopes an action to specific lamps; omit it to fan out to every lamp.

def _light_cfg(action: str, targets: list[str] | None = None, **extra) -> dict:
    cfg: dict = {"action": action, **extra}
    if targets:
        cfg["targets"] = targets
    return cfg


@mcp.tool()
async def lights_turn_on(targets: list[str] | None = None) -> str:
    """Turn configured Govee lights on. Pass `targets` to scope to specific lamps."""
    await lights.turn_on(_light_cfg("turn_on", targets))
    return "lights on" + (f" ({', '.join(targets)})" if targets else "")


@mcp.tool()
async def lights_turn_off(targets: list[str] | None = None) -> str:
    """Turn configured Govee lights off. Pass `targets` to scope to specific lamps."""
    await lights.turn_off(_light_cfg("turn_off", targets))
    return "lights off" + (f" ({', '.join(targets)})" if targets else "")


@mcp.tool()
async def lights_set_color(
    hex_color: str,
    brightness: int = 100,
    targets: list[str] | None = None,
) -> str:
    """Set a specific color and brightness (1-100). Optional `targets` list."""
    cfg = _light_cfg("color", targets, color=hex_color, brightness=brightness)
    await lights.set_color(cfg, hex_color, brightness)
    return f"color {hex_color} @ {brightness}" + (
        f" ({', '.join(targets)})" if targets else "")


@mcp.tool()
async def lights_preset(
    preset: Literal["movie_mode", "party_mode", "sleep_mode"],
    targets: list[str] | None = None,
) -> str:
    """Activate a preset scene."""
    fn = getattr(lights, preset)
    await fn(_light_cfg(preset, targets))
    return f"preset {preset} activated"


# ---- TV --------------------------------------------------------------------

@mcp.tool()
async def tv_power() -> str:
    """Toggle TV power (same button for on and off on Samsung)."""
    await tv.power_on()
    return "tv power toggled"


@mcp.tool()
async def tv_launch_app(
    app: Literal["netflix", "youtube", "disney", "prime"],
) -> str:
    """Launch one of the built-in streaming apps."""
    await tv.launch_app(APP_IDS[app])
    return f"launched {app}"


@mcp.tool()
async def tv_send_key(key: str) -> str:
    """Send any Samsung remote key code, e.g. KEY_VOLUP, KEY_UP, KEY_ENTER."""
    await tv.send_key(key)
    return f"sent {key}"


# ---- Game / keyboard emulation --------------------------------------------

@mcp.tool()
async def game_press_key(key: str, hold_ms: int = 40) -> str:
    """Simulate a keyboard press on THIS machine (the one running the server).

    key:     KEY_SPACE, KEY_W, KEY_UP, etc.
    hold_ms: how long the key is held down before release.
    """
    await game.press_key(key, hold_ms=hold_ms)
    return f"pressed {key}"


# ---- Audio (stubs until a real backend is wired up) -----------------------

@mcp.tool()
async def audio_play_pause() -> str:
    await audio.play_pause()
    return "play/pause"


@mcp.tool()
async def audio_next_track() -> str:
    await audio.next_track()
    return "next track"


@mcp.tool()
async def audio_prev_track() -> str:
    await audio.prev_track()
    return "previous track"


@mcp.tool()
async def audio_set_volume(level: int) -> str:
    """Set volume 0-100."""
    await audio.set_volume(level)
    return f"volume {level}"


# ---- Profiles --------------------------------------------------------------
# Switching profiles from an MCP client changes which mappings the MIDI
# listener uses on the next key press — useful for "put the keyboard in
# TV mode" style commands.

@mcp.tool()
async def profile_list() -> list[str]:
    """Return every profile defined in profiles.json."""
    data = profile_store.load()
    return list(data.get("profiles", {}).keys())


@mcp.tool()
async def profile_active() -> str:
    """Return the currently active profile name."""
    data = profile_store.load()
    return data.get("active", "")


@mcp.tool()
async def profile_switch(name: str) -> str:
    """Set the active profile. main.py hot-reloads on the next key press."""
    data = profile_store.load()
    profiles = data.get("profiles", {})
    if name not in profiles:
        raise ValueError(
            f"unknown profile '{name}'. Available: {', '.join(profiles)}"
        )
    data["active"] = name
    profile_store.save(data)
    return f"active profile -> {name}"


if __name__ == "__main__":
    mcp.run()
