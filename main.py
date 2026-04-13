"""Puzzle Solver — Entry point.

Launches the Flet-based puzzle solver application.
Pass --web for browser mode, otherwise runs as desktop app.
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
        os.chdir(os.path.dirname(sys.executable))


_handle_frozen_state()

import flet as ft  # noqa: E402
from src.logger import setup_logging  # noqa: E402
from src.ui.app import main as app_main  # noqa: E402

setup_logging()

if __name__ == "__main__":
    web_mode = "--web" in sys.argv or os.environ.get(
        "PUZZLE_SOLVER_WEB", ""
    ).lower() in ("1", "true", "yes")

    if web_mode:
        ft.run(app_main, view=ft.AppView.WEB_BROWSER, port=8080)
    else:
        ft.run(app_main)
