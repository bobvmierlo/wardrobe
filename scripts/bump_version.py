#!/usr/bin/env python3
"""Read or update the single version source at backend/app/_version.py.

Used by the release workflow:
  * ``python3 scripts/bump_version.py v1.2.3``  -> writes __version__ = "1.2.3"
  * ``python3 scripts/bump_version.py --get``    -> prints the current version

A leading "v" on the given version is stripped, mirroring the release tag.
"""
from __future__ import annotations

import pathlib
import re
import sys

VERSION_FILE = pathlib.Path(__file__).resolve().parent.parent / "backend" / "app" / "_version.py"
_PATTERN = re.compile(r"""(__version__\s*=\s*)["'][^"']*["']""")


def get_version() -> str:
    m = re.search(r"""__version__\s*=\s*["']([^"']+)["']""", VERSION_FILE.read_text())
    return m.group(1) if m else "0.0.0"


def set_version(version: str) -> str:
    version = version.lstrip("v").strip()
    text = VERSION_FILE.read_text()
    new_text, n = _PATTERN.subn(rf'\g<1>"{version}"', text)
    if n == 0:
        raise SystemExit("Could not find __version__ assignment to update")
    VERSION_FILE.write_text(new_text)
    return version


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "--get"
    if arg == "--get":
        print(get_version())
    else:
        print(set_version(arg))
