# Casio Universal Controller

Turn your Casio CT-S100 (or any 61-key MIDI keyboard) into a universal
remote. Each key can trigger **smart lights**, a **Samsung TV**, **keyboard
inputs for games**, or **audio playback** — whatever you map it to.

Keys are edited in a small dark-themed GUI and saved to `mappings.json`.
A separate listener reads MIDI in real time and fires the matching action
asynchronously, so slow actions (TV, lights) never block each other.

## Features

- Live MIDI listener (`main.py`) that dispatches key presses by mode
- Editor GUI (`gui.py`) for all 61 keys (C2–C7) with:
  - Mode + action dropdowns
  - Color picker and brightness slider for lights
  - TV remote-key picker
  - Save + Launch Controller buttons
- Four mode handlers that can be extended:
  - `modes/lights.py`  — Govee LAN
  - `modes/tv.py`      — Samsung TV WebSocket
  - `modes/game.py`    — keyboard emulation via pynput
  - `modes/audio.py`   — stub (drop Sonos / Spotify in here)
- Async from end to end so lights, TV, games and audio can fire concurrently

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
python gui.py        # edit mappings
python main.py       # run the controller
```

Plug the Casio in before launching `main.py` so the `CASIO USB-MIDI`
port shows up.

## Configuration

`config.json` holds the device + MIDI details:

```json
{
  "govee":      { "device_mac": "AA:BB:CC:DD:EE:FF", "device_model": "H6159" },
  "samsung_tv": { "host": "192.168.1.100", "port": 8002, "name": "CasioController" },
  "midi":       { "port_name": "CASIO USB-MIDI" }
}
```

### Finding your Govee MAC

1. Enable **LAN Control** in the Govee Home app (Device ▸ Settings ▸ LAN Control).
2. Find the device's IP in your router admin page, then look up its MAC.
3. Or run `arp -a` on a machine on the same Wi-Fi and match the IP to a MAC.
4. Paste the MAC into `config.json`.

Only some Govee models support LAN mode. If yours doesn't, the `modes/lights.py`
handler can be swapped for the cloud API with minimal changes.

### Finding your Samsung TV IP

1. On the TV: **Settings ▸ General ▸ Network ▸ Network Status ▸ IP Settings**.
2. Or check your router's DHCP table for a device named something like
   `Samsung` or `TIZEN`.
3. Put the IP in `config.json`.

The first time `main.py` (or any TV action in the GUI) runs, the TV will
prompt you to allow the new remote. Accept it — the pairing token is saved
to `tv_token.txt` so you only do it once.

### MIDI port

Most of the time the default `CASIO USB-MIDI` name just works. If your
port is named differently, either edit `config.json` or let the controller
fall back to the first available port (it prints a warning when it does).

## How mappings work

`mappings.json` is a plain JSON file keyed by MIDI note number:

```json
{
  "48": { "mode": "LIGHTS", "action": "color", "color": "#ff0000", "brightness": 80 },
  "50": { "mode": "TV",     "action": "netflix" },
  "52": { "mode": "GAME",   "action": "KEY_SPACE" },
  "72": { "mode": "AUDIO",  "action": "play_pause" }
}
```

Middle C is MIDI note 60. The GUI shows note names alongside the number so
you don't have to memorise them.

### Available actions

| Mode   | Actions |
|--------|---------|
| LIGHTS | `turn_on`, `turn_off`, `color` (hex + brightness), `movie_mode`, `party_mode`, `sleep_mode` |
| TV     | `power_on`, `netflix`, `youtube`, `disney`, `prime`, `key` (any Samsung remote code like `KEY_VOLUP`) |
| GAME   | Any `KEY_*` name — letters (`KEY_W`), arrows (`KEY_UP`), modifiers (`KEY_SHIFT`), `KEY_SPACE`, `KEY_ENTER`, etc. |
| AUDIO  | `play_pause`, `next_track`, `prev_track`, `set_volume` (stubbed — wire up your own backend) |

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
  the light.
- **Keys do nothing in games on macOS.** — Give your terminal /
  Python Accessibility permission (System Settings ▸ Privacy & Security ▸
  Accessibility).

## License

MIT. Use it, fork it, remix it.
