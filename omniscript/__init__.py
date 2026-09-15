"""OmniScript -- a small language for doing big things in few lines.

    from omniscript import run_source
    run_source('print("hello")')
"""

from __future__ import annotations

from .errors import (OmniError, OmniLexError, OmniNameError, OmniRuntimeError,
                     OmniSyntaxError, OmniThrow, OmniTypeError)
from .interp import Environment, Interpreter
from .lexer import tokenize
from .parser import parse
from .stdlib import VERSION

__version__ = VERSION

__all__ = [
    "Interpreter", "Environment", "run_source", "run_file", "parse", "tokenize",
    "OmniError", "OmniSyntaxError", "OmniLexError", "OmniRuntimeError",
    "OmniTypeError", "OmniNameError", "OmniThrow", "__version__",
]


def make_interpreter(writer=None, root=".", argv=None, quiet=False,
                     max_steps=None, stdin=None) -> Interpreter:
    interp = Interpreter(writer=writer, root=root, argv=argv or [], quiet=quiet,
                         max_steps=max_steps)
    if stdin is not None:
        interp.stdin = stdin
    interp.load_builtins()
    return interp


def run_source(src: str, path: str = "<program>", writer=None, root: str = ".",
               argv=None, interp: Interpreter | None = None):
    """Execute OmniScript source text."""
    interp = interp or make_interpreter(writer=writer, root=root, argv=argv)
    interp.run_source(src, path)
    return interp


def run_file(path: str, writer=None, argv=None, interp: Interpreter | None = None):
    """Execute an OmniScript file."""
    import os
    with open(path, "r", encoding="utf-8") as fh:
        src = fh.read()
    return run_source(src, os.path.abspath(path), writer=writer,
                      root=os.path.dirname(os.path.abspath(path)) or ".",
                      argv=argv, interp=interp)
