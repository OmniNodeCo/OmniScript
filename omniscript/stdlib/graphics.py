"""OmniScript graphics: a small software rasteriser with no dependencies.

    let c = draw(window_size(120, 5390))
    c.rect(10, 10, 100, 40, "steelblue")
    c.text(20, 70, "hello omni")
    c.save("art.png")

Pictures are also written out automatically when the program finishes, so the
three lines above already produce a PNG.
"""

from __future__ import annotations

import math
import os
import struct
import zlib

from ..errors import OmniRuntimeError, OmniTypeError
from ..values import HostObject, NativeFunction, collect_signature, to_string, truthy
from .core import as_int, as_num, omni

# ------------------------------------------------------------------- colours
NAMED_COLORS = {
    "black": (0, 0, 0), "white": (255, 255, 255), "red": (220, 50, 47),
    "green": (42, 161, 52), "blue": (38, 139, 210), "yellow": (255, 213, 79),
    "orange": (255, 140, 0), "purple": (147, 84, 200), "pink": (255, 145, 175),
    "cyan": (42, 195, 222), "magenta": (211, 54, 130), "grey": (131, 148, 150),
    "gray": (131, 148, 150), "silver": (190, 199, 205), "navy": (20, 40, 90),
    "teal": (0, 128, 128), "olive": (128, 128, 0), "maroon": (128, 0, 0),
    "lime": (50, 205, 50), "aqua": (0, 255, 255), "brown": (139, 90, 43),
    "gold": (255, 200, 40), "coral": (255, 127, 80), "salmon": (250, 128, 114),
    "violet": (238, 130, 238), "indigo": (75, 0, 130), "khaki": (240, 230, 140),
    "steelblue": (70, 130, 180), "tomato": (255, 99, 71), "skyblue": (135, 206, 235),
    "seagreen": (46, 139, 87), "slate": (112, 128, 144), "cream": (255, 250, 235),
    "transparent": (0, 0, 0),
}

PALETTE = ["#4e79a7", "#f28e2b", "#e15759", "#76b7b2", "#59a14f",
           "#edc948", "#b07aa1", "#ff9da7", "#9c755f", "#bab0ac"]


def parse_color(value, default=(0, 0, 0, 255)):
    """Accept `"red"`, `"#ff8800"`, `"#f80"`, `[255, 128, 0]`, `0.5` or a map."""
    if value is None:
        return default
    if isinstance(value, bool):
        return (255, 255, 255, 255) if value else (0, 0, 0, 255)
    if isinstance(value, (int, float)):
        g = max(0, min(255, int(value)))
        return (g, g, g, 255)
    if isinstance(value, str):
        s = value.strip().lower()
        if s in NAMED_COLORS:
            r, g, b = NAMED_COLORS[s]
            return (int(r), int(g), int(b), 0 if s == "transparent" else 255)
        if s.startswith("#"):
            h = s[1:]
            try:
                if len(h) == 3:
                    return tuple(int(c * 2, 16) for c in h) + (255,)
                if len(h) == 4:
                    return tuple(int(c * 2, 16) for c in h)
                if len(h) == 6:
                    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 255)
                if len(h) == 8:
                    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16),
                            int(h[6:8], 16))
            except ValueError:
                pass
            raise OmniRuntimeError(f"`{value}` is not a colour I know",
                                   hint='use a name like "red", or hex like "#ff8800"')
        if s.startswith("rgb"):
            inner = s[s.find("(") + 1:s.rfind(")")]
            parts = [p.strip() for p in inner.split(",")]
            nums = [float(p.rstrip("%")) * (2.55 if p.endswith("%") else 1)
                    for p in parts]
            while len(nums) < 4:
                nums.append(255)
            return tuple(max(0, min(255, int(n))) for n in nums[:4])
        raise OmniRuntimeError(f"`{value}` is not a colour I know",
                               hint=f'known names include: {", ".join(list(NAMED_COLORS)[:8])}...')
    if isinstance(value, (list, tuple)):
        nums = [as_num(v, "colour channel") for v in value]
        if all(0.0 <= n <= 1.0 for n in nums) and len(nums) >= 3:
            nums = [n * 255 for n in nums]
        while len(nums) < 4:
            nums.append(255)
        return tuple(max(0, min(255, int(n))) for n in nums[:4])
    if isinstance(value, dict):
        r = value.get("r", value.get("red", 0))
        g = value.get("g", value.get("green", 0))
        b = value.get("b", value.get("blue", 0))
        a = value.get("a", value.get("alpha", 255))
        return tuple(max(0, min(255, int(as_num(v, "colour channel"))))
                     for v in (r, g, b, a))
    raise OmniTypeError(f"cannot use {to_string(value)} as a colour")


_COLOR_CACHE: dict = {}


def _norm(color):
    """Accept any colour spelling; always hand back a (r, g, b, a) tuple."""
    if type(color) is tuple and len(color) == 4:
        return color
    if isinstance(color, str):
        cached = _COLOR_CACHE.get(color)
        if cached is None:
            cached = parse_color(color)
            _COLOR_CACHE[color] = cached
        return cached
    return parse_color(color)


def mix(c1, c2, t=0.5):
    a, b = parse_color(c1), parse_color(c2)
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(4))


# ------------------------------------------------------------- 5x7 bitmap font
# Each glyph is five columns; each column is a byte whose low 7 bits are the
# rows of that column, top row first.
_FONT_HEX = """
20:00 00 00 00 00|21:00 00 5f 00 00|22:00 07 00 07 00|23:14 7f 14 7f 14
24:24 2a 7f 2a 12|25:23 13 08 64 62|26:36 49 55 22 50|27:00 05 03 00 00
28:00 1c 22 41 00|29:00 41 22 1c 00|2a:14 08 3e 08 14|2b:08 08 3e 08 08
2c:00 50 30 00 00|2d:08 08 08 08 08|2e:00 60 60 00 00|2f:20 10 08 04 02
30:3e 51 49 45 3e|31:00 42 7f 40 00|32:42 61 51 49 46|33:21 41 45 4b 31
34:18 14 12 7f 10|35:27 45 45 45 39|36:3c 4a 49 49 30|37:01 71 09 05 03
38:36 49 49 49 36|39:06 49 49 29 1e|3a:00 36 36 00 00|3b:00 56 36 00 00
3c:08 14 22 41 00|3d:14 14 14 14 14|3e:00 41 22 14 08|3f:02 01 51 09 06
40:32 49 79 41 3e|41:7e 11 11 11 7e|42:7f 49 49 49 36|43:3e 41 41 41 22
44:7f 41 41 22 1c|45:7f 49 49 49 41|46:7f 09 09 09 01|47:3e 41 49 49 7a
48:7f 08 08 08 7f|49:00 41 7f 41 00|4a:20 40 41 3f 01|4b:7f 08 14 22 41
4c:7f 40 40 40 40|4d:7f 02 0c 02 7f|4e:7f 04 08 10 7f|4f:3e 41 41 41 3e
50:7f 09 09 09 06|51:3e 41 51 21 5e|52:7f 09 19 29 46|53:46 49 49 49 31
54:01 01 7f 01 01|55:3f 40 40 40 3f|56:1f 20 40 20 1f|57:3f 40 38 40 3f
58:63 14 08 14 63|59:07 08 70 08 07|5a:61 51 49 45 43|5b:00 7f 41 41 00
5c:02 04 08 10 20|5d:00 41 41 7f 00|5e:04 02 01 02 04|5f:40 40 40 40 40
60:00 01 02 04 00|61:20 54 54 54 78|62:7f 48 44 44 38|63:38 44 44 44 20
64:38 44 44 48 7f|65:38 54 54 54 18|66:08 7e 09 01 02|67:0c 52 52 52 3e
68:7f 08 04 04 78|69:00 44 7d 40 00|6a:20 40 44 3d 00|6b:7f 10 28 44 00
6c:00 41 7f 40 00|6d:7c 04 18 04 78|6e:7c 08 04 04 78|6f:38 44 44 44 38
70:7c 14 14 14 08|71:08 14 14 18 7c|72:7c 08 04 04 08|73:48 54 54 54 20
74:04 3f 44 40 20|75:3c 40 40 20 7c|76:1c 20 40 20 1c|77:3c 40 30 40 3c
78:44 28 10 28 44|79:0c 50 50 50 3c|7a:44 64 54 4c 44|7b:00 08 36 41 00
7c:00 00 7f 00 00|7d:00 41 36 08 00|7e:08 04 08 10 08
"""

FONT: dict[str, list[int]] = {}
for _entry in _FONT_HEX.replace("\n", "|").split("|"):
    _entry = _entry.strip()
    if not _entry:
        continue
    _code, _cols = _entry.split(":", 1)
    FONT[chr(int(_code, 16))] = [int(x, 16) for x in _cols.split()]

GLYPH_W, GLYPH_H = 5, 7


# ------------------------------------------------------------------- canvas
class Raster:
    """A width x height RGBA pixel buffer."""

    def __init__(self, w: int, h: int, bg=(255, 255, 255, 255)):
        self.w = max(1, int(w))
        self.h = max(1, int(h))
        self.buf = bytearray(self.w * self.h * 4)
        self.fill_all(bg)

    # -- primitives ------------------------------------------------------
    def fill_all(self, color):
        r, g, b, a = _norm(color)
        if a == 255:
            self.buf = bytearray(bytes((r, g, b, a)) * (self.w * self.h))
            return
        for y in range(self.h):
            for x in range(self.w):
                self.blend(x, y, color)

    def blend(self, x: int, y: int, color):
        if not (0 <= x < self.w and 0 <= y < self.h):
            return
        r, g, b, a = _norm(color)
        if a == 0:
            return
        i = (y * self.w + x) * 4
        buf = self.buf
        if a == 255:
            buf[i] = r
            buf[i + 1] = g
            buf[i + 2] = b
            buf[i + 3] = 255
            return
        t = a / 255.0
        buf[i] = int(buf[i] * (1 - t) + r * t)
        buf[i + 1] = int(buf[i + 1] * (1 - t) + g * t)
        buf[i + 2] = int(buf[i + 2] * (1 - t) + b * t)
        buf[i + 3] = 255

    def get(self, x: int, y: int):
        if not (0 <= x < self.w and 0 <= y < self.h):
            return None
        i = (y * self.w + x) * 4
        return [float(self.buf[i]), float(self.buf[i + 1]),
                float(self.buf[i + 2]), float(self.buf[i + 3])]

    def rect(self, x, y, w, h, color, thickness=0):
        x0, y0 = int(x), int(y)
        x1, y1 = int(x + w) - 1, int(y + h) - 1
        if thickness and thickness > 0:
            t = int(thickness)
            for k in range(t):
                self.hline(x0 + k, x1 - k, y0 + k, color)
                self.hline(x0 + k, x1 - k, y1 - k, color)
                self.vline(x0 + k, y0 + k, y1 - k, color)
                self.vline(x1 - k, y0 + k, y1 - k, color)
            return
        for yy in range(max(0, y0), min(self.h, y1 + 1)):
            for xx in range(max(0, x0), min(self.w, x1 + 1)):
                self.blend(xx, yy, color)

    def hline(self, xa, xb, y, color):
        if not (0 <= y < self.h):
            return
        for x in range(max(0, int(xa)), min(self.w, int(xb) + 1)):
            self.blend(x, int(y), color)

    def vline(self, x, ya, yb, color):
        if not (0 <= x < self.w):
            return
        for y in range(max(0, int(ya)), min(self.h, int(yb) + 1)):
            self.blend(int(x), y, color)

    def line(self, x0, y0, x1, y1, color, thickness=1):
        x0, y0, x1, y1 = int(x0), int(y0), int(x1), int(y1)
        t = max(1, int(thickness))
        dx, dy = abs(x1 - x0), abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy
        half = t // 2
        while True:
            if t == 1:
                self.blend(x0, y0, color)
            else:
                for oy in range(-half, t - half):
                    for ox in range(-half, t - half):
                        self.blend(x0 + ox, y0 + oy, color)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x0 += sx
            if e2 < dx:
                err += dx
                y0 += sy

    def circle(self, cx, cy, r, color, thickness=0):
        self.ellipse(cx, cy, r, r, color, thickness)

    def ellipse(self, cx, cy, rx, ry, color, thickness=0):
        cx, cy = float(cx), float(cy)
        rx, ry = abs(float(rx)), abs(float(ry))
        if rx <= 0 or ry <= 0:
            return
        if thickness and thickness > 0:
            for k in range(int(thickness)):
                self._ellipse_ring(cx, cy, rx - k, ry - k, color)
            return
        y = -ry
        while y <= ry:
            span = rx * math.sqrt(max(0.0, 1 - (y * y) / (ry * ry)))
            self.hline(int(cx - span), int(cx + span), int(round(cy + y)), color)
            y += 1

    def _ellipse_ring(self, cx, cy, rx, ry, color):
        if rx <= 0 or ry <= 0:
            return
        steps = max(16, int(2 * math.pi * max(rx, ry)))
        prev = None
        for i in range(steps + 1):
            a = 2 * math.pi * i / steps
            p = (int(round(cx + rx * math.cos(a))), int(round(cy + ry * math.sin(a))))
            if prev:
                self.line(prev[0], prev[1], p[0], p[1], color, 1)
            prev = p

    def polygon(self, points, color, thickness=0):
        pts = [(float(p[0]), float(p[1])) for p in points]
        if len(pts) < 2:
            return
        if thickness and thickness > 0:
            for i in range(len(pts)):
                a, b = pts[i], pts[(i + 1) % len(pts)]
                self.line(a[0], a[1], b[0], b[1], color, int(thickness))
            return
        if len(pts) == 2:
            self.line(pts[0][0], pts[0][1], pts[1][0], pts[1][1], color, 1)
            return
        min_y = max(0, int(math.floor(min(p[1] for p in pts))))
        max_y = min(self.h - 1, int(math.ceil(max(p[1] for p in pts))))
        for y in range(min_y, max_y + 1):
            ys = y + 0.5
            xs = []
            for i in range(len(pts)):
                x1, y1 = pts[i]
                x2, y2 = pts[(i + 1) % len(pts)]
                if (y1 <= ys < y2) or (y2 <= ys < y1):
                    xs.append(x1 + (ys - y1) * (x2 - x1) / (y2 - y1))
            xs.sort()
            for i in range(0, len(xs) - 1, 2):
                self.hline(int(math.ceil(xs[i])), int(math.floor(xs[i + 1])), y, color)

    def text(self, x, y, s, color, scale=1, spacing=1):
        s = to_string(s)
        scale = max(1, int(scale))
        cx = int(x)
        cy = int(y)
        for ch in s:
            glyph = FONT.get(ch) or FONT.get(ch.upper()) or FONT.get("?")
            if ch == "\n":
                cx = int(x)
                cy += (GLYPH_H + 2) * scale
                continue
            if glyph:
                for col, bits in enumerate(glyph):
                    for row in range(GLYPH_H):
                        if bits & (1 << row):
                            px = cx + col * scale
                            py = cy + row * scale
                            if scale == 1:
                                self.blend(px, py, color)
                            else:
                                for oy in range(scale):
                                    for ox in range(scale):
                                        self.blend(px + ox, py + oy, color)
            cx += (GLYPH_W + int(spacing)) * scale
        return cx

    def text_size(self, s, scale=1, spacing=1):
        lines = to_string(s).split("\n")
        width = max((len(l) * (GLYPH_W + int(spacing)) - int(spacing)) * scale
                    for l in lines) if lines else 0
        return [float(max(0, width)), float(len(lines) * (GLYPH_H + 2) * scale - 2 * scale)]

    def gradient(self, x, y, w, h, c1, c2, vertical=True):
        a, b = parse_color(c1), parse_color(c2)
        w, h = int(w), int(h)
        span = h if vertical else w
        if span <= 0:
            return
        for i in range(span):
            t = i / max(1, span - 1)
            col = tuple(int(a[k] + (b[k] - a[k]) * t) for k in range(4))
            if vertical:
                self.hline(int(x), int(x) + w - 1, int(y) + i, col)
            else:
                self.vline(int(x) + i, int(y), int(y) + h - 1, col)

    def blur(self, radius=1):
        r = max(1, int(radius))
        src = self.buf
        w, h = self.w, self.h
        out = bytearray(len(src))
        window = 2 * r + 1
        for y in range(h):
            for x in range(w):
                acc = [0, 0, 0, 0]
                for dy in range(-r, r + 1):
                    yy = min(h - 1, max(0, y + dy))
                    for dx in range(-r, r + 1):
                        xx = min(w - 1, max(0, x + dx))
                        i = (yy * w + xx) * 4
                        for c in range(4):
                            acc[c] += src[i + c]
                i = (y * w + x) * 4
                for c in range(4):
                    out[i + c] = acc[c] // (window * window)
        self.buf = out

    def copy(self):
        clone = Raster(1, 1)
        clone.w, clone.h = self.w, self.h
        clone.buf = bytearray(self.buf)
        return clone

    def paste(self, other, x=0, y=0):
        for oy in range(other.h):
            for ox in range(other.w):
                self.blend(int(x) + ox, int(y) + oy, tuple(other.get(ox, oy)))

    # -- output ----------------------------------------------------------
    def png_bytes(self) -> bytes:
        raw = bytearray()
        stride = self.w * 4
        for y in range(self.h):
            raw.append(0)
            raw += self.buf[y * stride:(y + 1) * stride]

        def chunk(tag: bytes, data: bytes) -> bytes:
            return (struct.pack(">I", len(data)) + tag + data +
                    struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

        ihdr = struct.pack(">IIBBBBB", self.w, self.h, 8, 6, 0, 0, 0)
        return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) +
                chunk(b"IDAT", zlib.compress(bytes(raw), 6)) + chunk(b"IEND", b""))


# ---------------------------------------------------------- OmniScript glue
CANVAS_METHODS: dict[str, NativeFunction] = {}


def canvas_method(fn):
    CANVAS_METHODS[fn.__name__] = collect_signature(fn, fn.__name__,
                                                    (fn.__doc__ or "").strip(),
                                                    takes_interp=False)
    return fn


def _raster(canvas: HostObject) -> Raster:
    if not isinstance(canvas, HostObject) or canvas.type_name != "Canvas":
        raise OmniTypeError(f"expected a canvas, got {to_string(canvas)}",
                            hint="make one with `draw(width, height)`")
    return canvas.data


def make_canvas(w: int, h: int, bg="white", title="OmniScript") -> HostObject:
    r, g, b, a = parse_color(bg)
    raster = Raster(int(w), int(h), (r, g, b, a))
    return HostObject(
        "Canvas",
        methods=dict(CANVAS_METHODS),
        fields={"w": float(raster.w), "h": float(raster.h), "title": to_string(title)},
        display=lambda o: f"<Canvas {o.data.w}x{o.data.h}>",
        data=raster,
    )


@canvas_method
def clear(self, color="white"):
    """wipe the canvas to a colour"""
    _raster(self).fill_all(parse_color(color))
    return self


@canvas_method
def pixel(self, x, y, color="black"):
    """set one pixel"""
    _raster(self).blend(as_int(x, "x"), as_int(y, "y"), parse_color(color))
    return self


@canvas_method
def at(self, x, y):
    """read one pixel as [r, g, b, a]"""
    return _raster(self).get(as_int(x, "x"), as_int(y, "y"))


@canvas_method
def rect(self, x, y, width, height, color="black", filled=True, thickness=1.0):
    """draw a rectangle"""
    _raster(self).rect(as_num(x, "x"), as_num(y, "y"), as_num(width, "width"),
                       as_num(height, "height"), parse_color(color),
                       0 if truthy(filled) else as_int(thickness, "thickness"))
    return self


@canvas_method
def rounded_rect(self, x, y, width, height, radius=6.0, color="black", filled=True):
    """draw a rectangle with rounded corners"""
    ras = _raster(self)
    x, y, width, height = as_num(x), as_num(y), as_num(width), as_num(height)
    r = min(as_num(radius), width / 2, height / 2)
    col = parse_color(color)
    if truthy(filled):
        ras.rect(x + r, y, width - 2 * r, height, col)
        ras.rect(x, y + r, width, height - 2 * r, col)
        for cx, cy in ((x + r, y + r), (x + width - r, y + r),
                       (x + r, y + height - r), (x + width - r, y + height - r)):
            ras.circle(cx, cy, r, col)
    else:
        ras.line(x + r, y, x + width - r, y, col)
        ras.line(x + r, y + height, x + width - r, y + height, col)
        ras.line(x, y + r, x, y + height - r, col)
        ras.line(x + width, y + r, x + width, y + height - r, col)
        ras._ellipse_ring(x + r, y + r, r, r, col)
        ras._ellipse_ring(x + width - r, y + r, r, r, col)
        ras._ellipse_ring(x + r, y + height - r, r, r, col)
        ras._ellipse_ring(x + width - r, y + height - r, r, r, col)
    return self


@canvas_method
def circle(self, x, y, radius, color="black", filled=True, thickness=1.0):
    """draw a circle"""
    _raster(self).circle(as_num(x, "x"), as_num(y, "y"), as_num(radius, "radius"),
                         parse_color(color),
                         0 if truthy(filled) else as_int(thickness, "thickness"))
    return self


@canvas_method
def ellipse(self, x, y, rx, ry, color="black", filled=True, thickness=1.0):
    """draw an oval"""
    _raster(self).ellipse(as_num(x), as_num(y), as_num(rx), as_num(ry),
                          parse_color(color),
                          0 if truthy(filled) else as_int(thickness, "thickness"))
    return self


@canvas_method
def line(self, x1, y1, x2, y2, color="black", thickness=1.0):
    """draw a straight line"""
    _raster(self).line(as_num(x1), as_num(y1), as_num(x2), as_num(y2),
                       parse_color(color), max(1, as_int(thickness, "thickness")))
    return self


@canvas_method
def poly(self, points, color="black", filled=True, thickness=1.0, close=True):
    """draw a polygon from a list of [x, y] points"""
    from ..interp import Interpreter
    pts = [list(p) for p in Interpreter.current().iterate(points)]
    ras = _raster(self)
    col = parse_color(color)
    if truthy(filled):
        ras.polygon(pts, col)
    else:
        ras.polygon(pts, col, max(1, as_int(thickness, "thickness")))
    return self


@canvas_method
def triangle(self, x1, y1, x2, y2, x3, y3, color="black", filled=True):
    """draw a triangle"""
    _raster(self).polygon([[as_num(x1), as_num(y1)], [as_num(x2), as_num(y2)],
                           [as_num(x3), as_num(y3)]], parse_color(color),
                          0 if truthy(filled) else 1)
    return self


@canvas_method
def text(self, x, y, content, color="black", size=1.0, spacing=1.0):
    """draw text using the built-in bitmap font"""
    _raster(self).text(as_num(x), as_num(y), content, parse_color(color),
                       max(1, as_int(size, "size")), max(0, as_int(spacing, "spacing")))
    return self


@canvas_method
def text_size(self, content, size=1.0, spacing=1.0):
    """how much room some text needs: [width, height]"""
    return _raster(self).text_size(content, max(1, as_int(size, "size")),
                                   max(0, as_int(spacing, "spacing")))


@canvas_method
def fill(self, x, y, color="black"):
    """flood-fill an area, starting from one pixel"""
    ras = _raster(self)
    sx, sy = as_int(x, "x"), as_int(y, "y")
    target = ras.get(sx, sy)
    if target is None:
        return self
    replacement = list(parse_color(color))
    if target == replacement:
        return self
    stack = [(sx, sy)]
    seen = set()
    while stack:
        cx, cy = stack.pop()
        if not (0 <= cx < ras.w and 0 <= cy < ras.h):
            continue
        if (cx, cy) in seen:
            continue
        seen.add((cx, cy))
        if ras.get(cx, cy) != target:
            continue
        ras.blend(cx, cy, tuple(replacement))
        stack.extend([(cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)])
    return self


@canvas_method
def gradient(self, x, y, width, height, start="white", end="black", vertical=True):
    """fill a rectangle with a smooth colour transition"""
    _raster(self).gradient(as_num(x), as_num(y), as_num(width), as_num(height),
                           start, end, truthy(vertical))
    return self


@canvas_method
def blur(self, radius=1.0):
    """soften the whole picture"""
    _raster(self).blur(as_int(radius, "radius"))
    return self


@canvas_method
def grid(self, step=10.0, color="#00000022", thickness=1.0):
    """draw graph paper over the canvas"""
    ras = _raster(self)
    s = max(1, as_int(step, "step"))
    col = parse_color(color)
    t = max(1, as_int(thickness, "thickness"))
    for x in range(0, ras.w, s):
        ras.line(x, 0, x, ras.h - 1, col, t)
    for y in range(0, ras.h, s):
        ras.line(0, y, ras.w - 1, y, col, t)
    return self


@canvas_method
def border(self, color="black", thickness=1.0):
    """draw a frame around the edges"""
    ras = _raster(self)
    ras.rect(0, 0, ras.w, ras.h, parse_color(color), max(1, as_int(thickness, "thickness")))
    return self


@canvas_method
def copy(self):
    """an independent duplicate of this canvas"""
    clone = _raster(self).copy()
    out = make_canvas(clone.w, clone.h)
    out.data = clone
    return out


@canvas_method
def paste(self, other, x=0.0, y=0.0):
    """draw another canvas on top of this one"""
    _raster(self).paste(_raster(other), as_num(x), as_num(y))
    return self


@canvas_method
def save(self, path=None):
    """write a PNG; returns the path it used"""
    from ..interp import Interpreter
    interp = Interpreter.current()
    target = to_string(path) if path is not None else interp.next_picture_path()
    os.makedirs(os.path.dirname(os.path.abspath(target)) or ".", exist_ok=True)
    with open(target, "wb") as fh:
        fh.write(_raster(self).png_bytes())
    self.fields["saved"] = target
    if not interp.quiet:
        r = _raster(self)
        interp.out(f"picture saved to {os.path.abspath(target)} ({r.w}x{r.h})")
    return target


@canvas_method
def show(self, path=None):
    """save the picture and announce where it went"""
    return save(self, path)


@canvas_method
def to_base64(self):
    """the PNG as base64 text, ready to embed in a web page"""
    import base64
    return base64.b64encode(_raster(self).png_bytes()).decode("ascii")


@canvas_method
def data_url(self):
    """a `data:image/png;base64,...` URL"""
    return "data:image/png;base64," + to_base64(self)


@omni("window_size")
def _window_size(interp, width, height):
    """window_size(120, 5390) -- describe a drawing surface without making it yet."""
    w, h = as_int(width, "width"), as_int(height, "height")
    if w <= 0 or h <= 0:
        raise OmniRuntimeError("a window needs a positive width and height")
    return HostObject("Size", fields={"w": float(w), "h": float(h)},
                      display=lambda o: f"<Size {int(o.fields['w'])}x{int(o.fields['h'])}>",
                      data=(w, h))


@omni("window", alias=("canvas", "image", "picture"))
def _window(interp, width, height, bg="white", title="OmniScript"):
    """window(120, 5390) -- make a drawing surface you can draw on."""
    if isinstance(width, HostObject) and width.type_name == "Size":
        width, height = width.data
    if height is None:
        raise OmniRuntimeError("window() needs both a width and a height")
    canvas = make_canvas(as_int(width, "width"), as_int(height, "height"), bg, title)
    _track(interp, canvas)
    return canvas


@omni("draw")
def _draw(interp, target=None, height=None, bg="white", title="OmniScript", save_to=None):
    """draw(window_size(120, 5390)) -- open a drawing surface.

    Also accepts `draw(120, 5390)`, or `draw(canvas)` to save one you already have.
    Pictures that were never saved are written out when the program finishes.
    """
    if isinstance(target, HostObject) and target.type_name == "Canvas":
        return save(target, save_to)
    if isinstance(target, HostObject) and target.type_name == "Size":
        w, h = target.data
    elif target is None:
        w, h = 640, 480
    else:
        w = as_int(target, "width")
        if height is None:
            raise OmniRuntimeError("draw() needs a height too, e.g. draw(120, 5390)")
        h = as_int(height, "height")
    canvas = make_canvas(w, h, bg, title)
    _track(interp, canvas)
    return canvas


def _track(interp, canvas):
    if not hasattr(interp, "canvases"):
        interp.canvases = []
    interp.canvases.append(canvas)


@omni("rgb")
def _rgb(interp, r, g, b, a=255.0):
    """rgb(255, 128, 0) -- build a colour from channels."""
    return [float(as_int(r, "r")), float(as_int(g, "g")), float(as_int(b, "b")),
            float(as_int(a, "a"))]


@omni("hsl")
def _hsl(interp, hue, saturation, lightness, alpha=255.0):
    """hsl(210, 0.7, 0.5) -- build a colour from hue, saturation and lightness."""
    import colorsys
    r, g, b = colorsys.hls_to_rgb((as_num(hue, "hue") % 360) / 360.0,
                                  as_num(lightness, "lightness"),
                                  as_num(saturation, "saturation"))
    return [r * 255, g * 255, b * 255, float(as_int(alpha, "alpha"))]


@omni("mix_colors", alias=("blend_colors",))
def _mix_colors(interp, c1, c2, t=0.5):
    """mix_colors("red", "white", 0.3) -- a colour between two others."""
    return list(mix(c1, c2, as_num(t, "t")))


@omni("palette")
def _palette(interp, index=0.0):
    """palette(0) -- a ready-made colour from the built-in chart palette."""
    return PALETTE[as_int(index, "index") % len(PALETTE)]


@omni("save_picture", alias=("save_image",))
def _save_picture(interp, canvas, path=None):
    """save_picture(canvas, "art.png") -- write a canvas to disk."""
    return save(canvas, path)


# ------------------------------------------------------------------- charts
def _axis_frame(ras: Raster, pad_left, pad_top, pad_right, pad_bottom, title,
                axis_color="#c9c9c9", text_color="#333333"):
    ras.line(pad_left, pad_top, pad_left, ras.h - pad_bottom, axis_color, 1)
    ras.line(pad_left, ras.h - pad_bottom, ras.w - pad_right, ras.h - pad_bottom,
             axis_color, 1)
    if title:
        tw, _ = ras.text_size(title, 2)
        ras.text(max(pad_left, (ras.w - tw) // 2), 8, title, text_color, 2)


@omni("chart")
def _chart(interp, data, kind="line", title=None, labels=None, width=640.0,
           height=360.0, color=None, bg="white", show_values=False):
    """chart([3, 1, 4, 1, 5], kind: "bar", title: "Digits") -- draw a chart.

    `data` can be a list of numbers, a map of label -> number, or a list of
    maps with `x`/`y` keys. `kind` is "line", "bar", "area", "scatter" or "pie".
    """
    from ..interp import Interpreter
    values, names = _chart_series(Interpreter.current(), data, labels)
    if not values:
        raise OmniRuntimeError("chart() needs at least one value")
    w, h = max(24, as_int(width, "width")), max(20, as_int(height, "height"))
    canvas = make_canvas(w, h, bg, to_string(title or "chart"))
    ras = canvas.data
    k = to_string(kind).lower()
    base = color or PALETTE[0]

    pad_l, pad_r, pad_t, pad_b = 46, 18, 34 if title else 16, 30
    _axis_frame(ras, pad_l, pad_t, pad_r, pad_b, to_string(title) if title else "")

    lo = min(0.0, min(values))
    hi = max(values)
    if hi == lo:
        hi = lo + 1
    plot_w = ras.w - pad_l - pad_r
    plot_h = ras.h - pad_t - pad_b

    def ypos(v):
        return pad_t + plot_h - (v - lo) / (hi - lo) * plot_h

    if k in ("bar", "column", "histogram"):
        n = len(values)
        slot = plot_w / n
        bar_w = max(1.0, slot * 0.68)
        zero = ypos(max(lo, 0.0))
        for i, v in enumerate(values):
            x = pad_l + i * slot + (slot - bar_w) / 2
            top = ypos(v)
            col = parse_color(PALETTE[i % len(PALETTE)] if color is None else base)
            ras.rect(x, min(top, zero), bar_w, abs(top - zero) or 1, col)
            if truthy(show_values):
                label = _short(v)
                ras.text(x + bar_w / 2 - len(label) * 3, min(top, zero) - 10,
                         label, "#333333", 1)
    elif k in ("pie", "donut"):
        total = sum(abs(v) for v in values) or 1.0
        cx, cy = ras.w // 2, pad_t + plot_h // 2
        radius = min(plot_w, plot_h) / 2 - 6
        angle = -math.pi / 2
        for i, v in enumerate(values):
            sweep = 2 * math.pi * abs(v) / total
            pts = [(cx, cy)]
            steps = max(6, int(sweep * radius))
            for s in range(steps + 1):
                a = angle + sweep * s / steps
                pts.append((cx + radius * math.cos(a), cy + radius * math.sin(a)))
            ras.polygon(pts, parse_color(PALETTE[i % len(PALETTE)]))
            angle += sweep
    else:
        n = len(values)
        pts = []
        for i, v in enumerate(values):
            x = pad_l + (plot_w * (i / max(1, n - 1)) if n > 1 else plot_w / 2)
            pts.append((x, ypos(v)))
        col = parse_color(base)
        if k == "area":
            filled = list(pts) + [(pts[-1][0], ypos(max(lo, 0))),
                                  (pts[0][0], ypos(max(lo, 0)))]
            ras.polygon(filled, parse_color(mix(base, bg, 0.75)))
        if k == "scatter":
            for x, y in pts:
                ras.circle(x, y, 3, col)
        else:
            for i in range(len(pts) - 1):
                ras.line(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1], col, 2)
            for x, y in pts:
                ras.circle(x, y, 2.5, col)

    # y-axis ticks
    for i in range(5):
        v = lo + (hi - lo) * i / 4
        y = ypos(v)
        ras.line(pad_l - 4, y, pad_l, y, "#999999", 1)
        label = _short(v)
        ras.text(max(2, pad_l - 6 - len(label) * 6), y - 3, label, "#666666", 1)

    # x-axis labels
    if names:
        step = max(1, len(names) // max(1, plot_w // 40))
        for i in range(0, len(names), step):
            x = pad_l + (plot_w * (i / max(1, len(values) - 1))
                         if k not in ("bar", "column", "histogram") and len(values) > 1
                         else plot_w * (i + 0.5) / len(values))
            label = to_string(names[i])[:10]
            ras.text(x - len(label) * 3, ras.h - pad_b + 6, label, "#666666", 1)

    _track(interp, canvas)
    return canvas


def _short(v: float) -> str:
    if abs(v) >= 1_000_000:
        return f"{v / 1_000_000:.1f}M"
    if abs(v) >= 10_000:
        return f"{v / 1000:.1f}k"
    if float(v).is_integer():
        return str(int(v))
    return f"{v:.2f}".rstrip("0").rstrip(".")


def _chart_series(interp, data, labels):
    values, names = [], []
    if isinstance(data, dict):
        for k, v in data.items():
            names.append(str(k))
            values.append(as_num(v, "chart value"))
        return values, names
    items = interp.iterate(data)
    for item in items:
        if isinstance(item, dict):
            y = item.get("y", item.get("value", item.get("count")))
            x = item.get("x", item.get("label", item.get("name")))
            values.append(as_num(y, "chart value"))
            names.append(to_string(x) if x is not None else "")
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            values.append(as_num(item[1], "chart value"))
            names.append(to_string(item[0]))
        else:
            values.append(as_num(item, "chart value"))
            names.append("")
    if labels is not None:
        names = [to_string(l) for l in interp.iterate(labels)]
    if all(n == "" for n in names):
        names = []
    return values, names


@omni("sparkline")
def _sparkline(interp, data, width=200.0, height=40.0, color=None):
    """sparkline([1,4,2,8]) -- a tiny chart with no axes."""
    from ..interp import Interpreter
    values, _ = _chart_series(Interpreter.current(), data, None)
    canvas = make_canvas(max(8, as_int(width)), max(6, as_int(height)), "white")
    ras = canvas.data
    if not values:
        return canvas
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1
    pts = [(i * (ras.w - 2) / max(1, len(values) - 1) + 1,
            ras.h - 2 - (v - lo) / span * (ras.h - 4)) for i, v in enumerate(values)]
    col = parse_color(color or PALETTE[0])
    for i in range(len(pts) - 1):
        ras.line(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1], col, 1)
    _track(interp, canvas)
    return canvas


@omni("progress_bar")
def _progress_bar(interp, fraction, width=300.0, height=22.0, color=None, label=None):
    """progress_bar(0.65, label: "downloading") -- a filled bar."""
    canvas = make_canvas(max(20, as_int(width)), max(8, as_int(height)), "#eeeeee")
    ras = canvas.data
    frac = max(0.0, min(1.0, as_num(fraction, "fraction")))
    ras.rect(0, 0, ras.w * frac, ras.h, parse_color(color or "#59a14f"))
    ras.rect(0, 0, ras.w, ras.h, parse_color("#bbbbbb"), thickness=1)
    if label:
        tw, th = ras.text_size(label, 1)
        ras.text((ras.w - tw) / 2, (ras.h - th) / 2, label, "#222222", 1)
    _track(interp, canvas)
    return canvas
