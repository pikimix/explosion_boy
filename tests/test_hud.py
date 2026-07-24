"""Tests for app/ui/hud.py's player colour resolution.

Regression coverage for a bug where rendering code read a `Colour` instance
out of `state.player_colours` and then treated it like a plain RGB tuple
(splatting it with `*` or slicing it with `[:3]`), which raised a TypeError
once `player_colours` values became `Colour` dataclass instances instead of
tuples. `player_rgb` is the single place that conversion now happens.
"""

from app.ui.hud import player_rgb
from core.components import Colour
from core.state import GameState
from engine.config import PLAYER_COLOURS


def _empty_state() -> GameState:
    return GameState(tick=0, map_cols=3, map_rows=3, tiles=[[0, 0, 0]] * 3)


def test_player_rgb_returns_chosen_colour_as_plain_tuple():
    """A player with a chosen Colour gets that colour back as a plain (r, g, b) tuple."""
    state = _empty_state()
    state.player_colours[0] = Colour(220, 50, 10)

    rgb = player_rgb(state, 0)

    assert rgb == (220, 50, 10)
    assert isinstance(rgb, tuple)


def test_player_rgb_falls_back_to_default_palette_when_unset():
    """A player who hasn't chosen a colour falls back to PLAYER_COLOURS, not a crash."""
    state = _empty_state()

    rgb = player_rgb(state, 0)

    assert rgb == PLAYER_COLOURS[0][:3]


def test_player_rgb_result_is_splattable():
    """Regression: the result must be a plain iterable so `(*rgb, 255)` works,
    unlike a bare Colour instance which raised 'must be an iterable, not Colour'."""
    state = _empty_state()
    state.player_colours[0] = Colour(1, 2, 3)

    rgba = (*player_rgb(state, 0), 255)

    assert rgba == (1, 2, 3, 255)
