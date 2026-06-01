"""Active game scene. Bridges arcade 60fps render loop and server 20tps snapshots."""
from __future__ import annotations

import arcade

from app.game_view import GameView
from app.sound_system import SoundSystem
from core.components import PlayerInput
from core.state import GameState
from net.client import GameClient
from net.protocol import GameOverMsg, InputMsg
from engine.config import INPUT_LEAD_TICKS, TICK_RATE
from systems.prediction import PredictionEngine


class GameScene:
    def __init__(self, client: GameClient,
                 scene_manager: "SceneManager",  # type: ignore[name-defined]
                 player_name: str = "Player",
                 volume: float = 1.0,
                 colour_rgb: tuple[int, int, int] = (220, 50, 50)) -> None:
        self._client = client
        self._scene_manager = scene_manager
        self._player_name = player_name
        self._colour_rgb = colour_rgb
        self._view = GameView()
        self._sounds = SoundSystem(client.player_id, volume=volume)
        self._prev_state: GameState | None = None
        self._last_sound_tick: int = -1
        self._prediction: PredictionEngine | None = None
        self._tick_accum = 0.0
        self._keys: set[int] = set()

        pid = client.player_id
        state = client.get_state()
        self._tick = (state.tick if state else 0) + INPUT_LEAD_TICKS
        if pid is not None:
            self._prediction = PredictionEngine(pid)
            if state:
                self._prediction.reconcile(state)

    def update(self, dt: float) -> None:
        # Check for non-state messages (game over, etc.)
        for msg in self._client.poll_messages():
            if isinstance(msg, GameOverMsg):
                from app.scenes.game_over_scene import GameOverScene
                self._scene_manager.replace(
                    GameOverScene(msg, self._scene_manager, self._client, self._player_name,
                                  volume=self._sounds.volume, colour_rgb=self._colour_rgb)
                )
                return

        # Reconcile prediction with latest server state; trigger sounds on new ticks
        state = self._client.get_state()
        if state and self._prediction:
            self._prediction.reconcile(state)
        if state and state.tick > self._last_sound_tick:
            self._sounds.update(self._prev_state, state)
            self._prev_state = state
            self._last_sound_tick = state.tick

        # Generate and send input at tick rate
        self._tick_accum += dt
        tick_dt = 1.0 / TICK_RATE
        while self._tick_accum >= tick_dt:
            self._tick_accum -= tick_dt
            self._tick += 1
            self._send_input(self._tick)

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
            volume=self._sounds.volume,
        )

    def on_key_press(self, key: int, modifiers: int) -> None:
        self._keys.add(key)
        if key == arcade.key.BRACKETLEFT:
            self._sounds.volume = round(self._sounds.volume - 0.1, 1)
        elif key == arcade.key.BRACKETRIGHT:
            self._sounds.volume = round(self._sounds.volume + 0.1, 1)

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

        # Send to server
        self._client.queue_input(InputMsg(
            player_id=pid, tick=tick,
            move_x=mx, move_y=my, place_bomb=place,
        ))
