"""Tests for GameServer's connection handling."""

import random
from uuid import uuid4

from core.components import Cell, GamePhase, PlayerInput, TileKind
from core.state import GameState
from engine.physics import PhysicsSpace
from net.protocol import JoinMsg, PROTOCOL_VERSION, RejectMsg, decode_any
from net.server import GameServer


def test_join_with_mismatched_protocol_version_is_rejected(fake_server_transport):
    """A client whose protocol version doesn't match the server's is sent a
    RejectMsg and disconnected, without being admitted to the lobby."""
    transport = fake_server_transport
    server = GameServer(transport)
    peer_id = uuid4()

    server._on_receive(peer_id, JoinMsg(player_name="p1", version=PROTOCOL_VERSION - 1).encode())

    assert peer_id in transport.disconnected
    assert len(transport.sent) == 1
    sent_peer, data, _channel = transport.sent[0]
    assert sent_peer == peer_id
    msg = decode_any(data)
    assert isinstance(msg, RejectMsg)
    assert str(PROTOCOL_VERSION - 1) in msg.reason
    assert str(PROTOCOL_VERSION) in msg.reason
    assert server._lobby.peer_to_player_id(peer_id) is None


def test_join_with_matching_protocol_version_is_accepted(fake_server_transport):
    """A client whose protocol version matches the server's joins the lobby
    and is not disconnected or rejected."""
    transport = fake_server_transport
    server = GameServer(transport)
    peer_id = uuid4()

    server._on_receive(peer_id, JoinMsg(player_name="p1", version=PROTOCOL_VERSION).encode())

    assert peer_id not in transport.disconnected
    assert server._lobby.peer_to_player_id(peer_id) is not None
    assert not any(isinstance(decode_any(data), RejectMsg) for _peer, data, _ch in transport.sent)


def test_rebuild_space_from_state_reuses_space_when_tiles_unchanged(fake_server_transport):
    """Regression: _replay_from (the rollback path, triggered by every
    late/reordered input packet) used to call _rebuild_space_from_state,
    which built a brand-new PhysicsSpace and rebuilt every static wall shape
    from scratch every time — a major CPU hotspot found via py-spy profiling
    that stalled input processing under live load. A rollback replaying
    against an unchanged tile grid must reuse the same space and the same
    wall shape objects rather than rebuilding them."""
    server = GameServer(fake_server_transport)
    tiles = [[TileKind.EMPTY, TileKind.SOLID_WALL], [TileKind.EMPTY, TileKind.EMPTY]]
    state = GameState(tick=0, map_cols=2, map_rows=2, tiles=tiles)

    space1 = server._rebuild_space_from_state(state)
    server._space = space1
    wall_shape = space1._static_shapes[Cell(1, 0)]

    state2 = GameState(tick=1, map_cols=2, map_rows=2, tiles=[row[:] for row in tiles])
    space2 = server._rebuild_space_from_state(state2)

    assert space2 is space1
    assert space2._static_shapes[Cell(1, 0)] is wall_shape


def test_replay_restores_rng_state_so_replayed_tick_draws_match_original(
    fake_server_transport, monkeypatch
):
    """Regression: a rollback replay used to re-run a tick's game logic
    against whatever cursor position Python's shared `random` module
    happened to be at by the time the replay fired — not the cursor position
    that tick actually saw live. This let random-chance outcomes (e.g. a
    powerup drop roll on soft-block destruction) diverge between the live
    broadcast and the replayed broadcast, silently un-spawning a powerup the
    client had already seen with no pickup ever occurring. Restoring the RNG
    state captured entering each tick before replaying it must make every
    replayed tick draw identically to the original."""
    server = GameServer(fake_server_transport)
    server._state = GameState(
        tick=0, map_cols=1, map_rows=1, tiles=[[TileKind.EMPTY]], phase=GamePhase.PLAYING
    )
    server._space = PhysicsSpace()
    server._space.rebuild_static_walls(server._state.tiles)
    server._clock.reset()

    draws: list[tuple] = []

    def fake_run_tick(tick, inputs):
        draws.append((tick, random.random()))

    monkeypatch.setattr(server, "_run_tick", fake_run_tick)

    random.seed(12345)
    for _ in range(5):
        server._tick()

    assert [t for t, _ in draws] == [1, 2, 3, 4, 5]
    original = dict(draws)

    late_inp = PlayerInput(player_id=0, tick=3, move_x=0.0, move_y=0.0, place_bomb=False)
    server._replay_from(3, late_inp)

    replayed = draws[5:]
    assert [t for t, _ in replayed] == [3, 4, 5]
    for tick, value in replayed:
        assert value == original[tick]
