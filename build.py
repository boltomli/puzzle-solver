#!/usr/bin/env python
"""Build script for packaging Puzzle Solver with PyInstaller.

Creates a standalone Windows executable using PyInstaller.
NiceGUI static assets are automatically included.

Usage:
    python build.py
    python build.py --onefile          # Single executable (default)
    python build.py --onedir           # Directory-based output
    python build.py --name MyApp       # Custom app name
    python build.py --dry-run          # Print command without executing
"""

import os
import platform
import subprocess
import sys
from pathlib import Path

import nicegui


def main() -> None:
    """Build the Puzzle Solver executable with PyInstaller."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Package Puzzle Solver as a standalone executable using PyInstaller.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--name",
        type=str,
        default="PuzzleSolver",
        help="Name of the output executable (default: PuzzleSolver).",
    )
    parser.add_argument(
        "--onedir",
        action="store_true",
        default=False,
        help="Create a directory-based distribution instead of a single file.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print the PyInstaller command without executing it.",
    )

    args = parser.parse_args()

    # Discover nicegui package path for --add-data
    nicegui_dir = Path(nicegui.__file__).parent
    separator = os.pathsep  # ';' on Windows, ':' on Unix

    # Build command
    # On Windows, call pyinstaller directly; on other platforms use python -m
    if platform.system() == "Windows":
        command: list[str] = ["pyinstaller"]
    else:
        command = [sys.executable, "-m", "PyInstaller"]

    command.extend(["--name", args.name])

    # --onefile is the default; use --onedir to override
    if not args.onedir:
        command.append("--onefile")

    # --windowed: suppress console window (for native desktop mode)
    command.append("--windowed")

    # Include nicegui static assets
    command.extend(["--add-data", f"{nicegui_dir}{separator}nicegui"])

    # Target the main entry point
    command.append("main.py")

    print("PyInstaller command:")
    print("  " + " ".join(command))
    print()

    if args.dry_run:
        print("Dry run — not executing.")
        return

    # Clean previous build artifacts
    for directory in ["build", "dist"]:
        dirpath = Path(directory)
        if dirpath.exists():
            import shutil

            shutil.rmtree(dirpath)

    exit_code = subprocess.call(command)
    if exit_code == 0:
        print("\n✅ Build succeeded! Output is in the 'dist' directory.")
    else:
        print(f"\n❌ Build failed with exit code {exit_code}.")
        sys.exit(exit_code)


if __name__ == "__main__":
    main()
