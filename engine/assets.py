"""Asset loader and cache. Client-only — never called by the server."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import arcade

_ASSETS_DIR = Path(__file__).parent.parent / "assets"

_textures: dict[str, "arcade.Texture"] = {}


def load_texture(name: str) -> "arcade.Texture":
    """Load a texture from the assets directory, caching it for subsequent calls.

    Parameters
    ----------
    name : str
        Base filename (without extension) of the PNG under the assets directory.

    Returns
    -------
    arcade.Texture
        The loaded (or cached) texture.
    """
    if name not in _textures:
        import arcade
        path = _ASSETS_DIR / f"{name}.png"
        _textures[name] = arcade.load_texture(str(path))
    return _textures[name]


def clear_cache() -> None:
    """Clear the in-memory texture cache."""
    _textures.clear()
