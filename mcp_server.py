"""Casio Controller MCP server.

Exposes the same lights / TV / game / audio handlers used by the MIDI
listener as MCP tools. Runs locally over stdio so Claude Desktop (or
Claude Code) can call them directly — no cloud sandbox in between, which
means it can still reach devices on your LAN.

Register with Claude Desktop by adding to claude_desktop_config.json:

    {
      "mcpServers": {
        "casio-controller": {
          "command": "python",
          "args": ["/absolute/path/to/mcp_server.py"]
        }
      }
    }

Or with Claude Code:

    claude mcp add casio-controller python /abs/path/to/mcp_server.py
"""

from typing import Literal

from mcp.server.fastmcp import FastMCP

from modes import lights, tv, game, audio
from modes.tv import APP_IDS


mcp = FastMCP("casio-controller")


# ---- Lights ----------------------------------------------------------------

@mcp.tool()
async def lights_turn_on() -> str:
    """Turn the Govee light on (keeps last color/brightness)."""
    await lights.turn_on()
    return "lights on"


@mcp.tool()
async def lights_turn_off() -> str:
    """Turn the Govee light off."""
    await lights.turn_off()
    return "lights off"


@mcp.tool()
async def lights_set_color(hex_color: str, brightness: int = 100) -> str:
    """Set the light to a specific color and brightness.

    hex_color:  e.g. "#ff6a00"
    brightness: 1-100
    """
    await lights.set_color(hex_color, brightness)
    return f"color {hex_color} @ {brightness}"


@mcp.tool()
async def lights_preset(
    preset: Literal["movie_mode", "party_mode", "sleep_mode"],
) -> str:
    """Activate a preset lighting scene."""
    fn = getattr(lights, preset)
    await fn()
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


if __name__ == "__main__":
    mcp.run()
