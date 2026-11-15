"""Make ``src/`` importable when the package is not installed (test convenience)."""

import pathlib
import sys

SRC = pathlib.Path(__file__).parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
