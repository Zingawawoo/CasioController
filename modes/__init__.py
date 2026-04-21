"""Mode handlers for the Casio Universal Controller.

Each submodule exposes a `handle(action_cfg)` coroutine that receives the
mapping entry for a pressed key and performs the corresponding action.
"""

from . import lights, tv, game, audio

__all__ = ["lights", "tv", "game", "audio"]
