"""Shared shader-effect init skeleton for particle/shockwave/smoke systems.

Each of those systems independently checks a force-disable flag and the
driver's GL version, then tries to load its own shaders and allocate its
own GPU resources — degrading gracefully (with a logged reason) on any
failure so the rest of the game is unaffected. This module factors out
that shared skeleton; each caller still owns its own force-disable flag
and shader/buffer setup.
"""
from __future__ import annotations

import logging
from typing import Callable

import arcade


def try_init_shader_effect(
    logger: logging.Logger,
    label: str,
    force_disabled: bool,
    build: Callable[["arcade.ArcadeContext"], None],
    success_label: str | None = None,
) -> bool:
    """Run the standard force-disable/GL-version/try-build sequence.

    Parameters
    ----------
    logger : logging.Logger
        The caller's own module logger, so log lines keep their original
        module identity.
    label : str
        Name used in the force-disabled and GL-version-warning log lines
        (e.g. "Shockwave effect").
    force_disabled : bool
        The caller's own force-disable flag.
    build : Callable[[ArcadeContext], None]
        Callback that does the effect-specific shader/program/buffer setup
        (assigning to the caller's own attributes) given the current GL
        context. Any exception it raises is treated as init failure.
    success_label : str, optional
        Name used in the "initialised" log line, if different from `label`.

    Returns
    -------
    bool
        True if `build` completed without error, False otherwise.
    """
    if force_disabled:
        logger.info('%s disabled via --no-shader flag.', label)
        return False

    ctx = arcade.get_window().ctx
    gl_ver: tuple[int, int] | None = getattr(ctx, 'gl_version', None)
    if gl_ver is not None and gl_ver < (3, 3):
        logger.warning('%s disabled — OpenGL %d.%d detected, 3.3 required.', label, *gl_ver)
        return False
    try:
        build(ctx)
        ok_label = label if success_label is None else success_label
        if gl_ver is not None:
            logger.info('%s initialised (OpenGL %d.%d).', ok_label, *gl_ver)
        else:
            logger.info('%s initialised.', ok_label)
        return True
    except Exception:
        logger.warning('%s disabled — shader load or compilation failed.', label, exc_info=True)
        return False
