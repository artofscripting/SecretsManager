#!/usr/bin/env python3
"""Build the harbor-cli Linux binary via PyInstaller.

Run this on Linux. The output executable will be placed at dist/harbor-cli.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys


def main() -> int:
    here = pathlib.Path(__file__).resolve().parent
    spec = here / "HarborCLI.spec"

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--clean",
        "--noconfirm",
        str(spec.name),
    ]

    completed = subprocess.run(cmd, cwd=here, check=False)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
