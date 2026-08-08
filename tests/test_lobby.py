"""Tests for LobbyManager's initial game state construction."""

from uuid import uuid4

from core.components import TileKind
from engine.config import MAX_GRID_SIZE, MIN_GRID_SIZE, TILE_SIZE
from net.lobby import LobbyManager, READY_COUNTDOWN_SECONDS
from systems.world import map_size_for_player_count, spawn_points_for_grid


class _FakeTransport:
    def poll(self, timeout: float = 0):
        """Return no pending events, satisfying the transport polling interface."""
        return []

    def send(self, peer_id, data, channel):
        """No-op stub for sending data to a single peer."""

    def broadcast(self, data, channel):
        """No-op stub for broadcasting data to all peers."""

    def disconnect(self, peer_id):
        """No-op stub for disconnecting a peer."""


def _join_n_players(lobby: LobbyManager, n: int) -> None:
    for i in range(n):
        lobby.on_join(uuid4(), f"player{i}")


def test_build_initial_state_sizes_grid_by_player_count():
    """Verify the map grid is sized according to the number of joined players."""
    for n, expected in ((2, (MIN_GRID_SIZE, MIN_GRID_SIZE)), (16, (MAX_GRID_SIZE, MAX_GRID_SIZE))):
        lobby = LobbyManager(_FakeTransport())
        _join_n_players(lobby, n)
        state = lobby.build_initial_state(seed=1)
        assert (state.map_cols, state.map_rows) == expected == map_size_for_player_count(n)
        assert state.starting_player_count == n
        assert len(state.players) == n
        assert len(state.player_physics) == n


def test_build_initial_state_places_every_player_in_bounds():
    """Verify every player's spawn position lies within the map bounds."""
    lobby = LobbyManager(_FakeTransport())
    _join_n_players(lobby, 5)
    state = lobby.build_initial_state(seed=2)
    for phys in state.player_physics.values():
        assert 0 <= phys.x <= state.map_cols * TILE_SIZE
        assert 0 <= phys.y <= state.map_rows * TILE_SIZE


def test_build_initial_state_protects_spawns_with_non_contiguous_player_ids():
    """A player who leaves the lobby frees their id, but a later joiner takes
    the smallest *unused* id — so the round can start with ids like {0, 2, 3}
    for 3 players. The safety zone must follow the real id, not spawn_points[:n]."""
    lobby = LobbyManager(_FakeTransport())
    peers = [uuid4() for _ in range(4)]
    for i, peer in enumerate(peers):
        lobby.on_join(peer, f"player{i}")
    lobby.on_disconnect(peers[1])  # frees id 1; ids now {0, 2, 3}

    state = lobby.build_initial_state(seed=5)
    assert len(state.players) == 3
    assert set(state.players.keys()) == {0, 2, 3}

    cols, rows = map_size_for_player_count(3)
    spawn_points = spawn_points_for_grid(cols, rows)
    for pid in (0, 2, 3):
        col, row = spawn_points[pid].col, spawn_points[pid].row
        for dr in range(-2, 3):
            for dc in range(-2, 3):
                c, r = col + dc, row + dr
                if not (0 <= r < state.map_rows and 0 <= c < state.map_cols):
                    continue
                assert state.tiles[r][c] != TileKind.SOFT_BLOCK


def test_countdown_starts_once_everyone_ready_and_cancels_on_unready():
    """The 5s ready countdown only starts once every player is ready, and
    cancels immediately if anyone un-readies."""
    lobby = LobbyManager(_FakeTransport())
    p1, p2 = uuid4(), uuid4()
    lobby.on_join(p1, "a")
    lobby.on_join(p2, "b")

    lobby.on_ready(p1, True)
    assert lobby.countdown_seconds() is None

    lobby.on_ready(p2, True)
    assert lobby.countdown_seconds() == READY_COUNTDOWN_SECONDS

    lobby.on_ready(p2, False)
    assert lobby.countdown_seconds() is None


def test_countdown_tick_signals_game_start_after_delay():
    """Ticking the countdown for its full duration reports the game should start."""
    lobby = LobbyManager(_FakeTransport())
    p1, p2 = uuid4(), uuid4()
    lobby.on_join(p1, "a")
    lobby.on_join(p2, "b")
    lobby.on_ready(p1, True)
    lobby.on_ready(p2, True)

    started = False
    for _ in range(1000):
        if lobby.tick(0.1):
            started = True
            break
    assert started
    assert lobby.countdown_seconds() is None
