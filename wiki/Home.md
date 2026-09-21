# OmniScript 1.0.0 — super simple

Three modules:

- `draw` — window, rect, circle, line, text, button, save, show
- `cmd` — run, bg (background)
- `pathlib` — read, write, exists, mkdir, list, Path object

Imports like Python:

```
import draw
from draw import window, rect
import draw as d
from draw import *
```

See [[How-to-use]].

Build:

```
make
./omni examples/01_hello.omni
```
