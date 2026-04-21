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
    from samsungtvws.remote import ChannelEmitCommand, SendRemoteKey  # type: ignore
    _TV_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    SamsungTVWSAsyncRemote = None  # type: ignore
    ChannelEmitCommand = None  # type: ignore
    SendRemoteKey = None  # type: ignore
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

# Keep the connect attempt short — a Samsung TV that's powered off won't
# answer on port 8002 at all, and we'd rather fail loudly than hang the
# dispatcher forever.
CONNECT_TIMEOUT = 4.0


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
        host = cfg["host"]
        port = cfg.get("port", 8002)

        remote = SamsungTVWSAsyncRemote(
            host=host, port=port, token_file=TOKEN_PATH,
            name=cfg.get("name", "CasioController"),
        )
        try:
            await asyncio.wait_for(remote.start_listening(),
                                   timeout=CONNECT_TIMEOUT)
        except asyncio.TimeoutError:
            # Clean up the half-open remote so the next keypress retries
            # instead of finding a broken cached instance.
            try:
                await remote.close()
            except Exception:
                pass
            raise RuntimeError(
                f"TV at {host}:{port} didn't respond within "
                f"{CONNECT_TIMEOUT:.0f}s. Is it powered on? "
                "(Standby is fine; fully off won't answer.)"
            )
        except Exception as e:
            try:
                await remote.close()
            except Exception:
                pass
            raise RuntimeError(
                f"TV at {host}:{port} couldn't connect: {e}"
            )

        _remote = remote
        return _remote


def _clear_cached_remote() -> None:
    """Drop the cached connection so the next keypress opens a fresh one."""
    global _remote
    _remote = None


SEND_TIMEOUT = 4.0


async def _send(command) -> None:
    """Wrap `remote.send_command` with a timeout + cache-invalidation.

    If the TV drops the socket between keypresses the cached remote will
    error or hang; wiping the cache lets the next press reconnect.
    """
    remote = await _get_remote()
    try:
        await asyncio.wait_for(remote.send_command(command),
                               timeout=SEND_TIMEOUT)
    except Exception as e:
        _clear_cached_remote()
        raise RuntimeError(f"TV send failed: {e}")


async def send_key(key: str) -> None:
    """Send a raw remote key like KEY_VOLUP, KEY_UP, KEY_ENTER."""
    await _send(SendRemoteKey.click(key))


async def power_on() -> None:
    """Toggle power (Samsung's WebSocket API uses the same key for on/off)."""
    await send_key("KEY_POWER")


async def launch_app(app_id: str) -> None:
    """Launch a Tizen app by numeric app ID."""
    await _send(ChannelEmitCommand.launch_app(app_id))


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
