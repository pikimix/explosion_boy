"""Tests for engine.gl_log_filter."""
from engine.gl_log_filter import is_noise


def test_is_noise_matches_known_driver_warning() -> None:
    """The known GLDriver Metal 'not implemented' warning is treated as noise."""
    assert is_noise(b'gldCopyBufferSubData: NEEDS IMPLEMENTATION') is True


def test_is_noise_ignores_unrelated_lines() -> None:
    """Ordinary output, such as a traceback line, is never filtered."""
    assert is_noise(b'Traceback (most recent call last):') is False


def test_is_noise_ignores_empty_line() -> None:
    """An empty line is not treated as noise."""
    assert is_noise(b'') is False
