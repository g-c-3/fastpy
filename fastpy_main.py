"""
fastpy_main.py — pip install entry point shim
=============================================
When FastPy is installed via `pip install fastpy`, the CLI entry point
`fastpy = "fastpy_main:main"` calls this module.

When running from the project root (development mode), `python main.py`
is used directly. Both paths converge on the same `main()` function.
"""

import sys
import os

# When installed via pip, main.py is in the same directory as this file.
# Add it to sys.path so it can be imported directly.
_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)

from main import main  # noqa: E402


if __name__ == "__main__":
    sys.exit(main())
