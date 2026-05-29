"""Server-side lobby: join/ready handshake and game-start trigger."""
from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from core.components import GamePhase, PlayerStats, PhysicsState
from core.serialiser import encode_state
from core.state import GameState
from net.protocol import (
    GameStartMsg,
    LobbyUpdateMsg,
    WelcomeMsg,
)
from engine.config import MAX_PLAYERS, SPAWN_POINTS
from engine.transport import CHANNEL_RELIABLE, ServerTransport
from systems.world import generate_map, spawn_position_px


@dataclass
class _LobbyPlayer:
    peer_id: UUID
    player_id: int
    name: str
    ready: bool = False


class LobbyManager:
    def __init__(self, transport: ServerTransport) -> None:
        self._transport = transport
        self._players: dict[UUID, _LobbyPlayer] = {}

    # ── Incoming message handlers ─────────────────────────────────────────────

    def on_join(self, peer_id: UUID, name: str) -> None:
        if peer_id in self._players or len(self._players) >= MAX_PLAYERS:
            return
        used = {p.player_id for p in self._players.values()}
        pid = next(i for i in range(MAX_PLAYERS) if i not in used)
        self._players[peer_id] = _LobbyPlayer(peer_id, pid, name)
        self._transport.send(
            peer_id,
            WelcomeMsg(assigned_player_id=pid).encode(),
            CHANNEL_RELIABLE,
        )
        self._broadcast_lobby()

    def on_ready(self, peer_id: UUID, ready: bool) -> None:
        if player := self._players.get(peer_id):
            player.ready = ready
            self._broadcast_lobby()

    def on_disconnect(self, peer_id: UUID) -> None:
        self._players.pop(peer_id, None)
        self._broadcast_lobby()

    def reset(self) -> None:
        self._players.clear()

    # ── State check ───────────────────────────────────────────────────────────

    def should_start(self) -> bool:
        return (
            len(self._players) >= 2
            and all(p.ready for p in self._players.values())
        )

    def build_initial_state(self, seed: int | None = None) -> GameState:
        n = len(self._players)
        tiles = generate_map(num_players=n, seed=seed)
        state = GameState(
            tick=0,
            map_cols=len(tiles[0]),
            map_rows=len(tiles),
            tiles=tiles,
            phase=GamePhase.PLAYING,
        )
        for lp in self._players.values():
            state.players[lp.player_id] = PlayerStats(player_id=lp.player_id)
            px, py = spawn_position_px(lp.player_id)
            state.player_physics[lp.player_id] = PhysicsState(px, py)
        return state

    def broadcast_game_start(self, state: GameState) -> None:
        state_bytes = encode_state(state)
        msg = GameStartMsg(state_bytes=state_bytes).encode()
        self._transport.broadcast(msg, CHANNEL_RELIABLE)

    def peer_to_player_id(self, peer_id: UUID) -> int | None:
        if lp := self._players.get(peer_id):
            return lp.player_id
        return None

    def player_name(self, player_id: int) -> str:
        for lp in self._players.values():
            if lp.player_id == player_id:
                return lp.name
        return f"Player {player_id}"

    # ── Internal ──────────────────────────────────────────────────────────────

    def _broadcast_lobby(self) -> None:
        players_list = [
            {"id": lp.player_id, "name": lp.name, "ready": lp.ready}
            for lp in self._players.values()
        ]
        msg = LobbyUpdateMsg(players=players_list).encode()
        self._transport.broadcast(msg, CHANNEL_RELIABLE)
