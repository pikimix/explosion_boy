"""Small shared UI geometry types."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Bounds:
    """An axis-aligned rectangle in window space."""
    left: float
    right: float
    bottom: float
    top: float
