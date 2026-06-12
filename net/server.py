"""
Authoritative game server. Headless — never imports arcade or assets.

Run via: python run_server.py
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID


def _ts() -> str:
    return datetime.now().strftime('%H:%M:%S.%f')[:-3]

from core.clock import TickClock
from core.components import GamePhase, PlayerInput
from core.serialiser import encode_state
from core.state import GameState
from net.lobby import LobbyManager
from net.protocol import (
    ColourMsg,
    GameOverMsg,
    GameStartMsg,
    InputMsg,
    JoinMsg,
    ReadyMsg,
    RenameMsg,
    StateUpdateMsg,
    decode_any,
)
from engine.config import TICK_RATE
from engine.physics import PhysicsSpace
from engine.transport import (
    CHANNEL_RELIABLE,
    CHANNEL_UNRELIABLE,
    ConnectEvent,
    DisconnectEvent,
    ReceiveEvent,
    ServerTransport,
)
from systems.bomb_system import (
    apply_new_bombs,
    process_fuses,
    sync_pushed_bombs,
)
from systems.collision import sync_grid_positions
from systems.event_bus import EventBus, PlayerDiedEvent
from systems.explosion_system import process_detonations, tick_explosions
from systems.input_buffer import InputBuffer
from systems.movement import process_movement
from systems.powerup_system import (
    process_powerup_pickups,
    spawn_random_powerup,
    tick_status_effects,
    _LAST_2_SPAWN_INTERVAL,
)


class GameServer:
    def __init__(self, transport: ServerTransport, debug: bool = False) -> None:
        self._transport = transport
        self._debug = debug
        self._clock = TickClock()
        self._state: GameState | None = None
        self._space: PhysicsSpace | None = None
        self._input_buffer = InputBuffer()
        self._bus = EventBus()
        self._lobby = LobbyManager(transport)
        self._peer_to_player: dict[UUID, int] = {}
        self._player_names: dict[int, str] = {}

        self._last_alive_pids: set[int] = set()
        self._last_2_spawn_tick: int = 0

        self._bus.subscribe(PlayerDiedEvent, self._on_player_died)

    def run(self) -> None:
        print(f"[{_ts()}] Server running at {TICK_RATE} tps. Waiting for players…")
        while True:
            if self._state is not None and self._state.phase == GamePhase.PLAYING:
                timeout = self._clock.seconds_until_next_tick()
            else:
                timeout = 0.005
            self._poll(timeout)
            if self._state is None or self._state.phase != GamePhase.PLAYING:
                continue
            if self._clock.should_tick():
                self._tick()
                self._poll(0)  # flush broadcast snapshot without blocking

    # ── Poll transport ────────────────────────────────────────────────────────

    def _poll(self, timeout: float = 0) -> None:
        for event in self._transport.poll(timeout):
            if isinstance(event, ConnectEvent):
                pass   # wait for JoinMsg
            elif isinstance(event, DisconnectEvent):
                self._on_disconnect(event.peer_id)
            elif isinstance(event, ReceiveEvent):
                self._on_receive(event.peer_id, event.data)

    def _on_receive(self, peer_id: UUID, data: bytes) -> None:
        msg = decode_any(data)
        if msg is None:
            return

        if isinstance(msg, JoinMsg):
            self._lobby.on_join(peer_id, msg.player_name)
            pid = self._lobby.peer_to_player_id(peer_id)
            if pid is not None:
                self._peer_to_player[peer_id] = pid
                self._player_names[pid] = msg.player_name
            if self._state is not None and self._state.phase == GamePhase.PLAYING:
                # Game already in progress — send current state so client can spectate
                self._transport.send(
                    peer_id,
                    GameStartMsg(state_bytes=encode_state(self._state)).encode(),
                    CHANNEL_RELIABLE,
                )
                print(f"[{_ts()}] {msg.player_name!r} joined as spectator (game in progress).")
            else:
                self._maybe_start_game()

        elif isinstance(msg, ReadyMsg):
            self._lobby.on_ready(peer_id, msg.ready)
            self._maybe_start_game()

        elif isinstance(msg, ColourMsg):
            self._lobby.on_colour(peer_id, msg.colour_rgb)

        elif isinstance(msg, RenameMsg):
            self._lobby.on_rename(peer_id, msg.new_name)
            pid = self._peer_to_player.get(peer_id)
            if pid is not None:
                stripped = msg.new_name.strip()[:16]
                if stripped:
                    self._player_names[pid] = stripped

        elif isinstance(msg, InputMsg):
            if self._state and self._state.phase == GamePhase.PLAYING:
                pid = self._peer_to_player.get(peer_id)
                if pid is not None:
                    self._input_buffer.push(PlayerInput(
                        player_id=pid, tick=msg.tick,
                        move_x=msg.move_x, move_y=msg.move_y,
                        place_bomb=msg.place_bomb,
                    ))

    def _on_disconnect(self, peer_id: UUID) -> None:
        self._lobby.on_disconnect(peer_id)
        pid = self._peer_to_player.pop(peer_id, None)
        if pid is not None and self._state:
            self._state.players.pop(pid, None)
            self._state.player_physics.pop(pid, None)
            if self._space:
                self._space.remove_player(pid)
            self._input_buffer.unregister_player(pid)
            self._check_win_condition()

    # ── Game start ────────────────────────────────────────────────────────────

    def _maybe_start_game(self) -> None:
        if self._state is not None:
            return
        if not self._lobby.should_start():
            return

        state = self._lobby.build_initial_state()
        self._state = state

        space = PhysicsSpace()
        space.rebuild_static_walls(state.tiles)
        for pid, phys in state.player_physics.items():
            space.add_player(pid, phys.x, phys.y)
            self._input_buffer.register_player(pid)
        self._space = space

        self._clock.reset()
        self._lobby.broadcast_game_start(state)
        print(f"[{_ts()}] Game started with {len(state.players)} players.")

    # ── Tick ──────────────────────────────────────────────────────────────────

    def _tick(self) -> None:
        assert self._state is not None
        assert self._space is not None

        self._last_alive_pids = set(self._state.players.keys())
        tick = self._clock.advance()
        self._state.tick = tick
        inputs = self._input_buffer.drain(tick, debug=self._debug)

        process_movement(self._state, self._space, inputs)
        sync_grid_positions(self._state)
        tick_explosions(self._state, self._bus)
        apply_new_bombs(self._state, self._space, inputs)
        sync_pushed_bombs(self._state, self._space)
        detonations = process_fuses(self._state)
        process_detonations(self._state, self._space, detonations, self._bus)
        if self._state is None:
            return
        process_powerup_pickups(self._state)
        tick_status_effects(self._state)
        self._maybe_spawn_last_2_powerup(tick)
        self._check_win_condition()

        if self._state is None:
            return

        self._state.player_names = dict(self._player_names)
        state_bytes = encode_state(self._state)
        self._transport.broadcast(
            StateUpdateMsg(tick=tick, state_bytes=state_bytes).encode(),
            CHANNEL_UNRELIABLE,
        )

    # ── Last-two powerup surge ────────────────────────────────────────────────

    def _maybe_spawn_last_2_powerup(self, tick: int) -> None:
        if self._state is None:
            return
        if len(self._state.players) != 2:
            return
        if tick - self._last_2_spawn_tick >= _LAST_2_SPAWN_INTERVAL:
            spawn_random_powerup(self._state)
            self._last_2_spawn_tick = tick

    # ── Win condition ─────────────────────────────────────────────────────────

    def _on_player_died(self, event: PlayerDiedEvent) -> None:
        self._check_win_condition()

    def _check_win_condition(self) -> None:
        if self._state is None or self._state.phase != GamePhase.PLAYING:
            return
        alive = list(self._state.players.keys())
        if len(alive) > 1:
            return
        winner_id = alive[0] if alive else None
        winner_name = self._player_names.get(winner_id, "") if winner_id is not None else ""
        draw_names = (
            [self._player_names[p] for p in self._last_alive_pids
             if p in self._player_names]
            if winner_id is None else []
        )
        self._transport.broadcast(
            GameOverMsg(winner_id=winner_id, winner_name=winner_name,
                        draw_names=draw_names).encode(),
            CHANNEL_RELIABLE,
        )
        print(f"[{_ts()}] Game over. Winner: {winner_name or 'draw'}")
        self._reset_for_new_game()

    def _reset_for_new_game(self) -> None:
        self._state = None
        self._space = None
        self._input_buffer = InputBuffer()
        self._peer_to_player.clear()
        self._player_names.clear()
        self._last_2_spawn_tick = 0
        self._lobby.reset()
        print(f"[{_ts()}] Server reset. Waiting for players…")
