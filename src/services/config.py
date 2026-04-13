"""Configuration management for API settings.

Reads/writes config.json at the project root.
"""

import json
from pathlib import Path
from typing import Any

from loguru import logger

# Config file lives at the project root
_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config.json"

_DEFAULT_CONFIG: dict[str, Any] = {
    "api_base_url": "",
    "api_key": "",
    "model": "",
    "system_prompt_override": "",
}


def load_config() -> dict[str, Any]:
    """Load config from config.json. Returns defaults if file doesn't exist."""
    if _CONFIG_PATH.exists():
        try:
            data = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
            merged = {**_DEFAULT_CONFIG, **data}
            logger.debug(
                "load_config: loaded from {} base_url={!r} model={!r}",
                _CONFIG_PATH,
                merged.get("api_base_url"),
                merged.get("model"),
            )
            return merged
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("load_config: failed to read {}, using defaults: {}", _CONFIG_PATH, exc)
            return dict(_DEFAULT_CONFIG)
    logger.debug("load_config: {} not found, using defaults", _CONFIG_PATH)
    return dict(_DEFAULT_CONFIG)


def save_config(config: dict[str, Any]) -> None:
    """Save config to config.json at project root."""
    _CONFIG_PATH.write_text(
        json.dumps(config, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info(
        "save_config: written to {} base_url={!r} model={!r}",
        _CONFIG_PATH,
        config.get("api_base_url"),
        config.get("model"),
    )
