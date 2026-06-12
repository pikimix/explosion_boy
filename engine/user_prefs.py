"""Persistent user preferences stored as JSON on disk."""
from __future__ import annotations

import json
from pathlib import Path

_PREFS_FILE = Path.home() / '.config' / 'explosion_boy' / 'prefs.json'

_DEFAULTS: dict = {
    'name': 'Player',
    'volume': 1.0,
    'colour_rgb': None,
}

_prefs: dict = dict(_DEFAULTS)


def load() -> dict:
    """Load prefs from disk, returning a copy merged with defaults."""
    global _prefs
    _prefs = dict(_DEFAULTS)
    if _PREFS_FILE.exists():
        try:
            data = json.loads(_PREFS_FILE.read_text(encoding='utf-8'))
            for key in _DEFAULTS:
                if key in data:
                    _prefs[key] = data[key]
        except Exception:
            pass
    return dict(_prefs)


def save() -> None:
    """Write current prefs to disk."""
    try:
        _PREFS_FILE.parent.mkdir(parents=True, exist_ok=True)
        _PREFS_FILE.write_text(
            json.dumps(_prefs, indent=2),
            encoding='utf-8',
        )
    except Exception:
        pass


def get(key: str):
    return _prefs.get(key, _DEFAULTS.get(key))


def set(key: str, value) -> None:  # noqa: A001
    _prefs[key] = value
