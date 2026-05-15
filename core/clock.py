"""Fixed-timestep tick clock for the server."""
from __future__ import annotations

import time

from core.tick import TICK_DT, TickNumber


class TickClock:
    def __init__(self) -> None:
        self._tick: TickNumber = 0
        self._last_tick_time: float = time.monotonic()

    @property
    def current_tick(self) -> TickNumber:
        return self._tick

    def should_tick(self) -> bool:
        return time.monotonic() - self._last_tick_time >= TICK_DT

    def reset(self) -> None:
        """Reset the clock to now so no ticks are owed for past lobby wait time."""
        self._last_tick_time = time.monotonic()
        self._tick = 0

    def advance(self) -> TickNumber:
        self._last_tick_time += TICK_DT
        self._tick += 1
        return self._tick

    def ticks_for_seconds(self, seconds: float) -> int:
        return max(1, round(seconds / TICK_DT))

    def elapsed_since(self, tick: TickNumber) -> int:
        return self._tick - tick
