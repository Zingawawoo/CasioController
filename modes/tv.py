"""Samsung TV control over the local WebSocket API (port 8002).

Uses `samsungtvws` with its async client. A pairing token is cached to
`tv_token.txt` so you only need to approve the remote on the TV the first
time you run it.

Exposed actions (via `handle`): power_on, netflix, youtube, disney, prime,
and `key` (for arbitrary remote key codes like KEY_VOLUP).
"""

import asyncio
import json
import os

try:
    from samsungtvws.async_remote import SamsungTVWSAsyncRemote  # type: ignore
    _TV_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    SamsungTVWSAsyncRemote = None  # type: ignore
    _TV_AVAILABLE = False


ROOT = os.path.dirname(os.path.dirname(__file__))
CONFIG_PATH = os.path.join(ROOT, "config.json")
TOKEN_PATH = os.path.join(ROOT, "tv_token.txt")

# Samsung Tizen app IDs for common streaming apps.
APP_IDS = {
    "netflix": "3201907018807",
    "youtube": "111299001912",
    "disney":  "3201901017640",
    "prime":   "3201910019365",
}

_remote = None
_lock = asyncio.Lock()


def _load_config() -> dict:
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)


async def _get_remote():
    """Return a connected SamsungTVWSAsyncRemote instance (cached)."""
    global _remote

    if not _TV_AVAILABLE:
        raise RuntimeError(
            "samsungtvws not installed. Run: pip install samsungtvws[async]"
        )

    if _remote is not None:
        return _remote

    async with _lock:
        if _remote is not None:
            return _remote

        cfg = _load_config()["samsung_tv"]
        _remote = SamsungTVWSAsyncRemote(
            host=cfg["host"],
            port=cfg.get("port", 8002),
            token_file=TOKEN_PATH,
            name=cfg.get("name", "CasioController"),
        )
        await _remote.start_listening()
        return _remote


async def power_on() -> None:
    """Toggle power (Samsung's WebSocket API uses the same key for on/off)."""
    remote = await _get_remote()
    await remote.send_command("KEY_POWER")


async def launch_app(app_id: str) -> None:
    """Launch a Tizen app by numeric app ID."""
    remote = await _get_remote()
    # Newer samsungtvws versions expose app launch via a dedicated helper.
    if hasattr(remote, "run_app"):
        await remote.run_app(app_id)
    else:
        # Fallback for older API shapes.
        await remote.send_command({"method": "ms.channel.emit",
                                    "params": {"event": "ed.apps.launch",
                                               "to": "host",
                                               "data": {"appId": app_id}}})


async def send_key(key: str) -> None:
    """Send a raw remote key like KEY_VOLUP, KEY_UP, KEY_ENTER."""
    remote = await _get_remote()
    await remote.send_command(key)


# ---- Dispatcher ------------------------------------------------------------

async def handle(cfg: dict) -> None:
    action = cfg.get("action")

    if action == "power_on":
        await power_on()
    elif action in APP_IDS:
        await launch_app(APP_IDS[action])
    elif action == "launch_app":
        await launch_app(cfg.get("app_id", ""))
    elif action == "key":
        await send_key(cfg.get("key", "KEY_POWER"))
    else:
        print(f"[tv] unknown action: {action}")
