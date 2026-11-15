"""Project codes: ``PJR-YYYY-NNN`` counted per year. Only the parent folder is listed (no deep Drive scan)."""

from __future__ import annotations

import re
from pathlib import Path

CODE_RE = re.compile(r"^PJR-(\d{4})-(\d{3})(?:_|$)")
ILLEGAL = set('<>:"/|?*') | {chr(92)}  # chr(92) is the backslash
MAX_NAME = 50


def clean_name(name: str) -> str:
    """Short project name safe for a Windows folder; rejects instead of silently changing meaning."""
    cleaned = " ".join(name.split())
    if not cleaned:
        raise ValueError("project name is empty")
    bad = sorted(ILLEGAL & set(cleaned))
    if bad:
        raise ValueError(f"project name has characters Windows does not allow: {bad}")
    if cleaned.endswith("."):
        raise ValueError("project name must not end with a dot")
    if len(cleaned) > MAX_NAME:
        raise ValueError(f"project name is {len(cleaned)} characters; keep it under {MAX_NAME} (Windows path limit)")
    return cleaned


def next_seq(parent: Path, year: int) -> int:
    """Highest existing number for ``year`` in ``parent`` plus one (001 when there is none)."""
    found = [
        int(m.group(2))
        for p in parent.iterdir()
        if p.is_dir() and (m := CODE_RE.match(p.name)) and int(m.group(1)) == year
    ]
    return max(found) + 1 if found else 1


def code_for(year: int, seq: int) -> str:
    if not 1 <= seq <= 999:
        raise ValueError(f"project number {seq} is outside 001-999")
    return f"PJR-{year}-{seq:03d}"


def folder_name(pattern: str, year: int, seq: int, name: str) -> str:
    return pattern.format(year=year, seq=seq, name=clean_name(name))
