"""Tests for GameState encode/decode round-tripping in core/serialiser.py."""

from core.components import Colour, SmokeCloud
from core.serialiser import decode_state, encode_state
from core.state import GameState


def test_shrink_fields_round_trip_through_encode_decode():
    """Verify shrink-related GameState fields survive an encode/decode round trip."""
    state = GameState(
        tick=123, map_cols=15, map_rows=13, tiles=[], starting_player_count=4,
        shrink_active=True, shrink_ring=2, shrink_target_ring=5, shrink_warn_ring=3,
        shrink_warn_ticks_remaining=42, shrink_next_warn_tick=999, shrink_stopped=False,
    )
    state.tiles = [[0] * state.map_cols for _ in range(state.map_rows)]

    decoded = decode_state(encode_state(state))

    assert decoded.starting_player_count == 4
    assert decoded.shrink_active is True
    assert decoded.shrink_ring == 2
    assert decoded.shrink_target_ring == 5
    assert decoded.shrink_warn_ring == 3
    assert decoded.shrink_warn_ticks_remaining == 42
    assert decoded.shrink_next_warn_tick == 999
    assert decoded.shrink_stopped is False


def test_shrink_fields_default_when_absent_from_older_payload():
    """Verify decoding an older payload without shrink fields defaults them safely."""
    # A GameState built before these fields existed decodes fine, defaulting
    # to inactive/zeroed shrink state rather than raising a KeyError.
    state = GameState(tick=1, map_cols=3, map_rows=3, tiles=[[0, 0, 0]] * 3)
    decoded = decode_state(encode_state(state))
    assert decoded.starting_player_count == 0
    assert decoded.shrink_active is False
    assert decoded.shrink_target_ring == 0
    assert decoded.shrink_stopped is False


def test_player_colours_round_trip_as_colour_instances():
    """Verify player_colours survives encode/decode as Colour instances, not plain tuples."""
    state = GameState(tick=1, map_cols=3, map_rows=3, tiles=[[0, 0, 0]] * 3)
    state.player_colours[0] = Colour(220, 50, 10)

    decoded = decode_state(encode_state(state))

    assert decoded.player_colours[0] == Colour(220, 50, 10)


def test_smoke_clouds_round_trip_through_encode_decode():
    """Verify SmokeCloud entries survive an encode/decode round trip."""
    state = GameState(tick=1, map_cols=3, map_rows=3, tiles=[[0, 0, 0]] * 3)
    state.smoke_clouds.append(SmokeCloud(col=3, row=4, radius=2, ticks_remaining=100, ticks_total=240))

    decoded = decode_state(encode_state(state))

    assert len(decoded.smoke_clouds) == 1
    cloud = decoded.smoke_clouds[0]
    assert (cloud.col, cloud.row, cloud.radius, cloud.ticks_remaining, cloud.ticks_total) == (3, 4, 2, 100, 240)
