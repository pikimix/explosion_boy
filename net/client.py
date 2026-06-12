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
from typing import Callable

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
    RenameMsg,
    StateUpdateMsg,
    WelcomeMsg,
    decode_any,
)
from engine.transport import CHANNEL_RELIABLE, CHANNEL_UNRELIABLE, ClientTransport


_RECONNECT_DELAYS = [2.0, 4.0, 8.0, 16.0, 30.0]


class GameClient:
    def __init__(self, transport: ClientTransport) -> None:
        self._transport = transport
        self._player_id: int | None = None
        self._player_name: str = ""
        self._last_state: GameState | None = None
        self._last_state_tick: int = -1
        self._lock = threading.Lock()
        self._pending_inputs: deque[InputMsg] = deque()
        self._message_queue: deque[AnyMsg] = deque()
        self._running = True
        self._reconnecting = False
        self._thread = threading.Thread(target=self._net_loop, daemon=True)
        self._thread.start()

    # ── Main-thread API ───────────────────────────────────────────────────────

    @property
    def player_id(self) -> int | None:
        return self._player_id

    @property
    def connected(self) -> bool:
        return self._transport.connected

    @property
    def reconnecting(self) -> bool:
        return self._reconnecting

    def get_state(self) -> GameState | None:
        with self._lock:
            return self._last_state

    def queue_input(self, inp: InputMsg) -> None:
        self._pending_inputs.append(inp)

    def send_join(self, name: str) -> None:
        self._player_name = name
        self._transport.send(JoinMsg(player_name=name).encode(), CHANNEL_RELIABLE)

    def send_ready(self, ready: bool) -> None:
        self._transport.send(ReadyMsg(ready=ready).encode(), CHANNEL_RELIABLE)

    def send_colour(self, colour_rgb: tuple[int, int, int]) -> None:
        self._transport.send(ColourMsg(colour_rgb=colour_rgb).encode(), CHANNEL_RELIABLE)

    def send_rename(self, new_name: str) -> None:
        self._player_name = new_name
        self._transport.send(RenameMsg(new_name=new_name).encode(), CHANNEL_RELIABLE)

    def poll_messages(self) -> list[AnyMsg]:
        msgs: list[AnyMsg] = []
        while self._message_queue:
            msgs.append(self._message_queue.popleft())
        return msgs

    def stop(self) -> None:
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
        if isinstance(msg, WelcomeMsg):
            self._player_id = msg.assigned_player_id
        elif isinstance(msg, (GameStartMsg, LobbyUpdateMsg, GameOverMsg)):
            self._message_queue.append(msg)
            if isinstance(msg, GameStartMsg):
                state = msg.get_state()
                with self._lock:
                    self._last_state = state
                    self._last_state_tick = state.tick
