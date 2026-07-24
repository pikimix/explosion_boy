"""Suppresses known-harmless native GL/Metal driver log noise on macOS.

Apple's OpenGL-on-Metal shim ("GLDriver Metal") writes warnings such as
"gldCopyBufferSubData: NEEDS IMPLEMENTATION" straight to the process's
stderr file descriptor when it silently no-ops an unimplemented GL call.
These bypass Python's logging module and sys.stderr object entirely, so
the only way to filter them out is to intercept the underlying OS file
descriptor.
"""
from __future__ import annotations

import os
import re
import sys
import threading

_NOISE_PATTERNS: tuple[re.Pattern[bytes], ...] = (
    re.compile(rb'NEEDS IMPLEMENTATION'),
)


def is_noise(line: bytes) -> bool:
    """Return True if `line` matches a known-harmless driver log pattern."""
    return any(pattern.search(line) for pattern in _NOISE_PATTERNS)


def install() -> None:
    """Start filtering known-harmless native log noise out of stderr.

    No-op on non-macOS platforms, where this noise does not occur. Must be
    called before the GL context is created so the redirected descriptor is
    in place when the driver starts logging.
    """
    if sys.platform != 'darwin':
        return

    real_stderr_fd = os.dup(sys.stderr.fileno())
    read_fd, write_fd = os.pipe()
    os.dup2(write_fd, sys.stderr.fileno())
    os.close(write_fd)

    thread = threading.Thread(
        target=_pump, args=(read_fd, real_stderr_fd), daemon=True,
    )
    thread.start()


def _pump(read_fd: int, real_stderr_fd: int) -> None:
    """Copy stderr from `read_fd` to `real_stderr_fd`, dropping noise lines."""
    with os.fdopen(read_fd, 'rb', buffering=0) as pipe_in, \
            os.fdopen(real_stderr_fd, 'wb', buffering=0) as real_out:
        buf = b''
        while True:
            chunk = pipe_in.read(4096)
            if not chunk:
                break
            buf += chunk
            *lines, buf = buf.split(b'\n')
            for line in lines:
                if not is_noise(line):
                    real_out.write(line + b'\n')
        if buf and not is_noise(buf):
            real_out.write(buf)
