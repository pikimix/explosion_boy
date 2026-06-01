"""Per-player input queue consumed by the server each tick."""
from __future__ import annotations

from collections import deque

from core.components import PlayerInput, neutral_input
from core.tick import TickNumber


class InputBuffer:
    def __init__(self) -> None:
        self._queues: dict[int, deque[PlayerInput]] = {}

    def register_player(self, player_id: int) -> None:
        self._queues[player_id] = deque()

    def unregister_player(self, player_id: int) -> None:
        self._queues.pop(player_id, None)

    def push(self, inp: PlayerInput) -> None:
        queue = self._queues.get(inp.player_id)
        if queue is not None:
            queue.append(inp)

    def drain(self, tick: TickNumber) -> list[PlayerInput]:
        """Return one input per registered player for this tick.

        Discards any inputs older than `tick` before looking for an exact
        match. Falls back to a neutral input if nothing is queued for this tick.
        """
        result: list[PlayerInput] = []
        for pid, queue in self._queues.items():
            while queue and queue[0].tick < tick:
                queue.popleft()
            if queue and queue[0].tick == tick:
                result.append(queue.popleft())
            else:
                result.append(neutral_input(pid, tick))
        return result
