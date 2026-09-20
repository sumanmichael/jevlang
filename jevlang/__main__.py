"""python -m jevlang [--show] file.jev [args...]"""

import sys
from pathlib import Path

from jevlang.loader import load_file
from jevlang.transform import transform


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    show = False
    if argv and argv[0] == "--show":
        show = True
        argv.pop(0)
    if not argv:
        print("usage: python -m jevlang [--show] file.jev [args...]", file=sys.stderr)
        return 2
    path = argv[0]
    if show:
        sys.stdout.write(transform(Path(path).read_text(), path))
        return 0
    sys.argv = argv
    sys.path.insert(0, str(Path(path).resolve().parent))
    load_file(path, "__main__")
    return 0


if __name__ == "__main__":
    sys.exit(main())
