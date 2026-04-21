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

import profiles as profile_store
from modes import lights, tv, game, audio


ROOT = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(ROOT, "config.json")


# Mode name -> async handler. Each handler accepts the mapping dict.
MODE_HANDLERS = {
    "LIGHTS": lights.handle,
    "TV":     tv.handle,
    "GAME":   game.handle,
    "AUDIO":  audio.handle,
}


def load_active_mappings() -> tuple[str, dict]:
    """Return (active_profile_name, mappings_for_that_profile)."""
    data = profile_store.load()
    return data.get("active", "?"), profile_store.active_mappings(data)


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


async def _run_single(entry: dict) -> None:
    mode = entry.get("mode", "").upper()
    handler = MODE_HANDLERS.get(mode)
    if handler is None:
        print(f"[dispatch] no handler for mode '{mode}'")
        return
    try:
        await handler(entry)
    except Exception as e:
        # We never want a single misbehaving action to kill the listener.
        print(f"[dispatch] error in {mode}: {e}")


async def dispatch(mapping: dict, scope: frozenset[str] | None = None) -> None:
    """Run one or more actions for a mapping entry.

    A mapping can be a single `{mode, action, ...}` dict, or a wrapper
    `{"actions": [entry, entry, ...]}` for chained multi-device triggers
    (e.g. TV on + Netflix + both lights red on a single key). Chained
    actions run concurrently so one slow device doesn't delay another.

    `scope`, if provided, filters out actions whose mode isn't allowed in
    the current profile — built-in profiles enforce their theme so a
    stray TV entry saved into the "lights" profile doesn't actually fire
    the TV.
    """
    actions = mapping.get("actions")
    if isinstance(actions, list):
        runnable = [a for a in actions
                    if profile_store.is_in_scope(a, scope)]
        dropped = len(actions) - len(runnable)
        if dropped:
            print(f"[scope] skipped {dropped} out-of-scope action(s)")
        if runnable:
            await asyncio.gather(*(_run_single(a) for a in runnable))
    else:
        if not profile_store.is_in_scope(mapping, scope):
            mode = mapping.get("mode", "?")
            print(f"[scope] skipped out-of-scope action ({mode}) "
                  "— not allowed in this profile")
            return
        await _run_single(mapping)


def _profiles_mtime() -> float:
    try:
        return os.path.getmtime(profile_store.PROFILES_PATH)
    except OSError:
        return 0.0


async def listen(port_name: str) -> None:
    """Main event loop: read MIDI messages and dispatch.

    Re-reads `profiles.json` whenever its mtime changes so the active
    profile (or edits made in the GUI) take effect without restarting the
    controller.
    """
    loop = asyncio.get_running_loop()

    active, mappings = load_active_mappings()
    scope = profile_store.profile_scope(active)
    mtime = _profiles_mtime()
    scope_label = (", ".join(sorted(scope)).lower() if scope else "mixed")
    print(f"  Profile   : {active}  (scope: {scope_label})")
    print(f"  Mapped    : {len(mappings)} keys")
    print("=" * 52)

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

            # Hot-reload the active profile if the GUI saved a change.
            current = _profiles_mtime()
            if current and current != mtime:
                new_active, new_mappings = load_active_mappings()
                if new_active != active:
                    new_scope = profile_store.profile_scope(new_active)
                    label = (", ".join(sorted(new_scope)).lower()
                             if new_scope else "mixed")
                    print(f"[profile] switched to '{new_active}' "
                          f"({len(new_mappings)} keys, scope: {label})")
                    scope = new_scope
                active, mappings = new_active, new_mappings
                mtime = current

            key = str(msg.note)
            mapping = mappings.get(key)
            if mapping is None:
                continue

            # Fire and forget so one slow action doesn't block the next key.
            asyncio.create_task(dispatch(mapping, scope))


async def main() -> None:
    cfg = load_config()
    port_name = find_midi_port(cfg["midi"]["port_name"])

    print("=" * 52)
    print("  Casio Universal Controller")
    print("=" * 52)
    print(f"  MIDI port : {port_name}")
    print("  Press Ctrl+C to quit.")

    await listen(port_name)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBye.")
        sys.exit(0)
