"""Pause menu overlay — drawn on top of the running game."""
from __future__ import annotations

import arcade

from engine import user_prefs

_OVERLAY_COLOUR = (0, 0, 0, 160)
_PANEL_W = 440
_PANEL_H = 310
_PANEL_COLOUR = (28, 30, 42, 238)
_PANEL_BORDER = (90, 95, 130, 200)
_TITLE_COLOUR = (240, 240, 255, 255)
_LABEL_COLOUR = (190, 195, 215, 255)
_HINT_COLOUR = (110, 115, 140, 200)
_BAR_BG = (45, 48, 65, 210)
_BAR_FILL = (110, 150, 255, 220)
_BAR_OUTLINE = (100, 105, 140, 160)
_HANDLE_COLOUR = (210, 225, 255, 245)
_BTN_COLOUR = (55, 65, 100, 225)
_BTN_HOVER_COLOUR = (80, 95, 145, 240)
_BTN_BORDER = (130, 145, 200, 200)
_BTN_TEXT_COLOUR = (215, 225, 255, 255)

_SLIDER_W = 190
_SLIDER_H = 13
_BTN_W = 190
_BTN_H = 38

# Vertical offsets from panel centre for each slider row (0=music, 1=sfx)
_SLIDER_Y_OFFSETS = [48, -10]


class PauseMenuScene:
    def __init__(self, background_scene, scene_manager, sound_system) -> None:  # type: ignore[type-arg]
        self._background = background_scene
        self._scene_manager = scene_manager
        self._sounds = sound_system
        self._dragging: int | None = None  # 0=music, 1=sfx
        self._resume_hovered = False

        # Release held movement keys so player doesn't drift while menu is open
        if hasattr(background_scene, '_keys'):
            background_scene._keys.clear()

        # Text objects created lazily on first draw (window size needed for position)
        self._title_text: arcade.Text | None = None
        self._hint_text: arcade.Text | None = None
        self._resume_text: arcade.Text | None = None
        self._slider_label_texts: list[arcade.Text] = []
        self._slider_value_texts: list[arcade.Text] = []

    # ── Geometry helpers ──────────────────────────────────────────────────────

    def _panel_bounds(self, win: arcade.Window) -> tuple[float, float, float, float]:
        cx, cy = win.width / 2, win.height / 2
        return cx - _PANEL_W / 2, cy - _PANEL_H / 2, cx + _PANEL_W / 2, cy + _PANEL_H / 2

    def _slider_left(self, win: arcade.Window) -> float:
        return win.width / 2 - _PANEL_W / 2 + 175

    def _slider_cy(self, win: arcade.Window, idx: int) -> float:
        return win.height / 2 + _SLIDER_Y_OFFSETS[idx]

    def _btn_bounds(self, win: arcade.Window) -> tuple[float, float, float, float]:
        cx, cy = win.width / 2, win.height / 2
        pb = cy - _PANEL_H / 2
        return (cx - _BTN_W / 2, pb + 28, cx + _BTN_W / 2, pb + 28 + _BTN_H)

    def _value_from_x(self, x: float, sl: float) -> float:
        return max(0.0, min(1.0, (x - sl) / _SLIDER_W))

    # ── Text initialisation ───────────────────────────────────────────────────

    def _ensure_texts(self, win: arcade.Window) -> None:
        if self._title_text is not None:
            return

        cx, cy = win.width / 2, win.height / 2
        pl, pb, pr, pt = self._panel_bounds(win)
        sl = self._slider_left(win)
        label_x = pl + 18

        self._title_text = arcade.Text(
            'PAUSED', cx, pt - 28,
            color=_TITLE_COLOUR, font_size=22, bold=True,
            anchor_x='center', anchor_y='top',
        )
        self._hint_text = arcade.Text(
            'Press ESC to resume', cx, pb + 10,
            color=_HINT_COLOUR, font_size=9,
            anchor_x='center', anchor_y='bottom',
        )
        bl, bb, br, bt = self._btn_bounds(win)
        self._resume_text = arcade.Text(
            'Resume', (bl + br) / 2, (bb + bt) / 2,
            color=_BTN_TEXT_COLOUR, font_size=13, bold=True,
            anchor_x='center', anchor_y='center',
        )

        for i, label in enumerate(('Music Volume', 'Sound Effects')):
            sy = self._slider_cy(win, i)
            self._slider_label_texts.append(arcade.Text(
                label, label_x, sy,
                color=_LABEL_COLOUR, font_size=11,
                anchor_x='left', anchor_y='center',
            ))
            self._slider_value_texts.append(arcade.Text(
                '100%', sl + _SLIDER_W + 14, sy,
                color=_LABEL_COLOUR, font_size=10,
                anchor_x='left', anchor_y='center',
            ))

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def update(self, dt: float) -> None:
        self._background.update(dt)

    def draw(self) -> None:
        self._background.draw()

        win = arcade.get_window()
        self._ensure_texts(win)
        cx, cy = win.width / 2, win.height / 2
        pl, pb, pr, pt = self._panel_bounds(win)

        # Full-screen dim
        arcade.draw_rect_filled(arcade.LBWH(0, 0, win.width, win.height), _OVERLAY_COLOUR)

        # Panel
        arcade.draw_rect_filled(arcade.LBWH(pl, pb, _PANEL_W, _PANEL_H), _PANEL_COLOUR)
        arcade.draw_rect_outline(arcade.LBWH(pl, pb, _PANEL_W, _PANEL_H), _PANEL_BORDER, border_width=1)

        self._title_text.draw()  # type: ignore[union-attr]
        self._hint_text.draw()   # type: ignore[union-attr]

        # Sliders
        sl = self._slider_left(win)
        track_cx = sl + _SLIDER_W / 2
        values = [self._sounds.music_volume, self._sounds.sfx_volume]

        for i, value in enumerate(values):
            sy = self._slider_cy(win, i)
            self._slider_label_texts[i].draw()

            # Track
            arcade.draw_rect_filled(arcade.XYWH(track_cx, sy, _SLIDER_W, _SLIDER_H), _BAR_BG)
            fill_w = _SLIDER_W * value
            if fill_w > 0:
                arcade.draw_rect_filled(
                    arcade.XYWH(sl + fill_w / 2, sy, fill_w, _SLIDER_H), _BAR_FILL,
                )
            arcade.draw_rect_outline(
                arcade.XYWH(track_cx, sy, _SLIDER_W, _SLIDER_H), _BAR_OUTLINE, border_width=1,
            )
            # Handle
            arcade.draw_rect_filled(
                arcade.XYWH(sl + _SLIDER_W * value, sy, 4, _SLIDER_H + 7), _HANDLE_COLOUR,
            )

            self._slider_value_texts[i].text = f'{int(value * 100)}%'
            self._slider_value_texts[i].draw()

        # Resume button
        bl, bb, br, bt = self._btn_bounds(win)
        btn_cx, btn_cy = (bl + br) / 2, (bb + bt) / 2
        btn_col = _BTN_HOVER_COLOUR if self._resume_hovered else _BTN_COLOUR
        arcade.draw_rect_filled(arcade.XYWH(btn_cx, btn_cy, _BTN_W, _BTN_H), btn_col)
        arcade.draw_rect_outline(arcade.XYWH(btn_cx, btn_cy, _BTN_W, _BTN_H), _BTN_BORDER, border_width=1)
        self._resume_text.draw()  # type: ignore[union-attr]

    # ── Input ─────────────────────────────────────────────────────────────────

    def on_key_press(self, key: int, modifiers: int) -> None:
        if key == arcade.key.ESCAPE:
            self._scene_manager.pop()

    def on_key_release(self, key: int, modifiers: int) -> None:
        pass

    def on_mouse_press(self, x: float, y: float, button: int, modifiers: int) -> None:
        win = arcade.get_window()

        bl, bb, br, bt = self._btn_bounds(win)
        if bl <= x <= br and bb <= y <= bt:
            self._scene_manager.pop()
            return

        sl = self._slider_left(win)
        for i in range(2):
            sy = self._slider_cy(win, i)
            if sl - 8 <= x <= sl + _SLIDER_W + 8 and abs(y - sy) <= 14:
                self._dragging = i
                self._apply_drag(i, x, win)
                return

    def on_mouse_drag(self, x: float, y: float, dx: float, dy: float,
                      buttons: int, modifiers: int) -> None:
        if self._dragging is not None:
            self._apply_drag(self._dragging, x, arcade.get_window())

    def on_mouse_release(self, x: float, y: float, button: int, modifiers: int) -> None:
        self._dragging = None

    def on_mouse_motion(self, x: float, y: float, dx: float, dy: float) -> None:
        win = arcade.get_window()
        bl, bb, br, bt = self._btn_bounds(win)
        self._resume_hovered = bl <= x <= br and bb <= y <= bt

    def _apply_drag(self, idx: int, x: float, win: arcade.Window) -> None:
        sl = self._slider_left(win)
        value = round(self._value_from_x(x, sl), 2)
        if idx == 0:
            self._sounds.music_volume = value
            user_prefs.set('music_volume', value)
        else:
            self._sounds.sfx_volume = value
            user_prefs.set('sfx_volume', value)
