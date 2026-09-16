"""Finding the files that ship inside the package.

An ordinary install -- a clone, a wheel, a frozen executable -- has `std/*.omni`
sitting on disk next to this module, and `resolve_module` just opens them.

A zipapp does not. There the whole package lives inside one archive, Python's
import machinery can see it, and `os.path.isfile` cannot: it knows nothing about
paths that go through a zip. So when the directory is missing we copy the four
`.omni` modules out of the archive once, into a temporary directory that goes
away with the process, and report that instead. It is a few kilobytes, and it
means `use std/math` works the same however OmniScript was installed.
"""

from __future__ import annotations

import atexit
import os
import shutil
import tempfile

# The marker file we look for: if this is not on disk, we are in an archive.
_PROBE = os.path.join("std", "math.omni")

_found: str | None = None
_checked = False


def here() -> str:
    """The directory holding this module, resolved as far as the OS allows."""
    return os.path.dirname(os.path.abspath(__file__))


def std_base() -> str:
    """A directory that contains `std/`, materialising it if we are zipped.

    Never raises: the caller appends the result to its list of places to look,
    and a missing module is reported by the interpreter with a proper error.
    """
    global _found, _checked
    if _found is not None:
        return _found
    on_disk = here()
    if os.path.isfile(os.path.join(on_disk, _PROBE)):
        _found = on_disk
        return _found
    if _checked:
        return on_disk
    _checked = True
    extracted = _extract()
    _found = extracted or on_disk
    return _found


def _extract() -> str | None:
    try:
        from importlib.resources import files

        bundled = files("omniscript").joinpath("std")
        names = sorted(item.name for item in bundled.iterdir()
                       if item.name.endswith(".omni"))
    except Exception:  # pragma: no cover - no archive, no resources, no luck
        return None
    if not names:
        return None
    try:
        root = tempfile.mkdtemp(prefix="omniscript-std-")
        out = os.path.join(root, "std")
        os.mkdir(out)
        for name in names:
            data = bundled.joinpath(name).read_bytes()
            with open(os.path.join(out, name), "wb") as fh:
                fh.write(data)
    except Exception:  # pragma: no cover - a read-only temp dir, say
        return None
    atexit.register(shutil.rmtree, root, True)
    return root


def running_from_archive() -> bool:
    """True when this module was loaded out of an archive rather than a directory."""
    return not os.path.isfile(os.path.join(here(), _PROBE))


def frozen_executable() -> str | None:
    """The path of this program when it is a single replaceable file, else None.

    Three shapes count: a PyInstaller executable (`sys.frozen`, with
    `sys.executable` pointing at the binary), a zipapp run by its own name
    (`argv[0]` ends in `.pyz`), and a zipapp that an installer renamed to plain
    `omni` -- recognised because its `std/` modules are inside an archive rather
    than on disk, which is never true of a source checkout.
    """
    import sys

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
