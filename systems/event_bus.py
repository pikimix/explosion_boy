"""Synchronous pub/sub within a single process."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class PlayerDiedEvent:
    """Emitted when a player dies."""
    player_id: int
    tick: int

@dataclass(frozen=True)
class BombPlacedEvent:
    """Emitted when a bomb is placed on the grid."""
    player_id: int
    col: int
    row: int

@dataclass(frozen=True)
class BombDetonatedEvent:
    """Emitted when a bomb detonates."""
    col: int
    row: int

@dataclass(frozen=True)
class SoftBlockDestroyedEvent:
    """Emitted when a soft block is destroyed by an explosion."""
    col: int
    row: int

@dataclass(frozen=True)
class PowerupPickedUpEvent:
    """Emitted when a player picks up a powerup."""
    player_id: int
    col: int
    row: int


AnyEvent = (PlayerDiedEvent | BombPlacedEvent | BombDetonatedEvent
            | SoftBlockDestroyedEvent | PowerupPickedUpEvent)


class EventBus:
    """Synchronous publish/subscribe registry for in-process event dispatch."""

    def __init__(self) -> None:
        self._handlers: dict[type, list[Callable]] = defaultdict(list)

    def subscribe(self, event_type: type, handler: Callable) -> None:
        """Register a handler to be called whenever an event of this type is emitted.

        Parameters
        ----------
        event_type : type
            The event dataclass type to listen for.
        handler : Callable
            Callable invoked with the event instance when it is emitted.
        """
        self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: type, handler: Callable) -> None:
        """Remove a previously registered handler for the given event type.

        Parameters
        ----------
        event_type : type
            The event dataclass type the handler was registered for.
        handler : Callable
            The handler instance to remove.
        """
        self._handlers[event_type].remove(handler)

    def emit(self, event: AnyEvent) -> None:
        """Dispatch an event to all handlers registered for its type.

        Parameters
        ----------
        event : AnyEvent
            The event instance to dispatch to subscribers.
        """
        for handler in self._handlers[type(event)]:
            handler(event)
