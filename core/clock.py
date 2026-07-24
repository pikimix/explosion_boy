"""Fixed-timestep tick clock for the server."""
from __future__ import annotations

import time

from core.tick import TickNumber


class TickClock:
    """Fixed-timestep accumulator that tracks tick count and timing."""

    def __init__(self, tick_rate: int = 60) -> None:
        self._tick: TickNumber = 0
        self._tick_dt: float = 1.0 / tick_rate
        self._last_tick_time: float = time.monotonic()

    @property
    def current_tick(self) -> TickNumber:
        """Return the current tick number."""
        return self._tick

    def should_tick(self) -> bool:
        """Check whether enough time has elapsed for the next tick to fire.

        Returns
        -------
        bool
            True if at least one tick's worth of time has passed since the
            last tick, False otherwise.
        """
        return time.monotonic() - self._last_tick_time >= self._tick_dt

    def reset(self) -> None:
        """Reset the clock to now so no ticks are owed for past lobby wait time."""
        self._last_tick_time = time.monotonic()
        self._tick = 0

    def advance(self) -> TickNumber:
        """Advance the clock by one tick.

        Returns
        -------
        TickNumber
            The new current tick number after advancing.
        """
        self._last_tick_time += self._tick_dt
        self._tick += 1
        return self._tick

    def seconds_until_next_tick(self) -> float:
        """Return the number of seconds remaining until the next tick is due.

        Returns
        -------
        float
            Seconds until the next tick, clamped to a minimum of 0.0.
        """
        return max(0.0, self._last_tick_time + self._tick_dt - time.monotonic())

    def ticks_for_seconds(self, seconds: float) -> int:
        """Convert a duration in seconds to an equivalent number of ticks.

        Parameters
        ----------
        seconds : float
            The duration to convert.

        Returns
        -------
        int
            The number of ticks corresponding to `seconds`, rounded to the
            nearest tick and clamped to a minimum of 1.
        """
        return max(1, round(seconds / self._tick_dt))

    def elapsed_since(self, tick: TickNumber) -> int:
        """Compute how many ticks have elapsed since a given tick.

        Parameters
        ----------
        tick : TickNumber
            The reference tick to measure from.

        Returns
        -------
        int
            The number of ticks that have passed since `tick`.
        """
        return self._tick - tick
