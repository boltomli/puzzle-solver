#!/usr/bin/env python
"""Build script for packaging Puzzle Solver with Flet.

Creates a standalone application package using Flet's built-in packaging.

Usage:
    python build.py
    python build.py --web              # Build for web deployment
    python build.py --name MyApp       # Custom app name
    python build.py --dry-run          # Print command without executing
"""

import subprocess
import sys


def main() -> None:
    """Build the Puzzle Solver application with Flet packaging."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Package Puzzle Solver as a standalone application using Flet.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--name",
        type=str,
        default="PuzzleSolver",
        help="Name of the output application (default: PuzzleSolver).",
    )
    parser.add_argument(
        "--web",
        action="store_true",
        default=False,
        help="Build for web deployment instead of desktop.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print the build command without executing it.",
    )

    args = parser.parse_args()

    # Build command using flet pack (desktop) or flet publish (web)
    if args.web:
        command: list[str] = [
            sys.executable,
            "-m",
            "flet",
            "publish",
            "main.py",
            "--app-name",
            args.name,
        ]
    else:
        command = [
            sys.executable,
            "-m",
            "flet",
            "pack",
            "main.py",
            "--name",
            args.name,
            "--add-data",
            "data:data",
        ]

    print("Flet build command:")
    print("  " + " ".join(command))
    print()

    if args.dry_run:
        print("Dry run — not executing.")
        return

    exit_code = subprocess.call(command)
    if exit_code == 0:
        print("\n✅ Build succeeded!")
    else:
        print(f"\n❌ Build failed with exit code {exit_code}.")
        sys.exit(exit_code)


if __name__ == "__main__":
    main()
