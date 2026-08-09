"""Shared player-removal helper used by the explosion and shrink systems."""
from __future__ import annotations

from core.state import GameState
from systems.event_bus import EventBus, PlayerDiedEvent


def kill_players(state: GameState, bus: EventBus, pids: list[int]) -> None:
    """Remove each player from state, then emit a PlayerDiedEvent per pid.

    Removal happens for every pid before any event is emitted, so a
    PlayerDiedEvent handler never sees a stale entry for another player
    being killed in the same batch.
    """
    for pid in pids:
        state.players.pop(pid, None)
        state.player_physics.pop(pid, None)
    for pid in pids:
        bus.emit(PlayerDiedEvent(pid, state.tick))
