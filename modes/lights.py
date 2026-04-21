"""Govee LAN light control.

Uses the `govee-lan-api` package to talk to a Govee device on the local
network. The target device MAC is read from config.json.

Exposed actions (via `handle`): turn_on, turn_off, color, movie_mode,
party_mode, sleep_mode.
"""

import asyncio
import json
import os

# We import the Govee library lazily so the rest of the controller still
# runs if the package isn't installed yet — useful during first-time setup.
try:
    from govee_lan_api import Govee  # type: ignore
    _GOVEE_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    Govee = None  # type: ignore
    _GOVEE_AVAILABLE = False


CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json")

# Cached singletons so we don't rediscover the device on every key press.
_govee_client = None
_device = None
_lock = asyncio.Lock()


def _load_config() -> dict:
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)


async def _get_device():
    """Discover the configured Govee device on the LAN (cached)."""
    global _govee_client, _device

    if not _GOVEE_AVAILABLE:
        raise RuntimeError(
            "govee-lan-api not installed. Run: pip install govee-lan-api"
        )

    if _device is not None:
        return _device

    async with _lock:
        if _device is not None:
            return _device

        cfg = _load_config()["govee"]
        target_mac = cfg["device_mac"].lower()

        _govee_client = Govee()
        # Discover devices on the LAN; block briefly to collect responses.
        await _govee_client.discover(timeout=3)

        for dev in _govee_client.devices:
            if getattr(dev, "mac", "").lower() == target_mac:
                _device = dev
                return _device

        raise RuntimeError(
            f"No Govee device with MAC {target_mac} found on the LAN. "
            "Check the MAC in config.json and that the device is online."
        )


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert '#rrggbb' or 'rrggbb' to an (R, G, B) tuple of 0-255 ints."""
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


async def turn_on() -> None:
    dev = await _get_device()
    await dev.on()


async def turn_off() -> None:
    dev = await _get_device()
    await dev.off()


async def set_color(hex_color: str, brightness: int = 100) -> None:
    """Set the light to `hex_color` at `brightness` (1-100)."""
    dev = await _get_device()
    r, g, b = _hex_to_rgb(hex_color)
    brightness = max(1, min(100, int(brightness)))
    await dev.on()
    await dev.set_color((r, g, b))
    await dev.set_brightness(brightness)


# ---- Preset scenes ---------------------------------------------------------

async def movie_mode() -> None:
    """Warm orange glow, dim — good for film nights."""
    await set_color("#ff6a00", brightness=20)


async def party_mode() -> None:
    """Bright white — for when things pop off."""
    await set_color("#ffffff", brightness=100)


async def sleep_mode() -> None:
    """Deep red, very dim — low stimulation for winding down."""
    await set_color("#8b0000", brightness=5)


# ---- Dispatcher ------------------------------------------------------------

async def handle(cfg: dict) -> None:
    """Route a mapping entry to the right light action."""
    action = cfg.get("action")

    if action == "turn_on":
        await turn_on()
    elif action == "turn_off":
        await turn_off()
    elif action == "color":
        await set_color(cfg.get("color", "#ffffff"), cfg.get("brightness", 100))
    elif action == "movie_mode":
        await movie_mode()
    elif action == "party_mode":
        await party_mode()
    elif action == "sleep_mode":
        await sleep_mode()
    else:
        print(f"[lights] unknown action: {action}")
