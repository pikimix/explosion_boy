"""Small shared UI geometry types and helpers."""
from __future__ import annotations

from dataclasses import dataclass

import arcade

from app.ui.hud import HUD_WIDTH


@dataclass(frozen=True)
class Bounds:
    """An axis-aligned rectangle in window space."""
    left: float
    right: float
    bottom: float
    top: float


def make_playfield_camera(
    width: float, height: float, map_w: float, map_h: float, hud_width: float = HUD_WIDTH,
) -> arcade.camera.Camera2D:
    """Build the camera that frames a map inside the play area right of the HUD.

    Parameters
    ----------
    width, height : float
        Current window size, in pixels.
    map_w, map_h : float
        Size of the map to frame, in pixels.
    hud_width : float, optional
        Width of the HUD strip reserved on the left (default `HUD_WIDTH`).
    """
    play_w = width - hud_width
    return arcade.camera.Camera2D(
        viewport=arcade.LBWH(hud_width, 0, play_w, height),
        position=(map_w / 2, map_h / 2),
        zoom=min(play_w / map_w, height / map_h),
    )


def unit_value_from_x(x: float, left: float, width: float) -> float:
    """Convert an x pixel coordinate to a [0, 1] fraction across a slider track."""
    return max(0.0, min(1.0, (x - left) / width))
