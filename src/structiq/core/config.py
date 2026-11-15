"""Machine-specific settings from ``config/paths.yaml`` (git-ignored; see ``paths.example.yaml``).

Only locations live here, never engineering values. Everything is optional: a missing file or key
returns ``None`` so callers can fall back to searching standard install folders.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

CONFIG_ENV = "STRUCTIQ_CONFIG"  # full path to a paths.yaml, for tests or another machine


def config_path() -> Path:
    env = os.environ.get(CONFIG_ENV)
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[3] / "config" / "paths.yaml"


def load_config(path: str | os.PathLike[str] | None = None) -> dict:
    p = Path(path) if path else config_path()
    if not p.is_file():
        return {}
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{p}: expected a mapping at the top level")
    return data


def tool_path(name: str, path: str | os.PathLike[str] | None = None) -> Path | None:
    """Configured executable for ``name`` (``tools:`` section), or None when not set or missing."""
    value = (load_config(path).get("tools") or {}).get(name)
    if not value:
        return None
    p = Path(str(value))
    return p if p.exists() else None
