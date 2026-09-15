"""`python3 -m omniscript ...` runs the same CLI as `./omni ...`."""
from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
