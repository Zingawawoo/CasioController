"""Game / keyboard emulation via pynput.

Maps friendly string names like KEY_SPACE, KEY_UP, KEY_Z into pynput key
presses so the Casio can drive games (or any app that takes keyboard input).
"""

import asyncio

try:
    from pynput.keyboard import Controller, Key  # type: ignore
    _KB_AVAILABLE = True
except Exception:  # pragma: no cover
    Controller = None  # type: ignore
    Key = None  # type: ignore
    _KB_AVAILABLE = False


_keyboard = Controller() if _KB_AVAILABLE else None


# Named-key aliases -> pynput Key enum values. Anything not listed here is
# treated as a single character (e.g. KEY_Z -> "z").
_SPECIAL_KEYS = {
    "KEY_SPACE":     "space",
    "KEY_ENTER":     "enter",
    "KEY_ESC":       "esc",
    "KEY_TAB":       "tab",
    "KEY_BACKSPACE": "backspace",
    "KEY_SHIFT":     "shift",
    "KEY_CTRL":      "ctrl",
    "KEY_ALT":       "alt",
    "KEY_CMD":       "cmd",
    "KEY_UP":        "up",
    "KEY_DOWN":      "down",
    "KEY_LEFT":      "left",
    "KEY_RIGHT":     "right",
    "KEY_F1":        "f1",
    "KEY_F2":        "f2",
    "KEY_F3":        "f3",
    "KEY_F4":        "f4",
    "KEY_F5":        "f5",
}


def _resolve(key_name: str):
    """Return something pynput.Controller.press can accept."""
    if key_name in _SPECIAL_KEYS:
        return getattr(Key, _SPECIAL_KEYS[key_name])

    # KEY_Z -> "z", KEY_A -> "a"
    if key_name.startswith("KEY_") and len(key_name) == 5:
        return key_name[4].lower()

    # Fallback: a single character like "a" or a raw value.
    return key_name.lower()


async def press_key(key_name: str, hold_ms: int = 40) -> None:
    """Press and release `key_name`. `hold_ms` is how long it's held down."""
    if not _KB_AVAILABLE:
        print("[game] pynput not installed — skipping press")
        return

    key = _resolve(key_name)
    # pynput is synchronous, but the press is instant so we just run it
    # inline and sleep asynchronously for the hold.
    _keyboard.press(key)
    await asyncio.sleep(hold_ms / 1000)
    _keyboard.release(key)


# ---- Dispatcher ------------------------------------------------------------

async def handle(cfg: dict) -> None:
    # The mapping stores the key name in the `action` field (e.g. KEY_SPACE).
    key_name = cfg.get("action")
    if not key_name:
        print("[game] no key configured")
        return
    await press_key(key_name, hold_ms=cfg.get("hold_ms", 40))
