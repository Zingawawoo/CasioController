"""Casio Universal Controller — MIDI listener.

Opens the `CASIO USB-MIDI` input, loads the key mappings from
`mappings.json`, and dispatches each key press to the matching mode
handler using asyncio so IO-heavy actions (TV, lights) don't block each
other.
"""

import asyncio
import json
import os
import sys

import mido

from modes import lights, tv, game, audio


ROOT = os.path.dirname(os.path.abspath(__file__))
MAPPINGS_PATH = os.path.join(ROOT, "mappings.json")
CONFIG_PATH = os.path.join(ROOT, "config.json")


# Mode name -> async handler. Each handler accepts the mapping dict.
MODE_HANDLERS = {
    "LIGHTS": lights.handle,
    "TV":     tv.handle,
    "GAME":   game.handle,
    "AUDIO":  audio.handle,
}


def load_mappings() -> dict:
    with open(MAPPINGS_PATH, "r") as f:
        return json.load(f)


def load_config() -> dict:
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)


def find_midi_port(preferred_name: str) -> str:
    """Return a MIDI input port whose name contains `preferred_name`.

    Falls back to the first available port if nothing matches, and raises
    if none are connected so we fail loudly instead of silently hanging.
    """
    ports = mido.get_input_names()
    for p in ports:
        if preferred_name.lower() in p.lower():
            return p

    if not ports:
        raise RuntimeError(
            "No MIDI input ports found. Plug in the Casio and try again."
        )

    print(f"[warn] '{preferred_name}' not found. Using '{ports[0]}' instead.")
    return ports[0]


async def dispatch(mapping: dict) -> None:
    """Run the correct mode handler for a mapping entry."""
    mode = mapping.get("mode", "").upper()
    handler = MODE_HANDLERS.get(mode)
    if handler is None:
        print(f"[dispatch] no handler for mode '{mode}'")
        return

    try:
        await handler(mapping)
    except Exception as e:
        # We never want a single misbehaving action to kill the listener.
        print(f"[dispatch] error in {mode}: {e}")


async def listen(port_name: str, mappings: dict) -> None:
    """Main event loop: read MIDI messages and dispatch."""
    loop = asyncio.get_running_loop()

    # mido's blocking iterator doesn't play nicely with asyncio, so we use
    # a callback that marshals messages onto a queue the loop can await.
    queue: asyncio.Queue = asyncio.Queue()

    def on_message(msg):
        # Called on mido's reader thread — just hand off to the loop.
        loop.call_soon_threadsafe(queue.put_nowait, msg)

    with mido.open_input(port_name, callback=on_message):
        while True:
            msg = await queue.get()

            # We care about real note-on presses, not releases (which some
            # keyboards send as note_on with velocity 0).
            if msg.type != "note_on" or msg.velocity == 0:
                continue

            key = str(msg.note)
            mapping = mappings.get(key)
            if mapping is None:
                continue

            # Fire and forget so one slow action doesn't block the next key.
            asyncio.create_task(dispatch(mapping))


async def main() -> None:
    cfg = load_config()
    mappings = load_mappings()

    port_name = find_midi_port(cfg["midi"]["port_name"])

    print("=" * 52)
    print("  Casio Universal Controller")
    print("=" * 52)
    print(f"  MIDI port : {port_name}")
    print(f"  Mapped    : {len(mappings)} keys")
    print("  Press Ctrl+C to quit.")
    print("=" * 52)

    await listen(port_name, mappings)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBye.")
        sys.exit(0)
