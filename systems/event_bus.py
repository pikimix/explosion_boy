"""Synchronous pub/sub within a single process."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class PlayerDiedEvent:
    player_id: int
    tick: int

@dataclass(frozen=True)
class BombPlacedEvent:
    player_id: int
    col: int
    row: int

@dataclass(frozen=True)
class BombDetonatedEvent:
    col: int
    row: int

@dataclass(frozen=True)
class SoftBlockDestroyedEvent:
    col: int
    row: int

@dataclass(frozen=True)
class PowerupPickedUpEvent:
    player_id: int
    col: int
    row: int


AnyEvent = (PlayerDiedEvent | BombPlacedEvent | BombDetonatedEvent
            | SoftBlockDestroyedEvent | PowerupPickedUpEvent)


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[type, list[Callable]] = defaultdict(list)

    def subscribe(self, event_type: type, handler: Callable) -> None:
        self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: type, handler: Callable) -> None:
        self._handlers[event_type].remove(handler)

    def emit(self, event: AnyEvent) -> None:
        for handler in self._handlers[type(event)]:
            handler(event)
