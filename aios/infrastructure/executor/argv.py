"""Validation boundary for shell-free executor argv construction."""

from __future__ import annotations

import os
import shlex

from aios import config


def argv_is_safe(argv: list[str]) -> bool:
    """Return whether structured argv contains no shell composition bytes."""
    if not argv:
        return False
    return all(
        isinstance(arg, str)
        and bool(arg)
        and not any(ch in arg for ch in ";&|<>`\r\n\x00")
        for arg in argv
    )


def parse_argv(command: str) -> list[str]:
    """Parse one classified command into shell-free, structured argv.

    Authorization happens in the gateway before this boundary.  This function
    rejects shell composition and values that cannot be represented safely by
    ``Popen`` before the resulting argv reaches an execution sink.
    """
    if len(command) > max(config.MAX_COMMAND_CHARS, 1):
        raise ValueError(f"command exceeds {config.MAX_COMMAND_CHARS} character limit")
    if not command or any(ch in command for ch in ";&|<>`\r\n\x00"):
        raise ValueError("shell composition is not permitted")
    argv = shlex.split(command, posix=os.name != "nt")
    if os.name == "nt":
        argv = [
            arg[1:-1]
            if len(arg) >= 2 and arg[0] == arg[-1] and arg[0] in "\"'"
            else arg
            for arg in argv
        ]
    if not argv or not argv_is_safe(argv):
        raise ValueError("empty command")
    return argv


__all__ = ["argv_is_safe", "parse_argv"]
