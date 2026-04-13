"""Puzzle Solver — Entry point.

Launches the NiceGUI-based puzzle solver application.
By default runs in native (desktop window) mode.
Pass --web or set PUZZLE_SOLVER_WEB=1 for browser mode.
"""

import os
import sys


def _handle_frozen_state() -> None:
    """Handle PyInstaller frozen state for correct path resolution.

    When running as a PyInstaller bundle, sys.frozen is True and
    sys._MEIPASS points to the temporary directory where bundled
    files are extracted. We change the working directory so that
    relative paths (e.g. data/, config.json) resolve correctly.
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        # Running inside a PyInstaller bundle
        # Set working directory to the directory containing the executable
        # so that data files and configs are found next to the .exe
        os.chdir(os.path.dirname(sys.executable))


_handle_frozen_state()

from src.ui.theme import create_app  # noqa: E402

if __name__ == "__main__":
    create_app()
