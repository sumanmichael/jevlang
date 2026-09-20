"""jevlang: Python plus a smart if backed by TypeSafe's Jev model.

Importing this package installs the .jev import hook.
"""

from importlib.metadata import PackageNotFoundError, version

from jevlang.runtime import Choice, Noul, Score, ask, ask_all, choice, noul, score
from jevlang.loader import install

try:
    __version__ = version("jevlang")
except PackageNotFoundError:  # a source tree that was never installed
    __version__ = "0+unknown"

install()

__all__ = ["Choice", "Noul", "Score", "ask", "ask_all", "choice", "noul", "score", "install", "__version__"]
