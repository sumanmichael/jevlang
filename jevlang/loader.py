"""Import hook and file runner for .jev sources."""

import importlib.abc
import importlib.util
import sys
from pathlib import Path

from jevlang import runtime
from jevlang.transform import transform

SUFFIX = ".jev"


def _compile(path):
    source = Path(path).read_text()
    return compile(transform(source, str(path)), str(path), "exec")


class JevLoader(importlib.abc.Loader):
    def __init__(self, path):
        self.path = path

    def exec_module(self, module):
        module.__dict__["__jev__"] = runtime
        exec(_compile(self.path), module.__dict__)


class JevFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        name = fullname.rpartition(".")[2]
        for entry in path or sys.path:
            candidate = Path(entry or ".") / f"{name}{SUFFIX}"
            if candidate.is_file():
                return importlib.util.spec_from_file_location(
                    fullname, str(candidate), loader=JevLoader(str(candidate))
                )
        return None


_finder = JevFinder()


def install():
    if _finder not in sys.meta_path:
        sys.meta_path.append(_finder)


def load_file(path, module_name="__main__"):
    """Run a .jev file as a fresh module and return it."""
    import types

    module = types.ModuleType(module_name)
    module.__file__ = str(path)
    module.__dict__["__jev__"] = runtime
    sys.modules[module_name] = module
    try:
        exec(_compile(path), module.__dict__)
    except BaseException:
        # same as importlib: a module that failed to execute must not stay cached
        sys.modules.pop(module_name, None)
        raise
    return module
