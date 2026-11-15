"""Store received architect drawings in a dated set. Copies only: the source is never changed or removed."""

from __future__ import annotations

import datetime
import hashlib
import shutil
from pathlib import Path

from structiq.project import numbering, record

SUBFOLDER = {".pdf": "PDF", ".dwg": "DWG", ".dxf": "DWG"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def receive(
    project: str | Path,
    files: list[str | Path],
    label: str,
    *,
    today: datetime.date | None = None,
) -> list[Path]:
    """Copy ``files`` into ``<received_architect>/<date> <label>/{PDF,DWG}``; returns the new paths."""
    root = Path(project)
    data = record.read_record(root)
    today = today or datetime.date.today()
    base = root / data["roles"]["received_architect"] / f"{today.isoformat()} {numbering.clean_name(label)}"

    plan: list[tuple[Path, Path]] = []
    for f in files:
        src = Path(f)
        if not src.is_file():
            raise FileNotFoundError(f"{src} not found")
        sub = SUBFOLDER.get(src.suffix.lower())
        if sub is None:
            raise ValueError(f"{src.name}: only {', '.join(sorted(SUBFOLDER))} drawings are stored here")
        dest = base / sub / src.name
        if dest.exists() or any(dest == d for _, d in plan):
            raise FileExistsError(f"{dest} already exists: use a new label for a new set; nothing was copied")
        plan.append((src, dest))
    if not plan:
        raise ValueError("no files given")

    done: list[Path] = []
    received = list(data.get("received") or [])
    for src, dest in plan:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        digest = sha256(dest)
        if digest != sha256(src):
            dest.unlink()
            raise OSError(f"copy of {src.name} did not match the original; copy removed")
        received.append(
            {
                "file": dest.relative_to(root).as_posix(),
                "sha256": digest,
                "date": today.isoformat(),
                "source_name": src.name,
            }
        )
        done.append(dest)
    data["received"] = received
    rec = record.find_record(root)
    if rec is None:  # read_record found it a moment ago
        raise FileNotFoundError(f"project record disappeared in {root}")
    record.write_record(rec, data, replace=True)
    return done
