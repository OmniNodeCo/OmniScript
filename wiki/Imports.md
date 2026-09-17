# Imports

Imports work like Python — because they *are* Python imports, done once at the
top and then waiting for you inside `python()`.

```python
import math
import os as operating_system
import os, sys
from math import sqrt
from math import floor as f
from os.path import join as pjoin
from math import *

python("print(math.floor(2.9))")       # 2
python("print(sqrt(144))")             # 12.0
python("print(operating_system.name)") # posix / nt
python("print(pjoin('a', 'b'))")       # a/b
```

## Rules

- Any import enables `python()`. With no import at all, `python()` points you
  at `import python`.
- `import python` still works exactly as before: it enables `python()` and
  imports nothing (there is no module by that name).
- Whatever you import is already bound in `python()`'s namespace — no need to
  import it twice. (Importing again inside the string still works.)
- `from x import *` binds the public names (`__all__` when the module has one).
- A bad import fails fast and says why:

```
-e:1: could not import 'no_such_module_xyz': No module named 'no_such_module_xyz'
-e:1: 'math' has no 'no_such_name_xyz' to import
```

([examples/07_imports.omni](../examples/07_imports.omni) runs every form.)
