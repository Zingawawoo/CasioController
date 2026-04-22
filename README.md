# Casio Universal Controller

Turn your Casio CT-S100 (or any 61-key MIDI keyboard) into a universal
remote. Each key can trigger **smart lights**, a **Samsung TV**, **keyboard
inputs for games**, or **audio playback** — whatever you map it to. A single
key can fire multiple actions in parallel (e.g. TV on → Netflix → two lights
go red), and mappings are grouped into **profiles** you can switch between.

Keys are edited in a dark-themed GUI with a real piano layout and saved to
`profiles.json`. A separate listener reads MIDI in real time and fires the
matching actions asynchronously, so slow actions (TV, lights) never block
each other.

## Features

- **Profiles** — named mapping sets, with three built-in defaults:
  - `tv` — remote-style layout: power, apps, volume, channels, D-pad.
  - `lights` — on/off, scenes, color palette across octaves, per-lamp control.
  - `pc` — WASD + modifiers + arrows + media keys for gaming/keyboard use.
- **Piano layout editor** — the GUI renders all 61 keys (C2–C7) as an actual
  piano. Click a key to edit it; mapped keys show a colored badge by mode.
- **Multi-action keys** — stack several actions under one key. The dispatcher
  runs them concurrently, so "TV on + Netflix + both lights red" is one press.
- **Multi-light control** — `config.json` holds a list of Govee devices, each
  with a user-defined name; a light action targets any subset via checkboxes
  (default: all lights).
- **Four extensible mode handlers**:
  - `modes/lights.py`  — Govee LAN (discovers devices, matches by MAC suffix)
  - `modes/tv.py`      — Samsung TV WebSocket (keys + app launch)
  - `modes/game.py`    — keyboard emulation via pynput
  - `modes/audio.py`   — stub (drop Sonos / Spotify in here)
- Async end-to-end so lights, TV, games and audio fire in parallel.

## Quick start

```bash
git clone https://github.com/zingawawoo/casiocontroller.git
cd casiocontroller
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Edit `config.json` with your own device info (see below), then:

```bash
python gui.py        # edit mappings / profiles, start/stop the controller
python main.py       # or run the controller headless (uses the active profile)
```

The GUI has a **Start controller** button that spawns `main.py` as a
subprocess and streams its log into a panel at the bottom, so you don't
need a second terminal. Hit the same button to stop it.

Plug the Casio in before launching `main.py` so the `CASIO USB-MIDI`
port shows up. On first run, `profiles.json` is generated with the three
default profiles (any pre-existing `mappings.json` is imported as a
`custom` profile).

## Configuration

`config.json` holds the device + MIDI details:

```json
{
  "govee": {
    "devices": [
      {"name": "tv_light", "mac": "60:74:F4:A6:C3:C5", "model": "H6199"},
      {"name": "lamp_1",   "mac": "5C:E7:53:20:BA:EA", "model": "H6008"},
      {"name": "lamp_2",   "mac": "5C:E7:53:14:88:08", "model": "H6008"}
    ]
  },
  "samsung_tv": { "host": "192.168.1.174", "port": 8002, "name": "CasioController" },
  "midi":       { "port_name": "CASIO USB-MIDI" }
}
```

The `govee.devices` list is the source of names used in light-targeting —
pick anything memorable (`lamp_1`, `desk`, `kitchen`, …). In the GUI,
LIGHTS actions get a checkbox per device so one key can hit any subset.

### Finding your Govee MAC

1. Enable **LAN Control** in the Govee Home app (Device ▸ Settings ▸ LAN Control).
2. Find the device's IP in your router admin page, then look up its MAC.
3. Or run `ip neigh` (or `arp -a`) on a machine on the same Wi-Fi and match
   the IP to a MAC.
4. Paste the 6-byte MAC into `config.json` — the handler matches it by
   suffix against Govee's full 8-byte device ID.

Only some Govee models support LAN mode (H6008, H6159, H6076, etc.). A few
models — notably the **H6199 TV light bar** — don't respond to LAN scans.
Unreachable devices are logged as warnings and skipped at dispatch time,
so the rest of your lights still work.

### Finding your Samsung TV IP

1. On the TV: **Settings ▸ General ▸ Network ▸ Network Status ▸ IP Settings**.
2. Or check your router's DHCP table for a device named something like
   `Samsung` or `TIZEN`.
3. Put the IP in `config.json`.

The first time a TV action runs, the TV will prompt you to allow the new
remote. Accept it — the pairing token is saved to `tv_token.txt`.

### MIDI port

Most of the time the default `CASIO USB-MIDI` name just works. If your
port is named differently, either edit `config.json` or let the controller
fall back to the first available port (it prints a warning when it does).

## How mappings work

`profiles.json` wraps multiple profiles and the currently active one:

```json
{
  "active": "lights",
  "profiles": {
    "tv":     { "36": {"mode": "TV",     "action": "power_on"}, "...": "..." },
    "lights": { "48": {"mode": "LIGHTS", "action": "color", "color": "#ff0000", "brightness": 80} },
    "pc":     { "36": {"mode": "GAME",   "action": "KEY_W"}, "...": "..." }
  }
}
```

Each profile is a `{midi_note: entry}` object. Middle C is MIDI note 60;
the piano view shows note names so you don't have to memorize numbers.

### Single-action vs. multi-action entries

A single-action entry is a flat dict:

```json
"48": { "mode": "TV", "action": "netflix" }
```

To fire several actions from one key, wrap them in an `actions` list:

```json
"60": {
  "actions": [
    { "mode": "TV",     "action": "power_on" },
    { "mode": "TV",     "action": "netflix" },
    { "mode": "LIGHTS", "action": "color", "color": "#ff0000", "brightness": 60 }
  ]
}
```

The dispatcher runs all entries in an `actions` list concurrently via
`asyncio.gather`, so the TV, lights, and anything else start in parallel.

### Scoping lights

A LIGHTS entry can include `targets`, a list of device names from
`config.json`:

```json
"40": { "mode": "LIGHTS", "action": "turn_on", "targets": ["lamp_1", "lamp_2"] }
```

Omit `targets` (or include every device) and the action fans out to every
configured light.

### Available actions

| Mode   | Actions |
|--------|---------|
| LIGHTS | `turn_on`, `turn_off`, `color` (hex + brightness), `movie_mode`, `party_mode`, `sleep_mode` |
| TV     | `power_on`, `netflix`, `youtube`, `disney`, `prime`, `key` (any Samsung remote code like `KEY_VOLUP`) |
| GAME   | Any `KEY_*` name — letters (`KEY_W`), arrows (`KEY_UP`), modifiers (`KEY_SHIFT`), `KEY_SPACE`, `KEY_ENTER`, etc. |
| AUDIO  | `play_pause`, `next_track`, `prev_track`, `set_volume` (stubbed — wire up your own backend) |

## Using it from Claude (MCP)

`mcp_server.py` exposes the same handlers as MCP tools so Claude Desktop
or Claude Code can control your lights and TV directly. The server runs
locally on your machine, so it can still reach devices on your LAN.

**Claude Desktop** — edit `claude_desktop_config.json`:

```
macOS:   ~/Library/Application Support/Claude/claude_desktop_config.json
Windows: %APPDATA%\Claude\claude_desktop_config.json
```

```json
{
  "mcpServers": {
    "casio-controller": {
      "command": "python",
      "args": ["/absolute/path/to/casiocontroller/mcp_server.py"]
    }
  }
}
```

Restart the desktop app. You should see the tools listed under the 🔌
icon.

**Claude Code:**

```bash
claude mcp add casio-controller python /absolute/path/to/mcp_server.py
```

**Tools exposed:**

- `lights_turn_on(targets?)`, `lights_turn_off(targets?)`
- `lights_set_color(hex_color, brightness, targets?)`
- `lights_preset(preset, targets?)` — `movie_mode` / `party_mode` / `sleep_mode`
- `tv_power`, `tv_launch_app(app)`, `tv_send_key(key)`
- `game_press_key(key, hold_ms)`
- `audio_play_pause`, `audio_next_track`, `audio_prev_track`, `audio_set_volume`
- `profile_list`, `profile_active`, `profile_switch(name)`

`targets` is a list of device names from `config.json`; omit it to hit
every configured light. Switching profiles via MCP takes effect on the
next key press — `main.py` hot-reloads `profiles.json` automatically.

## Running on Windows

Everything is pure Python and cross-platform. Concrete notes:

- **Install Python 3.11+** from python.org and tick "Add to PATH" in the
  installer. The Microsoft Store build also works (you'll just run it as
  `py` or `python3` instead of `python`).
- **Create and activate a venv:**
  ```powershell
  python -m venv .venv
  .venv\Scripts\activate
  pip install -r requirements.txt
  ```
- **`python-rtmidi` wheels** are prebuilt for common Python versions on
  Windows, so `pip install` just works. If pip tries to compile from
  source, install the "Build Tools for Visual Studio" (C++ workload) and
  retry.
- **MIDI port name.** Windows sometimes appends a number, e.g.
  `CASIO USB-MIDI 0`. The controller falls back to the first port if it
  can't find an exact match, and logs the real name — paste that into
  `config.json`.
- **Claude Desktop MCP config** lives at
  `%APPDATA%\Claude\claude_desktop_config.json`. Use an absolute path to
  `mcp_server.py` with double-escaped backslashes:
  ```json
  {
    "mcpServers": {
      "casio-controller": {
        "command": "python",
        "args": ["C:\\Users\\you\\casiocontroller\\mcp_server.py"]
      }
    }
  }
  ```
  If `python` isn't on PATH, swap in `"py"` or the full path to
  `python.exe` inside your venv.
- **Game mode (pynput).** Works against most apps out of the box. For
  games with anti-cheat, you may need to run the controller (or the
  terminal launching it) as administrator.

## Adding your own features

Each mode is a self-contained module in `modes/` that exposes an async
`handle(cfg)` coroutine. To add, say, a Hue integration:

1. Create `modes/hue.py` with an `async def handle(cfg): ...`.
2. Register it in `main.py`'s `MODE_HANDLERS` dict.
3. Add `"HUE"` to `ACTIONS_BY_MODE` in `gui.py`.

That's it — the GUI, the JSON format, and the dispatcher all follow the
same contract.

## Troubleshooting

- **"No MIDI input ports found."** — Plug the Casio in, make sure it's on,
  and re-run. On Linux you may need the `libasound2` + `librtmidi-dev`
  packages before installing `python-rtmidi`.
- **TV action hangs the first time.** — That's the pairing prompt; look at
  the TV screen and hit Allow. It's only once.
- **Govee device not found.** — Double-check LAN Control is on in the app
  and that the machine running the controller is on the same subnet as
  the light. If a specific model (e.g. H6199) doesn't appear in scans,
  it probably doesn't support LAN mode.
- **Keys do nothing in games on macOS.** — Give your terminal /
  Python Accessibility permission (System Settings ▸ Privacy & Security ▸
  Accessibility).
- **Remote-desktop permission pop-ups on Linux/Wayland.** — GAME-mode
  keypresses go through pynput, which on Wayland asks the portal each
  time. Install `ydotool` and give your user access to `/dev/uinput` (via
  an `input`-group udev rule) to bypass the portal.

## License

MIT. Use it, fork it, remix it.
