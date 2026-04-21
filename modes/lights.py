"""Govee LAN light control.

Discovery uses `govee-lan-api` (GoveeClient.scan_devices) once at
startup. Actual commands bypass that library and go straight out over
UDP, because the library binds port 4002 inside every send — which
means two concurrent sends collide on bind() and only one lamp fires.
A plain `sendto` has no such collision, so both lamps switch in the
same instant.

Configured devices are read from config.json — each has a user-defined
`name`, its LAN `mac`, and `model`. A mapping entry may include
`targets` (list of names) to scope an action to specific lights;
otherwise the action fans out to every configured device.

Exposed actions (via `handle`): turn_on, turn_off, color, movie_mode,
party_mode, sleep_mode.
"""

import asyncio
import json
import os
import socket

try:
    from govee_lan_api import GoveeClient  # type: ignore
    from govee_lan_api import api_requests  # type: ignore
    _GOVEE_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    GoveeClient = None  # type: ignore
    api_requests = None  # type: ignore
    _GOVEE_AVAILABLE = False


CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json")

# Govee devices receive commands on UDP port 4003.
GOVEE_CMD_PORT = 4003

# name -> {"id": device_id, "ip": ipv4}. Populated once per process.
_devices_by_name: dict[str, dict] = {}
_lock = asyncio.Lock()


def _load_config() -> dict:
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)


def _configured_devices() -> list[dict]:
    cfg = _load_config()["govee"]
    if "devices" not in cfg:
        return [{
            "name": "default",
            "mac": cfg["device_mac"],
            "model": cfg.get("device_model", ""),
        }]
    return cfg["devices"]


async def _ensure_discovered() -> None:
    """Scan the LAN once and cache {name: {id, ip}} for configured lights."""
    global _devices_by_name

    if not _GOVEE_AVAILABLE:
        raise RuntimeError(
            "govee-lan-api not installed. Run: pip install govee-lan-api"
        )

    if _devices_by_name:
        return

    async with _lock:
        if _devices_by_name:
            return

        configured = _configured_devices()
        # Govee reports 8-byte device IDs; config usually has 6-byte
        # MACs, so match by suffix.
        wanted = {d["name"]: d["mac"].upper() for d in configured}

        client = GoveeClient()
        await client.scan_devices()
        seen = {did.upper(): info for did, info in client.devices.items()}

        found: dict[str, dict] = {}
        for name, mac in wanted.items():
            for up, info in seen.items():
                if up == mac or up.endswith(mac):
                    found[name] = {"id": info["device"], "ip": info["ip"]}
                    break

        missing = [n for n in wanted if n not in found]
        if missing:
            print(
                f"[lights] not found on LAN (skipping): {', '.join(missing)}. "
                f"Seen: {sorted(seen)}"
            )

        _devices_by_name = found


async def _resolve_targets(cfg: dict) -> list[dict]:
    """Return the list of device records (id + ip) an action should affect."""
    await _ensure_discovered()
    names = cfg.get("targets")
    if not names:
        return list(_devices_by_name.values())
    return [_devices_by_name[n] for n in names if n in _devices_by_name]


def _send_udp(ip: str, payload: str) -> None:
    """Fire a Govee LAN command at a device. Returns immediately."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.sendto(payload.encode(), (ip, GOVEE_CMD_PORT))
    finally:
        sock.close()


async def _fan_out(devices: list[dict], payload_factory) -> None:
    """Fire `payload_factory(device)` to every device simultaneously.

    Uses a plain UDP `sendto` per device so we don't share any socket
    state — which is what lets two lamps switch at the same instant.
    """
    if not devices:
        return
    loop = asyncio.get_running_loop()
    # run_in_executor keeps us off the event loop for the (negligible)
    # sendto syscalls, and schedules them all at once.
    await asyncio.gather(*(
        loop.run_in_executor(None, _send_udp, d["ip"], payload_factory(d))
        for d in devices
    ))


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


# ---- Commands --------------------------------------------------------------

async def turn_on(cfg: dict) -> None:
    devs = await _resolve_targets(cfg)
    await _fan_out(devs, lambda _d: api_requests.turn_on())


async def turn_off(cfg: dict) -> None:
    devs = await _resolve_targets(cfg)
    await _fan_out(devs, lambda _d: api_requests.turn_off())


async def set_color(cfg: dict, hex_color: str, brightness: int = 100) -> None:
    """Turn on, set color, set brightness — all lamps fire in parallel.

    Within one lamp the three messages are still sent one after another
    (they're separate Govee commands), but the parallelism is across
    lamps: both start their first message at the same instant.
    """
    devs = await _resolve_targets(cfg)
    rgb = _hex_to_rgb(hex_color)
    brightness = max(1, min(100, int(brightness)))

    color_msg = api_requests.color_by_rgb(rgb)
    bright_msg = api_requests.brightness(brightness)
    on_msg = api_requests.turn_on()

    async def _apply(d: dict) -> None:
        loop = asyncio.get_running_loop()
        for msg in (on_msg, color_msg, bright_msg):
            await loop.run_in_executor(None, _send_udp, d["ip"], msg)

    await asyncio.gather(*(_apply(d) for d in devs))


# ---- Preset scenes ---------------------------------------------------------

async def movie_mode(cfg: dict) -> None:
    """Warm orange glow, dim — good for film nights."""
    await set_color(cfg, "#ff6a00", brightness=20)


async def party_mode(cfg: dict) -> None:
    """Bright white — for when things pop off."""
    await set_color(cfg, "#ffffff", brightness=100)


async def sleep_mode(cfg: dict) -> None:
    """Deep red, very dim — low stimulation for winding down."""
    await set_color(cfg, "#8b0000", brightness=5)


# ---- Dispatcher ------------------------------------------------------------

async def handle(cfg: dict) -> None:
    """Route a mapping entry to the right light action."""
    action = cfg.get("action")

    if action == "turn_on":
        await turn_on(cfg)
    elif action == "turn_off":
        await turn_off(cfg)
    elif action == "color":
        await set_color(cfg, cfg.get("color", "#ffffff"),
                        cfg.get("brightness", 100))
    elif action == "movie_mode":
        await movie_mode(cfg)
    elif action == "party_mode":
        await party_mode(cfg)
    elif action == "sleep_mode":
        await sleep_mode(cfg)
    else:
        print(f"[lights] unknown action: {action}")
