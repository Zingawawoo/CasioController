"""Profile storage and defaults for the Casio Universal Controller.

A profile is a named set of mappings ({midi_note: action_entry}). Only
one profile is active at a time. Defaults for TV, Lights, and PC modes
are generated on first run so the user has something usable out of the
box without hand-editing JSON.
"""

import json
import os


ROOT = os.path.dirname(os.path.abspath(__file__))
PROFILES_PATH = os.path.join(ROOT, "profiles.json")
LEGACY_MAPPINGS_PATH = os.path.join(ROOT, "mappings.json")

DEFAULT_PROFILE_NAMES = ("tv", "lights", "pc")

# Built-in profiles are scoped to specific modes. A stray entry in the
# wrong mode (e.g. a TV action saved into the "lights" profile) is
# ignored at dispatch time so the profile name matches what actually
# fires. Custom profiles have no scope and can mix any modes freely —
# that's how you build multi-device scenes.
PROFILE_SCOPE: dict[str, frozenset[str]] = {
    "tv":     frozenset({"TV"}),
    "lights": frozenset({"LIGHTS"}),
    "pc":     frozenset({"GAME", "AUDIO"}),
}


def profile_scope(name: str) -> frozenset[str] | None:
    """Return the allowed mode set for `name`, or None for unscoped profiles."""
    return PROFILE_SCOPE.get(name)


def is_in_scope(entry: dict, scope: frozenset[str] | None) -> bool:
    """Does `entry` belong in a profile with this scope?"""
    if scope is None:
        return True
    return entry.get("mode", "").upper() in scope


def _tv_profile() -> dict:
    """All 3 octaves of TV navigation, apps, and volume."""
    return {
        # Octave C2 — power + navigation
        "36": {"mode": "TV", "action": "power_on"},
        "38": {"mode": "TV", "action": "key", "key": "KEY_HOME"},
        "40": {"mode": "TV", "action": "key", "key": "KEY_MENU"},
        "41": {"mode": "TV", "action": "key", "key": "KEY_UP"},
        "42": {"mode": "TV", "action": "key", "key": "KEY_ENTER"},
        "43": {"mode": "TV", "action": "key", "key": "KEY_DOWN"},
        "45": {"mode": "TV", "action": "key", "key": "KEY_LEFT"},
        "46": {"mode": "TV", "action": "key", "key": "KEY_RETURN"},
        "47": {"mode": "TV", "action": "key", "key": "KEY_RIGHT"},

        # Octave C3 — streaming apps
        "48": {"mode": "TV", "action": "netflix"},
        "50": {"mode": "TV", "action": "youtube"},
        "52": {"mode": "TV", "action": "disney"},
        "53": {"mode": "TV", "action": "prime"},

        # Octave C4 — volume + channel
        "60": {"mode": "TV", "action": "key", "key": "KEY_VOLUP"},
        "62": {"mode": "TV", "action": "key", "key": "KEY_VOLDOWN"},
        "64": {"mode": "TV", "action": "key", "key": "KEY_MUTE"},
        "65": {"mode": "TV", "action": "key", "key": "KEY_CHUP"},
        "67": {"mode": "TV", "action": "key", "key": "KEY_CHDOWN"},
    }


def _lights_profile() -> dict:
    """Global on/off + scenes, then a color palette, then per-lamp control."""
    def color(hx: str, br: int = 80) -> dict:
        return {"mode": "LIGHTS", "action": "color",
                "color": hx, "brightness": br}
    return {
        # Octave C2 — global power + scenes
        "36": {"mode": "LIGHTS", "action": "turn_on"},
        "38": {"mode": "LIGHTS", "action": "turn_off"},
        "40": {"mode": "LIGHTS", "action": "movie_mode"},
        "41": {"mode": "LIGHTS", "action": "party_mode"},
        "43": {"mode": "LIGHTS", "action": "sleep_mode"},

        # Octave C3 — warm-to-cool color palette
        "48": color("#ff0000"),       # red
        "50": color("#ff8800"),       # orange
        "52": color("#ffee00"),       # yellow
        "53": color("#00ff33"),       # green
        "55": color("#00ddff"),       # cyan
        "57": color("#2244ff"),       # blue
        "59": color("#ff00ff"),       # magenta

        # Octave C4 — whites
        "60": color("#ffffff", 100),  # bright white
        "62": color("#ffdd99", 60),   # warm white
        "64": color("#ffffff", 20),   # dim white

        # Octave C5 — per-lamp targeting (lamp_1 only)
        "72": {"mode": "LIGHTS", "action": "turn_on",  "targets": ["lamp_1"]},
        "74": {"mode": "LIGHTS", "action": "turn_off", "targets": ["lamp_1"]},

        # Octave C6 — per-lamp targeting (lamp_2 only)
        "84": {"mode": "LIGHTS", "action": "turn_on",  "targets": ["lamp_2"]},
        "86": {"mode": "LIGHTS", "action": "turn_off", "targets": ["lamp_2"]},
    }


def _pc_profile() -> dict:
    """Gaming/keyboard emulation on the low end, media keys up top."""
    def game(key: str) -> dict:
        return {"mode": "GAME", "action": key}
    return {
        # Octave C2 — WASD + movement modifiers
        "36": game("KEY_W"),
        "38": game("KEY_A"),
        "40": game("KEY_S"),
        "41": game("KEY_D"),
        "43": game("KEY_SPACE"),
        "45": game("KEY_SHIFT"),
        "47": game("KEY_CTRL"),

        # Octave C3 — common hotkeys
        "48": game("KEY_Q"),
        "50": game("KEY_E"),
        "52": game("KEY_Z"),
        "53": game("KEY_X"),
        "55": game("KEY_TAB"),
        "57": game("KEY_ESC"),
        "59": game("KEY_ENTER"),

        # Octave C4 — arrow keys + alt
        "60": game("KEY_UP"),
        "62": game("KEY_DOWN"),
        "64": game("KEY_LEFT"),
        "65": game("KEY_RIGHT"),
        "67": game("KEY_ALT"),

        # Octave C5 — media controls
        "72": {"mode": "AUDIO", "action": "play_pause"},
        "74": {"mode": "AUDIO", "action": "next_track"},
        "76": {"mode": "AUDIO", "action": "prev_track"},
    }


def build_default_profiles() -> dict:
    return {
        "tv":     _tv_profile(),
        "lights": _lights_profile(),
        "pc":     _pc_profile(),
    }


def _migrate_from_legacy() -> dict | None:
    """If an old flat mappings.json exists, import it as a 'custom' profile."""
    if not os.path.exists(LEGACY_MAPPINGS_PATH):
        return None
    try:
        with open(LEGACY_MAPPINGS_PATH, "r") as f:
            data = json.load(f)
    except Exception:
        return None
    return data or None


def load() -> dict:
    """Return `{active: str, profiles: {name: {note: entry}}}`.

    On first run, writes a seeded profiles.json with tv/lights/pc defaults
    (and imports any pre-existing mappings.json as a 'custom' profile).
    """
    if os.path.exists(PROFILES_PATH):
        with open(PROFILES_PATH, "r") as f:
            data = json.load(f)
        # Backfill any missing defaults — handy if the user deletes one.
        defaults = build_default_profiles()
        for name, mapping in defaults.items():
            data.setdefault("profiles", {})
            data["profiles"].setdefault(name, mapping)
        data.setdefault("active", next(iter(data["profiles"])))
        return data

    profiles = build_default_profiles()
    active = "pc"

    legacy = _migrate_from_legacy()
    if legacy:
        profiles["custom"] = legacy
        active = "custom"

    data = {"active": active, "profiles": profiles}
    save(data)
    return data


def save(data: dict) -> None:
    with open(PROFILES_PATH, "w") as f:
        json.dump(data, f, indent=2, sort_keys=True)


def is_default_profile(name: str) -> bool:
    return name in DEFAULT_PROFILE_NAMES


def reset_to_default(data: dict, name: str) -> bool:
    """Overwrite `data['profiles'][name]` with its built-in default.

    Returns True if `name` is a known default and was reset, False if it's
    a user profile with no default to fall back to.
    """
    defaults = build_default_profiles()
    if name not in defaults:
        return False
    data.setdefault("profiles", {})[name] = defaults[name]
    return True


def reset_all_defaults(data: dict) -> list[str]:
    """Restore every built-in profile (tv/lights/pc) to its default layout.

    User-created profiles are left untouched. Returns the list of profile
    names that were reset so the caller can tell the user what changed.
    """
    defaults = build_default_profiles()
    data.setdefault("profiles", {})
    for name, mapping in defaults.items():
        data["profiles"][name] = mapping
    return list(defaults.keys())


def active_mappings(data: dict) -> dict:
    """Return the mapping dict for the active profile."""
    name = data.get("active")
    profiles = data.get("profiles", {})
    if name in profiles:
        return profiles[name]
    if profiles:
        return next(iter(profiles.values()))
    return {}
