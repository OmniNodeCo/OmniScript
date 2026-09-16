"""What draw() does: a window on screen when there is one, a PNG when there is not.

    draw(window(640, 400, "Demo"),
         rect(0, 0, 640, 60, "#161b22"),
         text(20, 20, "Hello", white, 18),
         button(20, 300, 140, 36, "List files", cmd("ls -la")),
         save("hello.png"))

With `save(...)` in the list, draw() writes that file and does nothing else.
Without it, a real window opens when the machine has a display -- buttons and
all, and clicking one runs the command it was given. With no display, the same
picture is written to `drawing.png`, so a server or a CI runner still gets
something to look at.

Everything here is drawn in this file: a bytearray of pixels, shapes on it, and
zlib to make a PNG. There is nothing to install.
"""

from __future__ import annotations

import os
import re
import struct
import sys
import zlib
from dataclasses import dataclass, field

DEFAULT_WIDTH = 640
DEFAULT_HEIGHT = 400
DEFAULT_TITLE = "OmniScript"
DEFAULT_BACKGROUND = "#0d1117"
DEFAULT_INK = "#58a6ff"
FALLBACK_FILE = "drawing.png"
BIGGEST = 8000

NAMED = {
    "black": "#000000", "white": "#ffffff", "red": "#e5534b", "green": "#2ea043",
    "blue": "#58a6ff", "yellow": "#f2cc60", "orange": "#f0883e", "purple": "#a371f7",
    "pink": "#ff7b9c", "cyan": "#39c5cf", "teal": "#1f6feb", "navy": "#0d1b3d",
    "grey": "#8b949e", "gray": "#8b949e", "silver": "#c9d1d9", "gold": "#e3b341",
    "brown": "#8b5a2b", "lime": "#7ee787", "maroon": "#8b2635", "olive": "#7d8c34",
}

# A 3x5 font, one row per line of the pattern. Small on purpose: it is only used
# for the PNG, because a window on screen has real fonts to draw with.
FONT = {
    "A": "111/101/111/101/101", "B": "110/101/110/101/110", "C": "111/100/100/100/111",
    "D": "110/101/101/101/110", "E": "111/100/111/100/111", "F": "111/100/111/100/100",
    "G": "111/100/101/101/111", "H": "101/101/111/101/101", "I": "111/010/010/010/111",
    "J": "001/001/001/101/111", "K": "101/101/110/101/101", "L": "100/100/100/100/111",
    "M": "101/111/111/101/101", "N": "110/101/101/101/101", "O": "111/101/101/101/111",
    "P": "111/101/111/100/100", "Q": "111/101/101/111/001", "R": "111/101/110/101/101",
    "S": "111/100/111/001/111", "T": "111/010/010/010/010", "U": "101/101/101/101/111",
    "V": "101/101/101/101/010", "W": "101/101/111/111/101", "X": "101/101/010/101/101",
    "Y": "101/101/111/010/010", "Z": "111/001/010/100/111",
    "0": "111/101/101/101/111", "1": "010/110/010/010/111", "2": "111/001/111/100/111",
    "3": "111/001/111/001/111", "4": "101/101/111/001/001", "5": "111/100/111/001/111",
    "6": "111/100/111/101/111", "7": "111/001/010/010/010", "8": "111/101/111/101/111",
    "9": "111/101/111/001/111",
    " ": "000/000/000/000/000", ".": "000/000/000/000/010", ",": "000/000/000/010/100",
    "!": "010/010/010/000/010", "?": "111/001/011/000/010", ":": "000/010/000/010/000",
    ";": "000/010/000/010/100", "-": "000/000/111/000/000", "_": "000/000/000/000/111",
    "+": "000/010/111/010/000", "=": "000/111/000/111/000", "(": "010/100/100/100/010",
    ")": "010/001/001/001/010", "/": "001/001/010/100/100", "\\": "100/100/010/001/001",
    "'": "010/010/000/000/000", '"': "101/101/000/000/000", "*": "101/010/111/010/101",
    "#": "101/111/101/111/101", "%": "101/001/010/100/101", "<": "001/010/100/010/001",
    ">": "100/010/001/010/100", "[": "110/100/100/100/110", "]": "011/001/001/001/011",
    "$": "111/110/111/011/111", "&": "010/101/010/101/011", "@": "111/101/111/100/111",
}

BUTTON_FACE = "#21262d"
BUTTON_EDGE = "#8b949e"
BUTTON_INK = "#ffffff"


class DrawError(Exception):
    """Something draw() was asked for that it cannot do, on a given line."""

    def __init__(self, message: str, line: int = 0):
        super().__init__(message)
        self.message = message
        self.line = line


@dataclass
class Element:
    """One thing in a draw() list, as it was written."""

    kind: str
    args: list = field(default_factory=list)
    action: object = None          # a button's command, kept to run when clicked
    line: int = 0


# --------------------------------------------------------------------- colours
def rgb(value, line: int = 0, default: str = DEFAULT_INK) -> tuple:
    if value is None:
        value = default
    text = str(value).strip().lower()
    if text in NAMED:
        text = NAMED[text]
    if re.fullmatch(r"#[0-9a-f]{6}", text):
        return (int(text[1:3], 16), int(text[3:5], 16), int(text[5:7], 16))
    if re.fullmatch(r"#[0-9a-f]{3}", text):
        return tuple(int(char * 2, 16) for char in text[1:])
    raise DrawError(f"'{value}' is not a colour: use #rrggbb, or one of "
                    f"{', '.join(sorted(NAMED))}", line)


def number(args: list, index: int, default, what: str, line: int = 0):
    if index >= len(args) or args[index] is None or args[index] == "":
        return default
    try:
        return float(args[index])
    except (TypeError, ValueError):
        raise DrawError(f"{what} has to be a number, not '{args[index]}'", line) from None


def whole(args: list, index: int, default: int, what: str, line: int = 0) -> int:
    value = int(number(args, index, default, what, line))
    if not -BIGGEST <= value <= BIGGEST:
        raise DrawError(f"{what} has to be between -{BIGGEST} and {BIGGEST}", line)
    return value



# ----------------------------------------------------------------------- the PNG
class Canvas:
    """Pixels, shapes on them, and a PNG at the end. No libraries."""

    def __init__(self, width: int, height: int, background=(13, 17, 23)):
        self.width = max(1, int(width))
        self.height = max(1, int(height))
        self.pixels = bytearray(background * (self.width * self.height))

    def plot(self, x: int, y: int, colour) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            at = (y * self.width + x) * 3
            self.pixels[at:at + 3] = bytes(colour)

    def rect(self, x: int, y: int, width: int, height: int, colour) -> None:
        for row in range(max(0, y), min(self.height, y + height)):
            start = (row * self.width + max(0, x)) * 3
            stop = (row * self.width + min(self.width, x + width)) * 3
            if stop > start:
                self.pixels[start:stop] = bytes(colour) * ((stop - start) // 3)

    def outline(self, x: int, y: int, width: int, height: int, colour) -> None:
        self.rect(x, y, width, 1, colour)
        self.rect(x, y + height - 1, width, 1, colour)
        self.rect(x, y, 1, height, colour)
        self.rect(x + width - 1, y, 1, height, colour)

    def circle(self, cx: int, cy: int, radius: int, colour) -> None:
        radius = max(0, int(radius))
        for y in range(cy - radius, cy + radius + 1):
            for x in range(cx - radius, cx + radius + 1):
                if (x - cx) ** 2 + (y - cy) ** 2 <= radius * radius:
                    self.plot(x, y, colour)

    def line(self, x1: int, y1: int, x2: int, y2: int, colour, width: int = 1) -> None:
        steps = max(abs(int(x2 - x1)), abs(int(y2 - y1)), 1)
        reach = max(1, int(width)) // 2
        for step in range(steps + 1):
            x = int(x1 + (x2 - x1) * step / steps)
            y = int(y1 + (y2 - y1) * step / steps)
            if reach <= 1:
                self.plot(x, y, colour)
            else:
                self.rect(x - reach, y - reach, reach * 2, reach * 2, colour)

    def text(self, x: int, y: int, message: str, colour, size: int = 14) -> None:
        scale = max(1, int(size) // 7)
        for index, char in enumerate(str(message).upper()):
            at = x + index * 4 * scale
            pattern = FONT.get(char)
            if pattern is None:
                if char.strip():
                    self.outline(at, y, 3 * scale, 5 * scale, colour)
                continue
            for row, bits in enumerate(pattern.split("/")):
                for column, bit in enumerate(bits):
                    if bit == "1":
                        self.rect(at + column * scale, y + row * scale, scale, scale,
                                  colour)

    def width_of(self, message: str, size: int = 14) -> int:
        return max(0, len(str(message)) * 4 * max(1, int(size) // 7) - 1)

    def png(self) -> bytes:
        stride = self.width * 3
        raw = bytearray()
        for row in range(self.height):
            raw.append(0)
            raw += self.pixels[row * stride:(row + 1) * stride]

        def chunk(kind: bytes, data: bytes) -> bytes:
            body = kind + data
            return (struct.pack(">I", len(data)) + body
                    + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF))

        return (b"\x89PNG\r\n\x1a\n"
                + chunk(b"IHDR", struct.pack(">IIBBBBB", self.width, self.height,
                                             8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
                + chunk(b"IEND", b""))


# ------------------------------------------------------------------ painting
def paint(elements: list, width: int, height: int, background) -> Canvas:
    canvas = Canvas(width, height, background)
    for element in elements:
        args, line = element.args, element.line
        if element.kind == "rect":
            canvas.rect(whole(args, 0, 0, "rect's x", line), whole(args, 1, 0, "rect's y", line),
                        whole(args, 2, 0, "rect's width", line),
                        whole(args, 3, 0, "rect's height", line),
                        rgb(args[4] if len(args) > 4 else None, line))
        elif element.kind == "circle":
            canvas.circle(whole(args, 0, 0, "circle's x", line),
                          whole(args, 1, 0, "circle's y", line),
                          whole(args, 2, 0, "circle's radius", line),
                          rgb(args[3] if len(args) > 3 else None, line))
        elif element.kind == "line":
            canvas.line(whole(args, 0, 0, "line's x1", line), whole(args, 1, 0, "line's y1", line),
                        whole(args, 2, 0, "line's x2", line), whole(args, 3, 0, "line's y2", line),
                        rgb(args[4] if len(args) > 4 else None, line),
                        whole(args, 5, 1, "line's width", line))
        elif element.kind == "text":
            canvas.text(whole(args, 0, 0, "text's x", line), whole(args, 1, 0, "text's y", line),
                        args[2] if len(args) > 2 else "",
                        rgb(args[3] if len(args) > 3 else None, line),
                        whole(args, 4, 14, "text's size", line))
        elif element.kind == "button":
            _paint_button(canvas, args, line)
    return canvas


def _paint_button(canvas: Canvas, args: list, line: int) -> None:
    x = whole(args, 0, 0, "button's x", line)
    y = whole(args, 1, 0, "button's y", line)
    width = whole(args, 2, 120, "button's width", line)
    height = whole(args, 3, 32, "button's height", line)
    label = str(args[4]) if len(args) > 4 else "button"
    canvas.rect(x, y, width, height, rgb(BUTTON_FACE, line))
    canvas.outline(x, y, width, height, rgb(BUTTON_EDGE, line))
    size = max(8, min(height - 8, 14))
    canvas.text(x + max(4, (width - canvas.width_of(label, size)) // 2),
                y + max(2, (height - size) // 2), label, rgb(BUTTON_INK, line), size)


# ------------------------------------------------------------------- a window
def has_display() -> bool:
    if sys.platform.startswith("linux"):
        return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    return sys.platform in ("darwin", "win32")


def show_window(elements: list, width: int, height: int, title: str, background,
                on_click, say) -> bool:
    """A real window with real buttons, or False when this machine has none."""
    if not has_display():
        return False
    try:
        import tkinter as tk
    except ImportError:
        return False
    try:
        root = tk.Tk()
    except Exception:                                  # noqa: BLE001 - no display, no window
        return False

    hexcol = "#%02x%02x%02x" % background
    root.title(title)
    root.geometry(f"{width}x{height}")
    root.configure(bg=hexcol)
    surface = tk.Canvas(root, width=width, height=height, bg=hexcol,
                        highlightthickness=0)
    surface.pack(fill="both", expand=True)

    def click(element):
        if on_click is None or element.action is None:
            return
        say(f"clicked '{_label(element)}'")
        on_click(element.action)

    for element in elements:
        kind, args, line = element.kind, element.args, element.line
        if kind == "rect":
            x, y = whole(args, 0, 0, "rect's x", line), whole(args, 1, 0, "rect's y", line)
            w, h = whole(args, 2, 0, "rect's width", line), whole(args, 3, 0, "rect's height", line)
            surface.create_rectangle(x, y, x + w, y + h, width=0,
                                     fill="#%02x%02x%02x" % rgb(args[4] if len(args) > 4 else None, line))
        elif kind == "circle":
            cx, cy = whole(args, 0, 0, "circle's x", line), whole(args, 1, 0, "circle's y", line)
            r = whole(args, 2, 0, "circle's radius", line)
            surface.create_oval(cx - r, cy - r, cx + r, cy + r, width=0,
                                fill="#%02x%02x%02x" % rgb(args[3] if len(args) > 3 else None, line))
        elif kind == "line":
            points = [whole(args, i, 0, f"line's point {i}", line) for i in range(4)]
            surface.create_line(*points, fill="#%02x%02x%02x" % rgb(args[4] if len(args) > 4 else None, line),
                                width=whole(args, 5, 1, "line's width", line))
        elif kind == "text":
            size = whole(args, 4, 14, "text's size", line)
            surface.create_text(whole(args, 0, 0, "text's x", line),
                                whole(args, 1, 0, "text's y", line), anchor="nw",
                                text=str(args[2]) if len(args) > 2 else "",
                                fill="#%02x%02x%02x" % rgb(args[3] if len(args) > 3 else None, line),
                                font=("Helvetica", max(6, int(size * 0.6))))
        elif kind == "button":
            x = whole(args, 0, 0, "button's x", line)
            y = whole(args, 1, 0, "button's y", line)
            widget = tk.Button(root, text=_label(element), command=lambda e=element: click(e),
                               bg=BUTTON_FACE, fg=BUTTON_INK, activebackground=BUTTON_EDGE,
                               activeforeground=BUTTON_INK, relief="flat", bd=0)
            surface.create_window(x, y, anchor="nw", window=widget,
                                  width=whole(args, 2, 120, "button's width", line),
                                  height=whole(args, 3, 32, "button's height", line))

    root.mainloop()
    return True


def _label(element: Element) -> str:
    return str(element.args[4]) if len(element.args) > 4 else "button"


# ------------------------------------------------------------------ the entry
def render(elements: list, cwd: str = ".", say=print, on_click=None):
    """Draw the elements. Returns the PNG it wrote, or None for a window."""
    width, height, title = DEFAULT_WIDTH, DEFAULT_HEIGHT, DEFAULT_TITLE
    background = DEFAULT_BACKGROUND
    save_to = ""
    for element in elements:
        if element.kind == "window":
            args, line = element.args, element.line
            width = whole(args, 0, DEFAULT_WIDTH, "the window's width", line)
            height = whole(args, 1, DEFAULT_HEIGHT, "the window's height", line)
            if len(args) > 2 and args[2] not in (None, ""):
                title = str(args[2])
            if len(args) > 3:
                background = "#%02x%02x%02x" % rgb(args[3], line, DEFAULT_BACKGROUND)
        elif element.kind == "save":
            if not element.args:
                raise DrawError("save() needs a file name", element.line)
            save_to = str(element.args[0])
    if width < 1 or height < 1:
        raise DrawError(f"a window cannot be {width}x{height}", 0)

    ink = rgb(background)
    if save_to:
        return _write(cwd, save_to, paint(elements, width, height, ink), say)
    if show_window(elements, width, height, title, ink, on_click, say):
        return None
    return _write(cwd, FALLBACK_FILE, paint(elements, width, height, ink), say,
                  note="there is no window here, so ")


def _write(cwd: str, name: str, canvas: Canvas, say, note: str = "") -> str:
    path = name if os.path.isabs(name) else os.path.join(cwd, name)
    parent = os.path.dirname(path)
    try:
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "wb") as handle:
            handle.write(canvas.png())
    except OSError as err:
        raise DrawError(f"could not write {name}: {err}") from err
    say(f"{note}wrote {name} ({canvas.width}x{canvas.height})")
    return path
