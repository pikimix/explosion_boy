"""Server-side lobby: join/ready handshake and game-start trigger."""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from core.components import GamePhase, PlayerStats, PhysicsState
from core.serialiser import encode_state
from core.state import GameState
from net.protocol import (
    GameStartMsg,
    LobbyUpdateMsg,
    WelcomeMsg,
)
from engine.config import MAX_PLAYERS, PLAYER_COLOURS
from engine.transport import CHANNEL_RELIABLE, ServerTransport
from systems.world import (
    generate_map,
    map_size_for_player_count,
    spawn_points_for_grid,
    spawn_position_px,
)


@dataclass
class _LobbyPlayer:
    peer_id: UUID
    player_id: int
    name: str
    ready: bool = False
    colour_rgb: tuple[int, int, int] = (220, 50, 50)


class LobbyManager:
    """Manage connected peers in the pre-game lobby.

    Tracks each connected player's identity, name, colour and ready
    state, broadcasts lobby updates to all peers, and builds the
    initial `GameState` once every player is ready and the game can
    start.
    """

    def __init__(self, transport: ServerTransport, tick_rate: int = 60) -> None:
        self._transport = transport
        self._tick_rate = tick_rate
        self._players: dict[UUID, _LobbyPlayer] = {}

    # ── Incoming message handlers ─────────────────────────────────────────────

    def on_join(self, peer_id: UUID, name: str) -> None:
        """Register a newly connected peer as a lobby player.

        Ignores the request if the peer is already known or the lobby
        is full. Otherwise assigns the peer the lowest free player id,
        sends it a `WelcomeMsg` with that id and the server tick rate,
        and broadcasts the updated lobby state to every peer.

        Parameters
        ----------
        peer_id : UUID
            Identifier of the connecting peer/transport connection.
        name : str
            Display name requested by the joining player.
        """
        if peer_id in self._players or len(self._players) >= MAX_PLAYERS:
            return
        used = {p.player_id for p in self._players.values()}
        pid = next(i for i in range(MAX_PLAYERS) if i not in used)
        initial_colour = PLAYER_COLOURS[pid % len(PLAYER_COLOURS)][:3]
        self._players[peer_id] = _LobbyPlayer(peer_id, pid, name, colour_rgb=initial_colour)
        self._transport.send(
            peer_id,
            WelcomeMsg(assigned_player_id=pid, tick_rate=self._tick_rate).encode(),
            CHANNEL_RELIABLE,
        )
        self._broadcast_lobby()

    def on_ready(self, peer_id: UUID, ready: bool) -> None:
        """Update a player's ready state and broadcast the lobby.

        Parameters
        ----------
        peer_id : UUID
            Identifier of the peer whose ready state changed.
        ready : bool
            New ready state for the player.
        """
        if player := self._players.get(peer_id):
            player.ready = ready
            self._broadcast_lobby()

    def on_colour(self, peer_id: UUID, colour_rgb: tuple[int, int, int]) -> None:
        """Update a player's chosen colour and broadcast the lobby.

        Parameters
        ----------
        peer_id : UUID
            Identifier of the peer whose colour changed.
        colour_rgb : tuple[int, int, int]
            New colour as an (r, g, b) tuple.
        """
        if player := self._players.get(peer_id):
            player.colour_rgb = colour_rgb
            self._broadcast_lobby()

    def on_rename(self, peer_id: UUID, new_name: str) -> None:
        """Update a player's display name and broadcast the lobby.

        The requested name is stripped of surrounding whitespace and
        truncated to 16 characters; if nothing is left after
        stripping, the rename is ignored and no broadcast is sent.

        Parameters
        ----------
        peer_id : UUID
            Identifier of the peer requesting the rename.
        new_name : str
            Requested new display name.
        """
        if player := self._players.get(peer_id):
            stripped = new_name.strip()[:16]
            if stripped:
                player.name = stripped
                self._broadcast_lobby()

    def on_disconnect(self, peer_id: UUID) -> None:
        """Remove a disconnected peer from the lobby and broadcast the update.

        Parameters
        ----------
        peer_id : UUID
            Identifier of the peer that disconnected.
        """
        self._players.pop(peer_id, None)
        self._broadcast_lobby()

    def reset(self) -> None:
        """Remove all players from the lobby, clearing it for reuse."""
        self._players.clear()

    # ── State check ───────────────────────────────────────────────────────────

    def should_start(self) -> bool:
        """Check whether the game is ready to start.

        Returns
        -------
        bool
            True if at least two players are in the lobby and every
            player has marked themselves ready, False otherwise.
        """
        return (
            len(self._players) >= 2
            and all(p.ready for p in self._players.values())
        )

    def build_initial_state(self, seed: int | None = None) -> GameState:
        """Build the initial `GameState` for a new match from the current lobby.

        Sizes the map for the current player count, generates the tile
        grid with a safety zone carved around each real player's exact
        spawn cell (player ids may be non-contiguous, so the spawn
        points used are looked up per player rather than assumed to be
        the first `n`), and populates per-player stats, physics state,
        names and colours.

        Parameters
        ----------
        seed : int or None, optional
            Random seed to use for map generation. If None, a random
            seed is used (default None).

        Returns
        -------
        GameState
            Freshly constructed game state ready for the match to begin.
        """
        n = len(self._players)
        cols, rows = map_size_for_player_count(n)
        spawn_points = spawn_points_for_grid(cols, rows)
        # Player ids aren't guaranteed to be a contiguous 0..n-1 range (a player
        # can leave mid-lobby and free up a lower id without every higher id
        # being reassigned), so the safety zone must be carved around the exact
        # spawn cells real players will use — not just spawn_points[:n] — or a
        # player at a higher id could spawn with no safe zone around them.
        active_spawns = [spawn_points[lp.player_id] for lp in self._players.values()]
        tiles = generate_map(
            cols=cols, rows=rows, num_players=n, seed=seed,
            spawn_points=spawn_points, active_spawns=active_spawns,
        )
        state = GameState(
            tick=0,
            map_cols=len(tiles[0]),
            map_rows=len(tiles),
            tiles=tiles,
            phase=GamePhase.PLAYING,
            starting_player_count=n,
        )
        for lp in self._players.values():
            state.players[lp.player_id] = PlayerStats(player_id=lp.player_id)
            px, py = spawn_position_px(lp.player_id, spawn_points)
            state.player_physics[lp.player_id] = PhysicsState(px, py)
            state.player_names[lp.player_id] = lp.name
            state.player_colours[lp.player_id] = lp.colour_rgb
        return state

    def broadcast_game_start(self, state: GameState) -> None:
        """Encode and broadcast the game start message to all peers.

        Parameters
        ----------
        state : GameState
            Initial game state to send, typically produced by
            `build_initial_state`.
        """
        state_bytes = encode_state(state)
        msg = GameStartMsg(state_bytes=state_bytes).encode()
        self._transport.broadcast(msg, CHANNEL_RELIABLE)

    def peer_to_player_id(self, peer_id: UUID) -> int | None:
        """Look up the player id assigned to a connected peer.

        Parameters
        ----------
        peer_id : UUID
            Identifier of the peer to look up.

        Returns
        -------
        int or None
            The peer's assigned player id, or None if the peer is not
            currently in the lobby.
        """
        if lp := self._players.get(peer_id):
            return lp.player_id
        return None

    def player_name(self, player_id: int) -> str:
        """Look up the display name for a player id.

        Parameters
        ----------
        player_id : int
            Player id to look up.

        Returns
        -------
        str
            The player's display name, or a fallback of the form
            "Player {player_id}" if no matching player is found.
        """
        for lp in self._players.values():
            if lp.player_id == player_id:
                return lp.name
        return f"Player {player_id}"

    # ── Internal ──────────────────────────────────────────────────────────────

    def _broadcast_lobby(self) -> None:
        players_list = [
            {"id": lp.player_id, "name": lp.name, "ready": lp.ready,
             "colour_rgb": list(lp.colour_rgb)}
            for lp in self._players.values()
        ]
        msg = LobbyUpdateMsg(players=players_list).encode()
        self._transport.broadcast(msg, CHANNEL_RELIABLE)
