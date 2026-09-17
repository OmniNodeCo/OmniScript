"""OmniScript: four commands to draw with, and Python when you need it.

    import math                   # imports work like Python
    from math import sqrt

    draw(window(640, 400, "Demo"), text(20, 20, "Hello"), save("hi.png"))
    draw_gui.window_size(640, 400, "Demo")
    draw_gui.button(pos=(20, 300), text="List files", action=cmd("ls"))
    draw_gui()                    # show the window

That is the drawing side. cmd(), file() and python() are still there for
shell commands, files and anything else.
"""

from .language import Interpreter, OmniScriptError

VERSION = "1.1.1"
__version__ = VERSION          # what packaging tools and the installers look for

__all__ = ["VERSION", "run", "Interpreter", "OmniScriptError"]


def run(source, name="<input>", writer=None, cwd=None):
    """Run OmniScript source; raise OmniScriptError if it does not."""
    Interpreter(writer=writer, cwd=cwd).run(source, name)
