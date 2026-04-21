"""Audio control stub.

Placeholder actions for media playback. A Sonos (via SoCo) or Spotify (via
Spotipy) integration can be dropped in here later — the dispatcher shape
below is the only contract `main.py` cares about.
"""

import asyncio


async def play_pause() -> None:
    print("[audio] play/pause")


async def next_track() -> None:
    print("[audio] next track")


async def prev_track() -> None:
    print("[audio] previous track")


async def set_volume(level: int) -> None:
    level = max(0, min(100, int(level)))
    print(f"[audio] set volume -> {level}")


# ---- Dispatcher ------------------------------------------------------------

async def handle(cfg: dict) -> None:
    action = cfg.get("action")

    if action == "play_pause":
        await play_pause()
    elif action == "next_track":
        await next_track()
    elif action == "prev_track":
        await prev_track()
    elif action == "set_volume":
        await set_volume(cfg.get("level", 50))
    else:
        print(f"[audio] unknown action: {action}")
