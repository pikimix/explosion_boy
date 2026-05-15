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
import time
from collections import deque
from typing import Callable

from core.state import GameState
from net.protocol import (
    AnyMsg,
    GameOverMsg,
    GameStartMsg,
    InputMsg,
    JoinMsg,
    LobbyUpdateMsg,
    ReadyMsg,
    StateUpdateMsg,
    WelcomeMsg,
    decode_any,
)
from engine.transport import CHANNEL_RELIABLE, CHANNEL_UNRELIABLE, ClientTransport


class GameClient:
    def __init__(self, transport: ClientTransport) -> None:
        self._transport = transport
        self._player_id: int | None = None
        self._last_state: GameState | None = None
        self._last_state_tick: int = -1
        self._lock = threading.Lock()
        self._pending_inputs: deque[InputMsg] = deque()
        self._message_queue: deque[AnyMsg] = deque()
        self._running = True
        self._thread = threading.Thread(target=self._net_loop, daemon=True)
        self._thread.start()

    # ── Main-thread API ───────────────────────────────────────────────────────

    @property
    def player_id(self) -> int | None:
        return self._player_id

    @property
    def connected(self) -> bool:
        return self._transport.connected

    def get_state(self) -> GameState | None:
        with self._lock:
            return self._last_state

    def queue_input(self, inp: InputMsg) -> None:
        self._pending_inputs.append(inp)

    def send_join(self, name: str) -> None:
        self._transport.send(JoinMsg(player_name=name).encode(), CHANNEL_RELIABLE)

    def send_ready(self) -> None:
        self._transport.send(ReadyMsg().encode(), CHANNEL_RELIABLE)

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
        while self._running:
            events = self._transport.poll()
            for event in events:
                from engine.transport import ReceiveEvent, DisconnectEvent
                if isinstance(event, ReceiveEvent):
                    self._handle_data(event.data)
                elif isinstance(event, DisconnectEvent):
                    self._running = False

            # Drain and send pending inputs
            while self._pending_inputs:
                inp = self._pending_inputs.popleft()
                self._transport.send(inp.encode(), CHANNEL_RELIABLE)

            time.sleep(0.001)

    def _handle_data(self, data: bytes) -> None:
        msg = decode_any(data)
        if msg is None:
            return

        if isinstance(msg, WelcomeMsg):
            self._player_id = msg.assigned_player_id

        elif isinstance(msg, StateUpdateMsg):
            # Only update if this snapshot is newer than what we have
            if msg.tick > self._last_state_tick:
                state = msg.get_state()
                with self._lock:
                    self._last_state = state
                    self._last_state_tick = msg.tick

        elif isinstance(msg, (GameStartMsg, LobbyUpdateMsg, GameOverMsg)):
            self._message_queue.append(msg)
            if isinstance(msg, GameStartMsg):
                state = msg.get_state()
                with self._lock:
                    self._last_state = state
                    self._last_state_tick = state.tick
