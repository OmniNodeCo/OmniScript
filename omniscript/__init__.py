"""OmniScript: four commands, and Python when you need it.

    import python                 # the escape hatch

    draw(window(640, 400, "Demo"), text(20, 20, "Hello"), button(..., cmd("ls")))
    cmd("tree /f")                # a shell command
    file(create, "a.txt", "hi")   # create, edit, delete
    python("print(6 * 7)")        # only after `import python`

That is the whole language. A program is a list of commands, and each command
says what it did.
"""

from .language import Interpreter, OmniScriptError

VERSION = "1.0.0"

__all__ = ["VERSION", "run", "Interpreter", "OmniScriptError"]


def run(source, name="<input>", writer=None, cwd=None):
    """Run OmniScript source; raise OmniScriptError if it does not."""
    Interpreter(writer=writer, cwd=cwd).run(source, name)
