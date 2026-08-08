"""Server-side lobby: join/ready handshake and game-start trigger."""
from __future__ import annotations

import math
from dataclasses import dataclass
from uuid import UUID

from core.components import Colour, GamePhase, PlayerStats, PhysicsState
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

READY_COUNTDOWN_SECONDS = 5.0


@dataclass
class _LobbyPlayer:
    peer_id: UUID
    player_id: int
    name: str
    ready: bool = False
    colour: Colour = Colour(220, 50, 50)


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
        self._countdown_remaining: float | None = None
        self._last_broadcast_second: int | None = None

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
        initial_colour = Colour(*PLAYER_COLOURS[pid % len(PLAYER_COLOURS)][:3])
        self._players[peer_id] = _LobbyPlayer(peer_id, pid, name, colour=initial_colour)
        self._transport.send(
            peer_id,
            WelcomeMsg(assigned_player_id=pid, tick_rate=self._tick_rate).encode(),
            CHANNEL_RELIABLE,
        )
        self._sync_countdown()

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
            self._sync_countdown()

    def on_colour(self, peer_id: UUID, colour: Colour) -> None:
        """Update a player's chosen colour and broadcast the lobby.

        Parameters
        ----------
        peer_id : UUID
            Identifier of the peer whose colour changed.
        colour : Colour
            The player's newly chosen colour.
        """
        if player := self._players.get(peer_id):
            player.colour = colour
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
        self._sync_countdown()

    def reset(self) -> None:
        """Remove all players from the lobby, clearing it for reuse."""
        self._players.clear()
        self._countdown_remaining = None
        self._last_broadcast_second = None

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

    def countdown_seconds(self) -> int | None:
        """Whole seconds remaining before the game auto-starts, or None if inactive."""
        if self._countdown_remaining is None:
            return None
        return math.ceil(self._countdown_remaining)

    def tick(self, dt: float) -> bool:
        """Advance the ready countdown by `dt` seconds.

        Broadcasts a lobby update whenever the displayed whole-second
        value changes, so clients can render a live countdown.

        Parameters
        ----------
        dt : float
            Time elapsed, in seconds, since the last call.

        Returns
        -------
        bool
            True if the countdown has just elapsed and the game should
            now be started.
        """
        if self._countdown_remaining is None:
            return False
        self._countdown_remaining -= dt
        if self._countdown_remaining <= 0:
            self._countdown_remaining = None
            self._last_broadcast_second = None
            return True
        whole = math.ceil(self._countdown_remaining)
        if whole != self._last_broadcast_second:
            self._last_broadcast_second = whole
            self._broadcast_lobby()
        return False

    def _sync_countdown(self) -> None:
        """Start or cancel the ready countdown to match `should_start()`, then broadcast."""
        if self.should_start():
            if self._countdown_remaining is None:
                self._countdown_remaining = READY_COUNTDOWN_SECONDS
                self._last_broadcast_second = self.countdown_seconds()
        else:
            self._countdown_remaining = None
            self._last_broadcast_second = None
        self._broadcast_lobby()

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
            state.player_colours[lp.player_id] = lp.colour
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
             "colour_rgb": list(lp.colour.as_tuple())}
            for lp in self._players.values()
        ]
        msg = LobbyUpdateMsg(players=players_list, countdown=self.countdown_seconds()).encode()
        self._transport.broadcast(msg, CHANNEL_RELIABLE)
