"""Puzzle Solver — Entry point.

Launches the NiceGUI-based puzzle solver application.
By default runs in native (desktop window) mode.
Pass --web or set PUZZLE_SOLVER_WEB=1 for browser mode.
"""

from src.ui.theme import create_app

if __name__ == "__main__":
    create_app()
