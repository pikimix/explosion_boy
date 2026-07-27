"""
Authoritative game server. Headless — never imports arcade or assets.

Run via: python run_server.py
"""
from __future__ import annotations

import time
from datetime import datetime
from uuid import UUID

from core.clock import TickClock
from core.components import GamePhase, PlayerInput
from core.serialiser import decode_state, encode_state
from core.state import GameState
from core.tick import TickNumber
from net.lobby import LobbyManager
from net.protocol import (
    ColourMsg,
    GameOverMsg,
    GameStartMsg,
    InputMsg,
    JoinMsg,
    PROTOCOL_VERSION,
    ReadyMsg,
    RejectMsg,
    RenameMsg,
    StateUpdateMsg,
    decode_any,
)
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
from systems.shrink_system import process_perimeter_shrink


def _ts() -> str:
    return datetime.now().strftime('%H:%M:%S.%f')[:-3]


class GameServer:
    """Authoritative headless game server owning simulation, networking, and rollback."""

    def __init__(
        self,
        transport: ServerTransport,
        tick_rate: int = 60,
        rollback_buffer_size: int = 120,
        debug: bool = False,
        profile: bool = False,
    ) -> None:
        self._transport = transport
        self._debug = debug
        self._profile = profile
        self._profile_tick_count = 0
        self._profile_total_ms = 0.0
        self._profile_detonation_ms = 0.0
        self._profile_encode_ms = 0.0
        self._profile_max_tick_ms = 0.0
        self._tick_rate = tick_rate
        self._tick_dt = 1.0 / tick_rate
        self._rollback_buffer_size = rollback_buffer_size
        self._clock = TickClock(tick_rate)
        self._state: GameState | None = None
        self._space: PhysicsSpace | None = None
        self._input_buffer = InputBuffer()
        self._bus = EventBus()
        self._lobby = LobbyManager(transport, tick_rate)
        self._peer_to_player: dict[UUID, int] = {}
        self._player_names: dict[int, str] = {}

        # Rollback state
        self._snapshots: dict[TickNumber, bytes] = {}
        self._input_log: dict[TickNumber, list[PlayerInput]] = {}

        self._last_alive_pids: set[int] = set()
        self._last_2_spawn_tick: int = 0
        self._initial_soft_blocks: int = 0
        self._last_player_physics: dict = {}
        self._last_player_colours: dict = {}

        self._bus.subscribe(PlayerDiedEvent, self._on_player_died)

    def run(self) -> None:
        """Run the main server loop, polling the transport and ticking the game forever."""
        print(f"[{_ts()}] Server running at {self._tick_rate} tps "
              f"(rollback window: {self._rollback_buffer_size} ticks). Waiting for players…")
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
            if msg.version != PROTOCOL_VERSION:
                self._transport.send(
                    peer_id,
                    RejectMsg(
                        reason=f"Protocol version mismatch: client={msg.version}, server={PROTOCOL_VERSION}"
                    ).encode(),
                    CHANNEL_RELIABLE,
                )
                self._transport.disconnect(peer_id)
                print(f"[{_ts()}] Rejected peer {peer_id}: version {msg.version} != {PROTOCOL_VERSION}")
                return
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
            self._lobby.on_colour(peer_id, msg.colour)

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
                if pid is None:
                    return
                inp = PlayerInput(
                    player_id=pid, tick=msg.tick,
                    move_x=msg.move_x, move_y=msg.move_y,
                    place_bomb=msg.place_bomb,
                )
                current = self._clock.current_tick
                if inp.tick < current:
                    # Late input — replay from the saved snapshot if within window
                    late_by = current - inp.tick
                    if late_by <= self._rollback_buffer_size:
                        self._replay_from(inp.tick, inp)
                    # else: too old, discard silently
                else:
                    self._input_buffer.push(inp)

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
        self._initial_soft_blocks = sum(
            1 for row in state.tiles for tile in row if tile == 2  # TileKind.SOFT_BLOCK
        )

        space = PhysicsSpace()
        space.rebuild_static_walls(state.tiles)
        for pid, phys in state.player_physics.items():
            space.add_player(pid, phys.x, phys.y)
            self._input_buffer.register_player(pid)
        self._space = space

        self._clock.reset()
        self._snapshots.clear()
        self._input_log.clear()
        self._lobby.broadcast_game_start(state)
        print(f"[{_ts()}] Game started with {len(state.players)} players.")

    # ── Tick ──────────────────────────────────────────────────────────────────

    def _tick(self) -> None:
        assert self._state is not None
        assert self._space is not None

        tick_start = time.perf_counter() if self._profile else 0.0

        self._last_alive_pids = set(self._state.players.keys())
        self._last_player_physics = dict(self._state.player_physics)
        self._last_player_colours = dict(self._state.player_colours)
        tick = self._clock.advance()
        self._state.tick = tick
        inputs = self._input_buffer.drain(tick, debug=self._debug)

        self._input_log[tick] = inputs
        self._run_tick(tick, inputs)

        if self._state is None:
            return

        encode_start = time.perf_counter() if self._profile else 0.0
        state_bytes = encode_state(self._state)
        if self._profile:
            self._profile_encode_ms += (time.perf_counter() - encode_start) * 1000
        self._snapshots[tick] = state_bytes

        # Evict entries outside the rollback window
        evict = tick - self._rollback_buffer_size
        self._snapshots.pop(evict, None)
        self._input_log.pop(evict, None)

        self._transport.broadcast(
            StateUpdateMsg(tick=tick, state_bytes=state_bytes).encode(),
            CHANNEL_UNRELIABLE,
        )

        if self._profile:
            self._record_profile_sample(tick_start)

    def _record_profile_sample(self, tick_start: float) -> None:
        """Accumulate per-tick timing and print a summary roughly once a second."""
        tick_ms = (time.perf_counter() - tick_start) * 1000
        self._profile_tick_count += 1
        self._profile_total_ms += tick_ms
        self._profile_max_tick_ms = max(self._profile_max_tick_ms, tick_ms)

        if self._profile_tick_count < self._tick_rate:
            return

        assert self._state is not None
        n = self._profile_tick_count
        print(
            f"[{_ts()}] [profile] tick avg={self._profile_total_ms / n:.2f}ms "
            f"max={self._profile_max_tick_ms:.2f}ms "
            f"detonation_avg={self._profile_detonation_ms / n:.2f}ms "
            f"encode_avg={self._profile_encode_ms / n:.2f}ms | "
            f"players={len(self._state.players)} "
            f"bombs={len(self._state.bombs)} "
            f"explosions={len(self._state.explosions)} "
            f"rays={len(self._state.explosion_rays)}"
        )
        self._profile_tick_count = 0
        self._profile_total_ms = 0.0
        self._profile_detonation_ms = 0.0
        self._profile_encode_ms = 0.0
        self._profile_max_tick_ms = 0.0

    def _run_tick(self, tick: int, inputs: list[PlayerInput]) -> None:
        """Execute one tick of game logic with the given inputs.

        Does not advance the clock, save snapshots, or broadcast — the caller
        is responsible for those so this method can be used both for normal
        ticks and for rollback replay.
        """
        if self._state is None or self._space is None:
            return

        self._state.tick = tick
        process_movement(self._state, self._space, inputs, self._tick_dt)
        sync_grid_positions(self._state)
        tick_explosions(self._state)
        apply_new_bombs(self._state, self._space, inputs)
        sync_pushed_bombs(self._state, self._space)
        detonations = process_fuses(self._state)
        det_start = time.perf_counter() if self._profile else 0.0
        process_detonations(self._state, self._space, detonations, self._bus)
        if self._profile:
            self._profile_detonation_ms += (time.perf_counter() - det_start) * 1000
        if self._state is None:
            return
        process_powerup_pickups(self._state)
        tick_status_effects(self._state)
        process_perimeter_shrink(self._state, self._space, self._bus)
        self._maybe_spawn_last_2_powerup(tick)
        self._check_win_condition()

        if self._state is None:
            return
        self._state.player_names = dict(self._player_names)

    # ── Rollback ──────────────────────────────────────────────────────────────

    def _replay_from(self, rollback_tick: TickNumber, late_inp: PlayerInput) -> None:
        """Restore state from snapshot at rollback_tick-1 and re-simulate forward."""
        prev_snap = self._snapshots.get(rollback_tick - 1)
        if prev_snap is None:
            if self._debug:
                print(f"[{_ts()}] Rollback: no snapshot for tick {rollback_tick - 1}, discarding late input")
            return

        current_tick = self._clock.current_tick
        if self._debug:
            print(f"[{_ts()}] Rollback: replaying ticks {rollback_tick}..{current_tick} "
                  f"(late input from player {late_inp.player_id})")

        self._state = decode_state(prev_snap)
        self._space = self._rebuild_space_from_state(self._state)

        for t in range(rollback_tick, current_tick + 1):
            inputs = list(self._input_log.get(t, []))
            if t == rollback_tick:
                # Inject the late input, replacing the neutral that ran originally
                inputs = [
                    late_inp if p.player_id == late_inp.player_id else p
                    for p in inputs
                ]
                if not any(p.player_id == late_inp.player_id for p in inputs):
                    inputs.append(late_inp)

            self._run_tick(t, inputs)

            if self._state is None:
                break  # game ended during replay

            state_bytes = encode_state(self._state)
            self._snapshots[t] = state_bytes
            self._input_log[t] = inputs

        if self._state is not None:
            self._transport.broadcast(
                StateUpdateMsg(
                    tick=current_tick,
                    state_bytes=self._snapshots[current_tick],
                ).encode(),
                CHANNEL_UNRELIABLE,
            )

    def _rebuild_space_from_state(self, state: GameState) -> PhysicsSpace:
        """Create a fresh PhysicsSpace populated from a GameState snapshot."""
        space = PhysicsSpace()
        space.rebuild_static_walls(state.tiles)
        for pid, phys in state.player_physics.items():
            space.add_player(pid, phys.x, phys.y)
        for i, bomb in enumerate(state.bombs):
            space.add_bomb(i, bomb.px, bomb.py)
        return space

    # ── Last-two powerup surge ────────────────────────────────────────────────

    def _maybe_spawn_last_2_powerup(self, tick: int) -> None:
        if self._state is None:
            return
        last_2 = len(self._state.players) == 2
        few_blocks = (
            self._initial_soft_blocks > 0
            and sum(1 for row in self._state.tiles for t in row if t == 2)
               < self._initial_soft_blocks * 0.1
        )
        if not (last_2 or few_blocks):
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
        # Send the final state reliably before GameOverMsg so clients render
        # the killing explosion even when it and the player death occur on the
        # same tick (and the normal unreliable StateUpdateMsg is skipped).
        # Re-add dead players at their last known position so the captured
        # freeze-frame shows them inside the explosion.
        dead_pids = set(self._last_player_physics) - set(self._state.player_physics)
        for pid in dead_pids:
            self._state.player_physics[pid] = self._last_player_physics[pid]
            if pid not in self._state.player_colours and pid in self._last_player_colours:
                self._state.player_colours[pid] = self._last_player_colours[pid]
        self._state.player_names = dict(self._player_names)
        state_bytes = encode_state(self._state)
        self._transport.broadcast(
            StateUpdateMsg(tick=self._state.tick, state_bytes=state_bytes).encode(),
            CHANNEL_RELIABLE,
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
        self._initial_soft_blocks = 0
        self._snapshots.clear()
        self._input_log.clear()
        self._lobby.reset()
        print(f"[{_ts()}] Server reset. Waiting for players…")
