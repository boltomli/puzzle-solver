"""Unified logging setup for Puzzle Solver using loguru.

Call ``setup_logging()`` once at application startup (in main.py).
After that, any module can simply do::

    from loguru import logger
    logger.info("something happened")

Log sinks:
- stderr (console): colored, INFO and above
- logs/puzzle-solver.log: plain text, DEBUG and above,
  rotated daily at midnight, kept for 14 days, compressed with zip
"""

import sys
from pathlib import Path

from loguru import logger


def setup_logging(log_dir: Path | None = None) -> None:
    """Configure loguru sinks.

    Args:
        log_dir: Directory for log files. Defaults to <project_root>/logs.
    """
    # Resolve log directory relative to this file's grandparent (project root)
    if log_dir is None:
        log_dir = Path(__file__).resolve().parent.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    # Remove default loguru sink
    logger.remove()

    # --- Console sink: INFO+ with colour ---
    logger.add(
        sys.stderr,
        level="INFO",
        colorize=True,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level:<8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{line}</cyan> — "
            "<level>{message}</level>"
        ),
    )

    # --- File sink: DEBUG+, daily rotation, 14-day retention, zip ---
    logger.add(
        log_dir / "puzzle-solver.log",
        level="DEBUG",
        rotation="00:00",  # rotate at midnight
        retention="14 days",
        compression="zip",
        encoding="utf-8",
        enqueue=True,  # non-blocking async-safe writes
        backtrace=True,  # full traceback on exceptions
        diagnose=True,  # variable values in traceback
        format=("{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {name}:{line} — {message}"),
    )

    logger.info("Logging initialised — log dir: {}", log_dir)
