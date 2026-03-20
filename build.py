#!/usr/bin/env python3
"""
build.py  Build script for Pokemon Toolkit

Produces a single-file executable using PyInstaller.
The result bundles the Python interpreter + all source files so the end user
does not need Python installed.

Run this script on each target platform separately:
  Windows  →  dist/pokemain.exe
  Mac      →  dist/pokemain
  Linux    →  dist/pokemain

The cache folder is NOT bundled — it is created automatically next to the
executable on first run (handled by the frozen-path detection in pkm_cache.py).
Distribute the binary alone; the cache/ folder will appear beside it after the
first launch.

Usage:
  python build.py            # build for the current platform
  python build.py --clean    # delete dist/ and build/ first, then build
  python build.py --help     # show this message

Requirements:
  pip install pyinstaller

The build does not affect the source .py files or your dev cache/ folder.
Running 'python pokemain.py' continues to work exactly as before.
"""

import os
import shutil
import subprocess
import sys

HERE     = os.path.dirname(os.path.abspath(__file__))
DIST_DIR = os.path.join(HERE, "dist")
BUILD_DIR = os.path.join(HERE, "build")
ENTRY    = os.path.join(HERE, "pokemain.py")


def _check_pyinstaller() -> bool:
    """Return True if PyInstaller is available."""
    try:
        subprocess.run(
            [sys.executable, "-m", "PyInstaller", "--version"],
            capture_output=True, check=True
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def clean() -> None:
    """Delete dist/ and build/ directories."""
    for d in (DIST_DIR, BUILD_DIR):
        if os.path.exists(d):
            shutil.rmtree(d)
            print(f"  Removed {d}")
        else:
            print(f"  (already clean: {d})")


def build() -> None:
    """Run PyInstaller to produce a single-file executable."""
    if not _check_pyinstaller():
        print("\n  ERROR: PyInstaller is not installed.")
        print("  Install it with:  pip install pyinstaller")
        print("  Then re-run:      python build.py")
        sys.exit(1)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",            # single binary, not a folder of DLLs
        "--console",            # keep terminal visible (CLI tool)
        "--name", "pokemain",   # output file name
        ENTRY,
    ]

    print()
    print("  Building Pokemon Toolkit...")
    print(f"  Command: {' '.join(cmd)}")
    print()

    result = subprocess.run(cmd, cwd=HERE)

    if result.returncode == 0:
        # Determine the output path based on platform
        exe_name = "pokemain.exe" if sys.platform == "win32" else "pokemain"
        out_path = os.path.join(DIST_DIR, exe_name)
        print()
        print("  ✓  Build successful.")
        print(f"  Output: {out_path}")
        print()
        print("  To distribute to end users:")
        print(f"    1. Copy '{exe_name}' to any folder on the user's machine.")
        print("    2. The user double-clicks it — no Python installation needed.")
        print("    3. A 'cache/' folder will be created next to the binary on first run.")
        print()
        print("  Your source .py files and dev cache/ are untouched.")
    else:
        print()
        print("  ✗  Build failed — see PyInstaller output above.")
        sys.exit(1)


def main() -> None:
    args = sys.argv[1:]

    if "--help" in args or "-h" in args:
        print(__doc__)
        sys.exit(0)

    if "--clean" in args:
        print("\n  Cleaning build artifacts...")
        clean()
        print()

    build()


if __name__ == "__main__":
    main()
