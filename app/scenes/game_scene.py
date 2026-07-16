"""Active game scene. Bridges arcade 60fps render loop and server tick snapshots."""
from __future__ import annotations

import math
import time

import arcade
from datetime import datetime


def _ts() -> str:
    return datetime.now().strftime('%H:%M:%S.%f')[:-3]

from app.game_view import GameView
from app.sound_system import SoundSystem
from core.components import PlayerInput
from core.state import GameState
from net.client import GameClient
from net.protocol import GameOverMsg, GameStartMsg, InputMsg
from engine.config import MIN_LEAD_TICKS, MAX_LEAD_TICKS, DEFAULT_LEAD_TICKS
from engine import user_prefs
from systems.prediction import PredictionEngine

# EWMA smoothing factor for RTT — matches TCP's default (slow to react, spike-resistant)
_RTT_ALPHA = 0.125


class GameScene:
    def __init__(self, client: GameClient,
                 scene_manager: "SceneManager",  # type: ignore[name-defined]
                 player_name: str = "Player",
                 music_volume: float = 1.0,
                 sfx_volume: float = 1.0,
                 colour_rgb: tuple[int, int, int] = (220, 50, 50),
                 debug: bool = False,
                 start_state: GameState | None = None) -> None:
        self._client = client
        self._scene_manager = scene_manager
        self._player_name = player_name
        self._colour_rgb = colour_rgb
        self._debug = debug
        self._view = GameView()
        self._sounds = SoundSystem(client.player_id, music_volume=music_volume, sfx_volume=sfx_volume)
        self._prev_state: GameState | None = None
        self._last_sound_tick: int = -1
        self._prediction: PredictionEngine | None = None
        self._tick_accum = 0.0
        self._keys: set[int] = set()
        self._pending_game_over: GameOverMsg | None = None

        # RTT measurement — keyed by the tick number we sent the input for
        self._send_times: dict[int, float] = {}
        self._smoothed_rtt: float | None = None

        tick_rate = client.tick_rate
        pid = client.player_id
        state = start_state if start_state is not None else client.get_state()
        current = client.get_state()
        base_tick = current.tick if current else (state.tick if state else 0)
        self._tick = base_tick + DEFAULT_LEAD_TICKS
        if pid is not None:
            self._prediction = PredictionEngine(pid, tick_rate)
            if state:
                self._prediction.reconcile(state)

    @property
    def _lead_ticks(self) -> int:
        """Compute optimal lead from smoothed RTT; fall back to DEFAULT_LEAD_TICKS."""
        if self._smoothed_rtt is None:
            return DEFAULT_LEAD_TICKS
        tick_dt = 1.0 / self._client.tick_rate
        one_way_s = self._smoothed_rtt * 0.5
        return max(MIN_LEAD_TICKS, min(MAX_LEAD_TICKS, math.ceil(one_way_s / tick_dt) + 1))

    def update(self, dt: float) -> None:
        # Check for non-state messages (game over, reconnect, etc.)
        for msg in self._client.poll_messages():
            if isinstance(msg, GameOverMsg):
                self._sounds.stop()
                self._pending_game_over = msg
                return
            elif isinstance(msg, GameStartMsg):
                # Reconnected mid-game — reset tick and prediction for spectator role
                state = self._client.get_state()
                tick_rate = self._client.tick_rate
                self._tick = (state.tick if state else 0) + DEFAULT_LEAD_TICKS
                self._send_times.clear()
                self._smoothed_rtt = None
                pid = self._client.player_id
                self._prediction = PredictionEngine(pid, tick_rate) if pid is not None else None
                if self._prediction and state:
                    self._prediction.reconcile(state)

        # Reconcile prediction with latest server state; trigger sounds on new ticks
        state = self._client.get_state()
        if state and self._prediction:
            self._prediction.reconcile(state)
        if state and state.tick > self._last_sound_tick:
            self._sounds.update(self._prev_state, state)
            self._prev_state = state
            self._last_sound_tick = state.tick

        # Update RTT estimate from confirmed server tick
        if state:
            self._update_rtt(state.tick)

        tick_dt = 1.0 / self._client.tick_rate

        # Guard: if the client tick has fallen behind the server (lead < 1),
        # hard-resync so subsequent inputs land in the server's future.
        if state and (self._tick - state.tick) < 1:
            old_tick = self._tick
            self._tick = state.tick + self._lead_ticks
            if self._debug:
                print(f"[{_ts()}] [client pid={self._client.player_id}] tick resync: {old_tick} → {self._tick} (server={state.tick})")

        # Advance lead tick counter to match target lead; never go backwards
        if state:
            target = state.tick + self._lead_ticks
            if self._tick < target:
                self._tick = target

        self._tick_accum += min(dt, tick_dt)
        while self._tick_accum >= tick_dt:
            self._tick_accum -= tick_dt
            self._tick += 1
            self._send_input(self._tick)
            if self._debug and state:
                lead = self._tick - state.tick
                if lead != 0 and self._tick % 60 == 0:
                    rtt_ms = self._smoothed_rtt * 1000 if self._smoothed_rtt else 0
                    print(f"[{_ts()}] [client pid={self._client.player_id}] "
                          f"client_tick={self._tick} server_tick={state.tick} "
                          f"lead={lead} (target {self._lead_ticks}) rtt={rtt_ms:.1f}ms")

    def draw(self) -> None:
        state = self._client.get_state()
        if state is None:
            return
        pred = self._prediction
        self._view.draw(
            state,
            local_player_id=self._client.player_id,
            predicted_x=pred.predicted_x if pred else None,
            predicted_y=pred.predicted_y if pred else None,
            predicted_vx=pred.predicted_vx if pred else None,
            predicted_vy=pred.predicted_vy if pred else None,
            speed=self._sounds.pitch if self._debug else None,
        )
        if self._client.reconnecting:
            from app.ui.overlay import draw_reconnecting
            draw_reconnecting()
        if self._pending_game_over is not None:
            from app.scenes.game_over_scene import GameOverScene
            msg = self._pending_game_over
            self._pending_game_over = None
            bg_image = arcade.get_image()
            bg_texture = arcade.Texture(bg_image, hash=f'game_over_bg_{id(bg_image)}')
            self._scene_manager.replace(
                GameOverScene(msg, self._scene_manager, self._client, self._player_name,
                              music_volume=self._sounds.music_volume,
                              sfx_volume=self._sounds.sfx_volume,
                              colour_rgb=self._colour_rgb,
                              debug=self._debug,
                              background_texture=bg_texture)
            )

    def on_key_press(self, key: int, modifiers: int) -> None:
        if key == arcade.key.ESCAPE:
            from app.scenes.pause_menu_scene import PauseMenuScene
            self._scene_manager.push(PauseMenuScene(self, self._scene_manager, self._sounds))
            return
        self._keys.add(key)
        if key == arcade.key.T and self._debug:
            self._sounds.step_pitch()

    def on_key_release(self, key: int, modifiers: int) -> None:
        self._keys.discard(key)

    def on_resize(self, width: int, height: int) -> None:
        self._view.on_resize(width, height)

    def _send_input(self, tick: int) -> None:
        pid = self._client.player_id
        if pid is None:
            return

        mx = my = 0.0
        if arcade.key.LEFT  in self._keys or arcade.key.A in self._keys:
            mx -= 1.0
        if arcade.key.RIGHT in self._keys or arcade.key.D in self._keys:
            mx += 1.0
        if arcade.key.DOWN  in self._keys or arcade.key.S in self._keys:
            my -= 1.0
        if arcade.key.UP    in self._keys or arcade.key.W in self._keys:
            my += 1.0
        place = arcade.key.SPACE in self._keys

        inp = PlayerInput(player_id=pid, tick=tick,
                          move_x=mx, move_y=my, place_bomb=place)

        # Apply to prediction immediately
        if self._prediction:
            self._prediction.apply_input(inp)

        # Record send time for RTT measurement
        self._send_times[tick] = time.monotonic()

        # Send to server
        self._client.queue_input(InputMsg(
            player_id=pid, tick=tick,
            move_x=mx, move_y=my, place_bomb=place,
        ))

        if self._debug:
            if mx or my or place:
                print(f"[{_ts()}] [client pid={pid}] tick={tick} input: mx={mx:+.0f} my={my:+.0f} bomb={place}")
            elif tick % 60 == 0:
                print(f"[{_ts()}] [client pid={pid}] tick={tick} input: (neutral)")

    def _update_rtt(self, confirmed_server_tick: int) -> None:
        """Feed the latest confirmed server tick into the RTT EWMA."""
        now = time.monotonic()
        # Find the oldest send_times entry that the server has now confirmed
        to_remove = [t for t in self._send_times if t <= confirmed_server_tick]
        if not to_remove:
            # Purge entries older than 10 seconds to avoid unbounded growth on loss
            stale = [t for t, ts in self._send_times.items() if now - ts > 10.0]
            for t in stale:
                del self._send_times[t]
            return
        # Use the most recently confirmed tick for the measurement
        sample_tick = max(to_remove)
        rtt = now - self._send_times[sample_tick]
        for t in to_remove:
            del self._send_times[t]
        if self._smoothed_rtt is None:
            self._smoothed_rtt = rtt
        else:
            self._smoothed_rtt = (1.0 - _RTT_ALPHA) * self._smoothed_rtt + _RTT_ALPHA * rtt
