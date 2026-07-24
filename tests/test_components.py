"""Tests for the small dataclasses added to replace shape-tuples: Cell, Colour,
Position, Velocity (core/components.py), Bounds (app/ui/geometry.py), and
Frame (engine/transport.py)."""

from app.ui.geometry import Bounds
from core.components import Cell, Colour, Position, Velocity
from engine.transport import Frame


def test_cell_is_hashable_and_usable_as_dict_key():
    """Cell instances with equal fields hash and compare equal, so they work as dict/set keys."""
    cells = {Cell(1, 2): "a"}
    assert cells[Cell(1, 2)] == "a"
    assert Cell(1, 2) == Cell(1, 2)
    assert Cell(1, 2) != Cell(2, 1)


def test_colour_as_tuple_round_trips_rgb_values():
    """as_tuple returns the (r, g, b) values in order, for arcade/msgpack boundaries."""
    colour = Colour(220, 50, 10)
    assert colour.as_tuple() == (220, 50, 10)


def test_position_and_velocity_hold_distinct_fields():
    """Position and Velocity are distinct types even though both wrap two floats,
    so a caller can't accidentally pass one where the other is expected."""
    pos = Position(3.0, 4.0)
    vel = Velocity(1.0, -1.0)
    assert (pos.x, pos.y) == (3.0, 4.0)
    assert (vel.vx, vel.vy) == (1.0, -1.0)
    assert pos != vel


def test_bounds_fields_are_in_consistent_left_right_bottom_top_order():
    """Bounds always exposes left/right/bottom/top by name, avoiding the
    field-order mismatch that previously existed between scene helper methods."""
    b = Bounds(left=0.0, right=10.0, bottom=0.0, top=5.0)
    assert b.left == 0.0
    assert b.right == 10.0
    assert b.bottom == 0.0
    assert b.top == 5.0


def test_frame_holds_channel_and_payload():
    """Frame carries the (channel, payload) pair produced by a transport backend's framing."""
    frame = Frame(channel=1, payload=b"hello")
    assert frame.channel == 1
    assert frame.payload == b"hello"
