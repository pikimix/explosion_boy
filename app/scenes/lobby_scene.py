"""Lobby waiting room. Connects to server, shows player list and ready status."""
from __future__ import annotations

import colorsys
import math
from pathlib import Path

import arcade
import arcade.camera
import arcade.shape_list
from PIL import Image

from app.sound_system import MusicPlayer, set_master_volume
from app.ui import volume_widget
from app.ui.hud import HUD_WIDTH
from core.components import TileKind
from net.client import GameClient
from net.protocol import GameStartMsg, LobbyUpdateMsg
from engine import user_prefs
from engine.config import (
    GRID_COLS, GRID_ROWS, PLAYER_COLOURS, SPAWN_POINTS,
    TILE_SIZE, WINDOW_H, WINDOW_W,
)

_LOBBY_MUSIC_PATH = Path(__file__).parent.parent.parent / 'resources' / 'music' / 'in_the_lobby.wav'

_SOLID_COLOUR = (60,  60,  60,  255)
_EMPTY_COLOUR = (180, 180, 180, 255)
_PLAYER_RADIUS = TILE_SIZE * 0.38

_HUD_X = 10.0
_HUD_TOP_MARGIN = 10.0
_NAME_SIZE = 13
_STATUS_SIZE = 11
_NAME_H = 17.0
_STATUS_H = 15.0
_PLAYER_GAP = 8.0

_NAME_BOX_Y = 172.0       # centre y of the editable name input box
_NAME_BOX_H = 20.0
_MAX_NAME_LEN = 16

# Colour picker popup dimensions
_WHEEL_SIZE = 200         # diameter of the HSV wheel in pixels
_POPUP_W = 280
_POPUP_H = 310
_SLIDER_H = 18
_SLIDER_SEGMENTS = 24     # gradient segments in brightness slider


class LobbyScene:
    def __init__(self, client: GameClient, player_name: str,
                 scene_manager: 'SceneManager',  # type: ignore[name-defined]
                 volume: float = 1.0,
                 colour_rgb: tuple[int, int, int] | None = None,
                 debug: bool = False) -> None:
        self._client = client
        self._scene_manager = scene_manager
        self._player_name = player_name
        self._players: list[dict] = []
        self._ready = False
        self._volume = volume
        self._debug = debug
        self._spawn_shapes: arcade.shape_list.ShapeElementList = (
            arcade.shape_list.ShapeElementList()
        )
        self._spawn_texts: list[arcade.Text] = []

        # Colour picker state
        self._colour_rgb: tuple[int, int, int] = colour_rgb if colour_rgb is not None else (220, 50, 50)
        self._colour_initialised = colour_rgb is not None
        self._colour_sent = False  # whether we've pushed colour to server this session
        rv, gv, bv = (c / 255.0 for c in self._colour_rgb)
        self._hue, self._saturation, self._value = colorsys.rgb_to_hsv(rv, gv, bv)
        r = _WHEEL_SIZE / 2
        self._wheel_sel_dx = math.cos(2 * math.pi * self._hue) * r * self._saturation
        self._wheel_sel_dy = -math.sin(2 * math.pi * self._hue) * r * self._saturation
        self._picker_open = False
        self._wheel_texture: arcade.Texture | None = None

        self._tile_shapes = self._build_preview_tiles()
        self._map_w = GRID_COLS * TILE_SIZE
        self._map_h = GRID_ROWS * TILE_SIZE
        self._camera = self._make_camera(WINDOW_W, WINDOW_H)

        play_cx = HUD_WIDTH + (WINDOW_W - HUD_WIDTH) / 2
        self._title_text = arcade.Text(
            'EXPLOSION BOY',
            play_cx, WINDOW_H - 40,
            arcade.color.WHITE, font_size=32, bold=True,
            anchor_x='center',
        )
        self._waiting_text = arcade.Text(
            'Waiting for players…',
            play_cx, WINDOW_H / 2,
            arcade.color.WHITE, font_size=16,
            anchor_x='center',
        )

        swatch_w = HUD_WIDTH - _HUD_X * 2
        swatch_cx = _HUD_X + swatch_w / 2

        self._hud_header_text = arcade.Text(
            'Players', _HUD_X, 0,
            color=(200, 200, 200), font_size=12, bold=True,
            anchor_x='left', anchor_y='top',
        )
        self._your_colour_text = arcade.Text(
            'Your colour', _HUD_X, 146,
            color=(200, 200, 200), font_size=10,
            anchor_x='left', anchor_y='bottom',
        )
        self._swatch_label_text = arcade.Text(
            'click to change', swatch_cx, 130,
            color=(255, 255, 255, 160), font_size=9,
            anchor_x='center', anchor_y='center',
        )
        self._hint_text = arcade.Text(
            'Press SPACE\nto ready up', _HUD_X, 70,
            color=(200, 200, 200), font_size=11,
            anchor_x='left', anchor_y='bottom',
            multiline=True, width=int(HUD_WIDTH - _HUD_X * 2),
        )
        self._picker_title_text = arcade.Text(
            'Pick Your Colour', 0, 0,
            color=(230, 230, 230), font_size=13, bold=True,
            anchor_x='center', anchor_y='top',
        )
        self._picker_brightness_text = arcade.Text(
            'Brightness', 0, 0,
            color=(150, 150, 150), font_size=8,
            anchor_x='left', anchor_y='top',
        )
        self._picker_close_text = arcade.Text(
            'Click outside to close', 0, 0,
            color=(140, 140, 140), font_size=9,
            anchor_x='center', anchor_y='bottom',
        )
        self._hud_name_texts: list[arcade.Text] = []
        self._hud_status_texts: list[arcade.Text] = []

        # Name editing state
        self._editing_name = False
        self._name_draft = player_name
        self._cursor_blink = 0.0

        self._your_name_label_text = arcade.Text(
            'Your name', _HUD_X, _NAME_BOX_Y + _NAME_BOX_H / 2 + 4,
            color=(200, 200, 200), font_size=10,
            anchor_x='left', anchor_y='bottom',
        )
        self._name_input_text = arcade.Text(
            player_name, _HUD_X + 4, _NAME_BOX_Y,
            color=(255, 255, 255), font_size=11,
            anchor_x='left', anchor_y='center',
        )

        set_master_volume(self._volume)
        self._music = MusicPlayer(_LOBBY_MUSIC_PATH)
        self._music.play()

        client.send_join(player_name)

    # ── Colour picker ─────────────────────────────────────────────────────────

    def _ensure_wheel(self) -> None:
        """Build the HSV wheel texture the first time the picker is opened."""
        if self._wheel_texture is not None:
            return
        size = _WHEEL_SIZE
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        pixels = img.load()
        assert pixels is not None
        cx = cy = size / 2
        r = size / 2 - 1
        for y in range(size):
            for x in range(size):
                dx, dy = x - cx, y - cy
                dist = math.sqrt(dx * dx + dy * dy)
                if dist <= r:
                    hue = (math.atan2(dy, dx) / (2 * math.pi)) % 1.0
                    sat = dist / r
                    rv, gv, bv = colorsys.hsv_to_rgb(hue, sat, 1.0)
                    pixels[x, y] = (int(rv * 255), int(gv * 255), int(bv * 255), 255)
        self._wheel_texture = arcade.Texture(img)

    def _update_colour_from_hsv(self) -> None:
        rv, gv, bv = colorsys.hsv_to_rgb(self._hue, self._saturation, self._value)
        self._colour_rgb = (int(rv * 255), int(gv * 255), int(bv * 255))

    def _wheel_coords(self, win: arcade.Window) -> tuple[float, float]:
        popup_cx = win.width / 2
        popup_cy = win.height / 2
        wheel_cx = popup_cx
        wheel_cy = popup_cy + 25
        return wheel_cx, wheel_cy

    def _slider_bounds(self, win: arcade.Window) -> tuple[float, float, float, float]:
        """Return (left, right, bottom, top) for the brightness slider."""
        _, wheel_cy = self._wheel_coords(win)
        slider_left = win.width / 2 - _WHEEL_SIZE / 2
        slider_right = slider_left + _WHEEL_SIZE
        slider_bottom = wheel_cy - _WHEEL_SIZE / 2 - 24
        slider_top = slider_bottom + _SLIDER_H
        return slider_left, slider_right, slider_bottom, slider_top

    def on_mouse_press(self, x: float, y: float, button: int, modifiers: int) -> None:
        if button != arcade.MOUSE_BUTTON_LEFT:
            return
        if self._picker_open:
            if not self._handle_picker_input(x, y):
                # Click outside popup → close
                win = arcade.get_window()
                popup_cx = win.width / 2
                popup_cy = win.height / 2
                if not (popup_cx - _POPUP_W / 2 <= x <= popup_cx + _POPUP_W / 2
                        and popup_cy - _POPUP_H / 2 <= y <= popup_cy + _POPUP_H / 2):
                    self._picker_open = False
            return

        swatch_w = HUD_WIDTH - _HUD_X * 2
        name_box_bottom = _NAME_BOX_Y - _NAME_BOX_H / 2
        name_box_top = _NAME_BOX_Y + _NAME_BOX_H / 2
        if _HUD_X <= x <= _HUD_X + swatch_w and name_box_bottom <= y <= name_box_top:
            # Activate name editing
            if not self._editing_name:
                self._name_draft = self._player_name
                self._cursor_blink = 0.0
            self._editing_name = True
        elif self._editing_name:
            # Click outside name box while editing → confirm
            self._confirm_rename()
        elif _HUD_X <= x <= _HUD_X + swatch_w and 118 <= y <= 142:
            # Click on the HUD colour swatch to open picker
            self._ensure_wheel()
            self._picker_open = True

    def on_mouse_drag(
        self, x: float, y: float, _dx: float, _dy: float, buttons: int, _modifiers: int
    ) -> None:
        if buttons & arcade.MOUSE_BUTTON_LEFT and self._picker_open:
            self._handle_picker_input(x, y)

    def _handle_picker_input(self, x: float, y: float) -> bool:
        """Update picker state from a mouse position. Returns True if the position hit a control."""
        win = arcade.get_window()
        wheel_cx, wheel_cy = self._wheel_coords(win)

        dx, dy = x - wheel_cx, y - wheel_cy
        dist = math.sqrt(dx * dx + dy * dy)

        # Wheel → update hue + saturation
        if dist <= _WHEEL_SIZE / 2:
            self._wheel_sel_dx = dx
            self._wheel_sel_dy = dy
            self._hue = (math.atan2(-dy, dx) / (2 * math.pi)) % 1.0
            self._saturation = min(dist / (_WHEEL_SIZE / 2), 1.0)
            self._update_colour_from_hsv()
            self._client.send_colour(self._colour_rgb)
            user_prefs.set('colour_rgb', list(self._colour_rgb))
            return True

        # Slider → update brightness
        sl, sr, sb, st = self._slider_bounds(win)
        if sl <= x <= sr and sb <= y <= st:
            self._value = max(0.0, min(1.0, (x - sl) / (sr - sl)))
            self._update_colour_from_hsv()
            self._client.send_colour(self._colour_rgb)
            user_prefs.set('colour_rgb', list(self._colour_rgb))
            return True

        return False

    # ── Camera ────────────────────────────────────────────────────────────────

    def _make_camera(self, width: float, height: float) -> arcade.camera.Camera2D:
        play_w = width - HUD_WIDTH
        return arcade.camera.Camera2D(
            viewport=arcade.LBWH(HUD_WIDTH, 0, play_w, height),
            position=(self._map_w / 2, self._map_h / 2),
            zoom=min(play_w / self._map_w, height / self._map_h),
        )

    # ── Map preview ───────────────────────────────────────────────────────────

    def _build_preview_tiles(self) -> arcade.shape_list.ShapeElementList:
        shape_list = arcade.shape_list.ShapeElementList()
        for row in range(GRID_ROWS):
            for col in range(GRID_COLS):
                is_wall = (
                    row == 0 or row == GRID_ROWS - 1
                    or col == 0 or col == GRID_COLS - 1
                    or (row % 2 == 0 and col % 2 == 0)
                )
                colour = _SOLID_COLOUR if is_wall else _EMPTY_COLOUR
                cx = col * TILE_SIZE + TILE_SIZE / 2
                cy = row * TILE_SIZE + TILE_SIZE / 2
                shape_list.append(
                    arcade.shape_list.create_rectangle_filled(
                        cx, cy, TILE_SIZE - 2, TILE_SIZE - 2, colour,
                    )
                )
        return shape_list

    # ── Network ───────────────────────────────────────────────────────────────

    def update(self, dt: float) -> None:
        self._cursor_blink = (self._cursor_blink + dt) % 1.0
        for msg in self._client.poll_messages():
            if isinstance(msg, LobbyUpdateMsg):
                self._players = msg.players
                if self._client.player_id is not None and not self._colour_initialised:
                    pid = self._client.player_id
                    initial = PLAYER_COLOURS[pid % len(PLAYER_COLOURS)]
                    self._colour_rgb = initial[:3]
                    rv, gv, bv = (c / 255.0 for c in self._colour_rgb)
                    self._hue, self._saturation, self._value = colorsys.rgb_to_hsv(rv, gv, bv)
                    r = _WHEEL_SIZE / 2
                    self._wheel_sel_dx = math.cos(2 * math.pi * self._hue) * r * self._saturation
                    self._wheel_sel_dy = -math.sin(2 * math.pi * self._hue) * r * self._saturation
                    self._colour_initialised = True
                if self._client.player_id is not None and not self._colour_sent:
                    self._client.send_colour(self._colour_rgb)
                    self._colour_sent = True
                self._rebuild_spawn_markers()
            elif isinstance(msg, GameStartMsg):
                self._music.stop()
                from app.scenes.game_scene import GameScene
                self._scene_manager.replace(
                    GameScene(self._client, self._scene_manager, self._player_name,
                              volume=self._volume, colour_rgb=self._colour_rgb,
                              debug=self._debug, start_state=msg.get_state())
                )
                return

    # ── Draw ──────────────────────────────────────────────────────────────────

    def draw(self) -> None:
        with self._camera.activate():
            self._tile_shapes.draw()
            self._spawn_shapes.draw()
            for t in self._spawn_texts:
                t.draw()
        self._title_text.draw()
        if not self._players:
            self._waiting_text.draw()
        self._draw_hud()
        if self._picker_open:
            self._draw_picker_popup()
        if self._client.reconnecting:
            from app.ui.overlay import draw_reconnecting
            draw_reconnecting()

    def _draw_hud(self) -> None:
        win = arcade.get_window()
        y = win.height - _HUD_TOP_MARGIN

        self._hud_header_text.y = y
        self._hud_header_text.draw()
        y -= 22.0

        while len(self._hud_name_texts) < len(self._players):
            self._hud_name_texts.append(arcade.Text(
                '', _HUD_X, 0, (255, 255, 255),
                font_size=_NAME_SIZE, bold=True,
                anchor_x='left', anchor_y='top',
            ))
            self._hud_status_texts.append(arcade.Text(
                '', _HUD_X, 0, (180, 180, 180),
                font_size=_STATUS_SIZE,
                anchor_x='left', anchor_y='top',
            ))

        for i, p in enumerate(self._players):
            pid = p['id']
            colour = tuple(p.get('colour_rgb', PLAYER_COLOURS[pid % len(PLAYER_COLOURS)][:3]))

            nt = self._hud_name_texts[i]
            nt.text = p['name']
            nt.color = colour
            nt.y = y
            nt.draw()
            y -= _NAME_H

            ready = p['ready']
            st = self._hud_status_texts[i]
            st.text = '✓ Ready' if ready else '… Waiting'
            st.color = (100, 220, 100) if ready else (180, 180, 180)
            st.y = y
            st.draw()
            y -= _STATUS_H + _PLAYER_GAP

        volume_widget.draw(self._volume)

        # Name input box
        swatch_w = HUD_WIDTH - _HUD_X * 2
        swatch_cx = _HUD_X + swatch_w / 2
        self._your_name_label_text.draw()
        box_border = (100, 180, 255, 200) if self._editing_name else (140, 140, 140, 160)
        arcade.draw_rect_filled(
            arcade.XYWH(swatch_cx, _NAME_BOX_Y, swatch_w, _NAME_BOX_H),
            (40, 40, 40, 200),
        )
        arcade.draw_rect_outline(
            arcade.XYWH(swatch_cx, _NAME_BOX_Y, swatch_w, _NAME_BOX_H),
            box_border, 1,
        )
        display = self._name_draft if self._editing_name else self._player_name
        cursor = '|' if (self._editing_name and self._cursor_blink < 0.5) else ''
        self._name_input_text.text = display + cursor
        self._name_input_text.draw()

        # Colour swatch button
        self._your_colour_text.draw()
        arcade.draw_rect_filled(
            arcade.XYWH(swatch_cx, 130, swatch_w, 24),
            (*self._colour_rgb, 255),
        )
        arcade.draw_rect_outline(
            arcade.XYWH(swatch_cx, 130, swatch_w, 24),
            (255, 255, 255, 120), 1,
        )
        brightness = sum(self._colour_rgb) / (255 * 3)
        self._swatch_label_text.color = (0, 0, 0, 160) if brightness > 0.5 else (255, 255, 255, 160)
        self._swatch_label_text.draw()

        # Space-to-ready / name-edit hint
        if self._editing_name:
            self._hint_text.text = 'Press ENTER to\nconfirm name'
            self._hint_text.color = (100, 180, 255)
        elif self._ready:
            self._hint_text.text = 'Ready!\nWaiting for\nothers…'
            self._hint_text.color = (100, 220, 100)
        else:
            self._hint_text.text = 'Press SPACE\nto ready up'
            self._hint_text.color = (200, 200, 200)
        self._hint_text.draw()

    def _draw_picker_popup(self) -> None:
        win = arcade.get_window()
        popup_cx = win.width / 2
        popup_cy = win.height / 2

        # Background panel
        arcade.draw_rect_filled(
            arcade.XYWH(popup_cx, popup_cy, _POPUP_W, _POPUP_H),
            (28, 28, 28, 230),
        )
        arcade.draw_rect_outline(
            arcade.XYWH(popup_cx, popup_cy, _POPUP_W, _POPUP_H),
            (160, 160, 160, 200), 2,
        )
        self._picker_title_text.x = popup_cx
        self._picker_title_text.y = popup_cy + _POPUP_H / 2 - 12
        self._picker_title_text.draw()

        # HSV wheel
        wheel_cx, wheel_cy = self._wheel_coords(win)
        if self._wheel_texture:
            arcade.draw_texture_rect(
                self._wheel_texture,
                arcade.XYWH(wheel_cx, wheel_cy, _WHEEL_SIZE, _WHEEL_SIZE),
            )

        # Selection crosshair — positioned from last click
        sel_x = wheel_cx + self._wheel_sel_dx
        sel_y = wheel_cy + self._wheel_sel_dy
        arcade.draw_circle_outline(sel_x, sel_y, 7, (0, 0, 0, 180), 2)
        arcade.draw_circle_outline(sel_x, sel_y, 7, (255, 255, 255, 220), 1)

        # Brightness slider (black → full hue/sat colour)
        sl, sr, sb, st = self._slider_bounds(win)
        slider_cx = (sl + sr) / 2
        slider_cy = (sb + st) / 2
        seg_w = (sr - sl) / _SLIDER_SEGMENTS
        for i in range(_SLIDER_SEGMENTS):
            t = i / (_SLIDER_SEGMENTS - 1)
            rv, gv, bv = colorsys.hsv_to_rgb(self._hue, self._saturation, t)
            seg_cx = sl + (i + 0.5) * seg_w
            arcade.draw_rect_filled(
                arcade.XYWH(seg_cx, slider_cy, seg_w + 0.5, _SLIDER_H),
                (int(rv * 255), int(gv * 255), int(bv * 255), 255),
            )
        arcade.draw_rect_outline(
            arcade.XYWH(slider_cx, slider_cy, sr - sl, _SLIDER_H),
            (140, 140, 140, 180), 1,
        )
        # Slider thumb
        thumb_x = sl + self._value * (sr - sl)
        arcade.draw_rect_filled(
            arcade.XYWH(thumb_x, slider_cy, 3, _SLIDER_H + 8),
            (255, 255, 255, 230),
        )
        self._picker_brightness_text.x = sl
        self._picker_brightness_text.y = sb - 4
        self._picker_brightness_text.draw()

        self._picker_close_text.x = popup_cx
        self._picker_close_text.y = popup_cy - _POPUP_H / 2 + 10
        self._picker_close_text.draw()

    def on_resize(self, width: int, height: int) -> None:
        self._camera = self._make_camera(width, height)
        play_cx = HUD_WIDTH + (width - HUD_WIDTH) / 2
        self._title_text.x = play_cx
        self._title_text.y = height - 40
        self._waiting_text.x = play_cx
        self._waiting_text.y = height / 2

    def on_text(self, text: str) -> None:
        if not self._editing_name:
            return
        for ch in text:
            if ch.isprintable() and len(self._name_draft) < _MAX_NAME_LEN:
                self._name_draft += ch
                self._cursor_blink = 0.0

    def _confirm_rename(self) -> None:
        self._editing_name = False
        stripped = self._name_draft.strip()
        if stripped and stripped != self._player_name:
            self._player_name = stripped
            self._client.send_rename(stripped)
            user_prefs.set('name', stripped)

    def on_key_press(self, key: int, modifiers: int) -> None:
        if self._editing_name:
            if key == arcade.key.BACKSPACE:
                self._name_draft = self._name_draft[:-1]
                self._cursor_blink = 0.0
            elif key in (arcade.key.RETURN, arcade.key.ENTER):
                self._confirm_rename()
            elif key == arcade.key.ESCAPE:
                self._editing_name = False
                self._name_draft = self._player_name
            return

        if key == arcade.key.ESCAPE and self._picker_open:
            self._picker_open = False
        elif key == arcade.key.SPACE:
            self._ready = not self._ready
            self._client.send_ready(self._ready)
        elif key == arcade.key.BRACKETLEFT:
            self._volume = round(max(0.0, self._volume - 0.1), 1)
            user_prefs.set('volume', self._volume)
            set_master_volume(self._volume)
            self._music.sync_volume()
        elif key == arcade.key.BRACKETRIGHT:
            self._volume = round(min(1.0, self._volume + 0.1), 1)
            user_prefs.set('volume', self._volume)
            set_master_volume(self._volume)
            self._music.sync_volume()

    def on_key_release(self, key: int, modifiers: int) -> None:
        pass

    # ── Spawn markers ─────────────────────────────────────────────────────────

    def _rebuild_spawn_markers(self) -> None:
        shapes = arcade.shape_list.ShapeElementList()
        texts = []
        for p in self._players:
            pid = p['id']
            col, row = SPAWN_POINTS[pid]
            px = col * TILE_SIZE + TILE_SIZE / 2
            py = row * TILE_SIZE + TILE_SIZE / 2
            colour_rgb = tuple(p.get('colour_rgb', PLAYER_COLOURS[pid % len(PLAYER_COLOURS)][:3]))
            colour = (*colour_rgb, 255)
            shapes.append(
                arcade.shape_list.create_ellipse_filled(
                    px, py, _PLAYER_RADIUS, _PLAYER_RADIUS, colour,
                )
            )
            label = f"{p['name']}  {'✓' if p['ready'] else '…'}"
            texts.append(arcade.Text(
                label, px, py + _PLAYER_RADIUS + 4,
                colour, font_size=11, bold=True,
                anchor_x='center',
            ))
        self._spawn_shapes = shapes
        self._spawn_texts = texts
