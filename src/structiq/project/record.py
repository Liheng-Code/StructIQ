"""``project.yaml``: the machine-readable record of one project (code, name, folder roles, files received)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

RECORD_NAME = "project.yaml"


def record_path(root: Path, management: str | None) -> Path:
    """New projects keep it in the management folder; adopted old projects keep it at the project root."""
    return root / management / RECORD_NAME if management else root / RECORD_NAME


def find_record(root: Path) -> Path | None:
    for candidate in sorted(root.glob(f"*/{RECORD_NAME}")) + [root / RECORD_NAME]:
        if candidate.is_file():
            return candidate
    return None


def read_record(root: Path) -> dict[str, Any]:
    path = find_record(root)
    if path is None:
        raise FileNotFoundError(f"no {RECORD_NAME} in {root}: create the project with 'new' or run 'adopt'")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict) or not isinstance(data.get("roles"), dict):
        raise ValueError(f"{path}: expected a mapping with 'roles'")
    return data


def write_record(path: Path, data: dict[str, Any], *, replace: bool = False) -> None:
    """Write the record. A new record never overwrites; an update (replace=True) swaps the file in one step."""
    text = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
    if not replace:
        with open(path, "x", encoding="utf-8") as fh:
            fh.write(text)
        return
    tmp = path.with_suffix(".yaml.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
