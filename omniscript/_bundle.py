"""Knowing when OmniScript is one file, so `omni update` can replace that file.

Three shapes count: a PyInstaller executable (`sys.frozen`), a zipapp run by its
own name (`argv[0]` ends in `.pyz`), and a zipapp an installer renamed to plain
`omni` -- recognised because this module is being read out of an archive rather
than off disk, which is never true of a checkout or a wheel.
"""

from __future__ import annotations

import os
import sys


def running_from_archive() -> bool:
    """True when this module was loaded out of an archive, not a directory."""
    return not os.path.isfile(os.path.abspath(__file__))


def frozen_executable() -> str | None:
    """The path of this program when it is a single replaceable file, else None."""
    if getattr(sys, "frozen", False):
        return os.path.abspath(sys.executable)
    argv0 = os.path.abspath(sys.argv[0]) if sys.argv and sys.argv[0] else ""
    if not argv0 or not os.path.isfile(argv0):
        return None
    if argv0.endswith((".pyz", ".zip")):
        return argv0
    if running_from_archive():
        return argv0
    return None
