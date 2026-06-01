"""Game over screen. Shows winner, play-again and quit buttons."""
from __future__ import annotations

import arcade
import arcade.gui

from net.protocol import GameOverMsg


class GameOverScene:
    def __init__(self, result: GameOverMsg,
                 scene_manager: "SceneManager",  # type: ignore[name-defined]
                 client: "GameClient",            # type: ignore[name-defined]
                 player_name: str = "Player",
                 volume: float = 1.0,
                 colour_rgb: tuple[int, int, int] = (220, 50, 50)) -> None:
        self._scene_manager = scene_manager
        self._client = client
        self._result = result
        self._player_name = player_name
        self._volume = volume
        self._colour_rgb = colour_rgb

        self._ui = arcade.gui.UIManager()
        self._ui.enable()

        layout = arcade.gui.UIBoxLayout(vertical=True, space_between=16)

        again_btn = arcade.gui.UIFlatButton(text="Play Again", width=200)
        again_btn.on_click = self._on_again  # type: ignore[method-assign]

        quit_btn = arcade.gui.UIFlatButton(text="Quit", width=200)
        quit_btn.on_click = self._on_quit  # type: ignore[method-assign]

        layout.add(again_btn)
        layout.add(quit_btn)

        self._ui.add(
            arcade.gui.UIAnchorLayout().add(layout,
                                            anchor_x="center_x",
                                            anchor_y="center_y")
        )

    def _on_again(self, _event) -> None:
        from app.scenes.lobby_scene import LobbyScene
        self._ui.disable()
        self._scene_manager.replace(
            LobbyScene(self._client, self._player_name, self._scene_manager,
                       volume=self._volume, colour_rgb=self._colour_rgb)
        )

    def _on_quit(self, _event) -> None:
        import arcade
        arcade.exit()

    def update(self, dt: float) -> None:
        pass

    def draw(self) -> None:
        if self._result.winner_id is not None:
            headline = f"{self._result.winner_name} wins!"
        else:
            headline = "Draw!"
        win = arcade.get_window()
        arcade.draw_text(
            headline,
            win.width / 2, win.height / 2 + 100,
            arcade.color.WHITE, font_size=40, bold=True,
            anchor_x="center",
        )
        self._ui.draw()

    def on_key_press(self, key: int, modifiers: int) -> None:
        pass

    def on_key_release(self, key: int, modifiers: int) -> None:
        pass
