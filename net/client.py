"""
Client network thread. Runs alongside arcade's main thread.

The arcade main thread:
  - Reads last_state (under lock) to render.
  - Calls queue_input() to send inputs.
  - Calls poll_messages() to consume non-state messages (lobby, game_over, etc.).

The net thread:
  - Calls transport.poll() every loop iteration.
  - Writes received state to last_state (under lock).
  - Sends queued inputs from pending_inputs.
"""
from __future__ import annotations

import threading
from collections import deque

from core.state import GameState
from net.protocol import (
    AnyMsg,
    ColourMsg,
    GameOverMsg,
    GameStartMsg,
    InputMsg,
    JoinMsg,
    LobbyUpdateMsg,
    ReadyMsg,
    RejectMsg,
    RenameMsg,
    StateUpdateMsg,
    WelcomeMsg,
    decode_any,
)
from engine.transport import CHANNEL_RELIABLE, ClientTransport


_RECONNECT_DELAYS = [2.0, 4.0, 8.0, 16.0, 30.0]


class GameClient:
    """Own the connection to the game server and bridge it to the main thread.

    Instances spawn a background network thread on construction that owns
    the ``ClientTransport`` and exchanges messages with the server. The
    main (arcade) thread interacts with this class only through its
    thread-safe "Main-thread API" methods below (``get_state``,
    ``queue_input``, ``poll_messages``, the ``send_*`` methods, and the
    read-only properties); it must never touch the transport directly.
    """

    def __init__(self, transport: ClientTransport) -> None:
        self._transport = transport
        self._player_id: int | None = None
        self._tick_rate: int = 60
        self._player_name: str = ""
        self._last_state: GameState | None = None
        self._last_state_tick: int = -1
        self._lock = threading.Lock()
        self._pending_inputs: deque[InputMsg] = deque()
        self._message_queue: deque[AnyMsg] = deque()
        self._running = True
        self._reconnecting = False
        self._reject_reason: str | None = None
        self._thread = threading.Thread(target=self._net_loop, daemon=True)
        self._thread.start()

    # ── Main-thread API ───────────────────────────────────────────────────────

    @property
    def player_id(self) -> int | None:
        """Return the player id assigned by the server, or None before welcome."""
        return self._player_id

    @property
    def tick_rate(self) -> int:
        """Return the server's simulation tick rate in ticks per second."""
        return self._tick_rate

    @property
    def connected(self) -> bool:
        """Return whether the underlying transport currently has a live connection."""
        return self._transport.connected

    @property
    def reconnecting(self) -> bool:
        """Return whether the net thread is currently attempting to reconnect."""
        return self._reconnecting

    @property
    def reject_reason(self) -> str | None:
        """Return the reason the server rejected this client, or None if not rejected."""
        return self._reject_reason

    def get_state(self) -> GameState | None:
        """Return the most recently received game state snapshot.

        Reads ``last_state`` under the lock shared with the net thread, so
        it is safe to call from the main thread while the net thread is
        writing a newer snapshot.

        Returns
        -------
        GameState or None
            The latest decoded state, or None if no snapshot has been
            received yet.
        """
        with self._lock:
            return self._last_state

    def queue_input(self, inp: InputMsg) -> None:
        """Queue a player input to be sent to the server by the net thread.

        Parameters
        ----------
        inp : InputMsg
            The input message to enqueue for sending.
        """
        self._pending_inputs.append(inp)

    def send_join(self, name: str) -> None:
        """Record the player's name and send a join request to the server.

        Parameters
        ----------
        name : str
            The name the player wishes to join the game with.
        """
        self._player_name = name
        self._transport.send(JoinMsg(player_name=name).encode(), CHANNEL_RELIABLE)

    def send_ready(self, ready: bool) -> None:
        """Notify the server of this player's ready state in the lobby.

        Parameters
        ----------
        ready : bool
            True if the player is ready to start, False otherwise.
        """
        self._transport.send(ReadyMsg(ready=ready).encode(), CHANNEL_RELIABLE)

    def send_colour(self, colour_rgb: tuple[int, int, int]) -> None:
        """Send the player's chosen colour to the server.

        Parameters
        ----------
        colour_rgb : tuple[int, int, int]
            The chosen colour as an (R, G, B) tuple.
        """
        self._transport.send(ColourMsg(colour_rgb=colour_rgb).encode(), CHANNEL_RELIABLE)

    def send_rename(self, new_name: str) -> None:
        """Record the player's new name and send a rename request to the server.

        Parameters
        ----------
        new_name : str
            The new name the player wishes to use.
        """
        self._player_name = new_name
        self._transport.send(RenameMsg(new_name=new_name).encode(), CHANNEL_RELIABLE)

    def poll_messages(self) -> list[AnyMsg]:
        """Drain and return all non-state messages received since the last poll.

        Intended to be called once per frame from the main thread to pick
        up lobby, game-over, and other discrete events queued by the net
        thread (state updates are consumed separately via ``get_state``).

        Returns
        -------
        list[AnyMsg]
            The messages received since the previous call, in arrival order.
        """
        msgs: list[AnyMsg] = []
        while self._message_queue:
            msgs.append(self._message_queue.popleft())
        return msgs

    def stop(self) -> None:
        """Signal the net thread to stop and disconnect the transport."""
        self._running = False
        self._transport.disconnect()

    # ── Net thread ────────────────────────────────────────────────────────────

    def _net_loop(self) -> None:
        import time
        from engine.transport import ConnectEvent, ReceiveEvent, DisconnectEvent
        _attempt = 0
        _reconnect_at: float | None = None

        while self._running:
            now = time.monotonic()

            # Fire a pending reconnect attempt when the delay has elapsed
            if self._reconnecting and _reconnect_at is not None and now >= _reconnect_at:
                _reconnect_at = None
                self._transport.reconnect()

            events = self._transport.poll(timeout=0.05)

            # Scan for the newest snapshot without decoding all of them
            latest_state_msg: StateUpdateMsg | None = None
            for event in events:
                if isinstance(event, ConnectEvent):
                    # Fresh connection (or successful reconnect)
                    self._reconnecting = False
                    _attempt = 0
                    _reconnect_at = None
                    if self._player_name:
                        self._transport.send(
                            JoinMsg(player_name=self._player_name).encode(),
                            CHANNEL_RELIABLE,
                        )
                elif isinstance(event, ReceiveEvent):
                    msg = decode_any(event.data)
                    if msg is None:
                        continue
                    if isinstance(msg, StateUpdateMsg):
                        if msg.tick > self._last_state_tick and (
                                latest_state_msg is None or msg.tick > latest_state_msg.tick):
                            latest_state_msg = msg
                    else:
                        self._handle_msg(msg)
                elif isinstance(event, DisconnectEvent):
                    if not self._reconnecting:
                        self._reconnecting = True
                        self._player_id = None
                        self._pending_inputs.clear()
                    delay = _RECONNECT_DELAYS[min(_attempt, len(_RECONNECT_DELAYS) - 1)]
                    _reconnect_at = time.monotonic() + delay
                    _attempt += 1

            # Decode only the latest snapshot (one msgpack unpack instead of N)
            if latest_state_msg is not None:
                state = latest_state_msg.get_state()
                with self._lock:
                    self._last_state = state
                    self._last_state_tick = latest_state_msg.tick

            # Drain and send pending inputs (skip while reconnecting)
            if not self._reconnecting:
                while self._pending_inputs:
                    inp = self._pending_inputs.popleft()
                    self._transport.send(inp.encode(), CHANNEL_RELIABLE)

    def _handle_msg(self, msg: AnyMsg) -> None:
        if isinstance(msg, RejectMsg):
            self._reject_reason = msg.reason
            self._running = False
        elif isinstance(msg, WelcomeMsg):
            self._player_id = msg.assigned_player_id
            self._tick_rate = msg.tick_rate
        elif isinstance(msg, (GameStartMsg, LobbyUpdateMsg, GameOverMsg)):
            if isinstance(msg, GameStartMsg):
                state = msg.get_state()
                with self._lock:
                    self._last_state = state
                    self._last_state_tick = state.tick
            self._message_queue.append(msg)
