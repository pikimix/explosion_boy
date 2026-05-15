"""Asset loader and cache. Client-only — never called by the server."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import arcade

_ASSETS_DIR = Path(__file__).parent.parent / "assets"

_textures: dict[str, "arcade.Texture"] = {}


def load_texture(name: str) -> "arcade.Texture":
    if name not in _textures:
        import arcade
        path = _ASSETS_DIR / f"{name}.png"
        _textures[name] = arcade.load_texture(str(path))
    return _textures[name]


def clear_cache() -> None:
    _textures.clear()
