"""Split a stored combined DWG/DXF into one file per drawing and register each piece.

The received file is never changed. Each piece is a derived copy: ``RCV-001.NN_<drawing no>_<title>_Rev<rev>``, kept in the
``Split Sheets`` folder next to the original, with ``derived_from`` pointing at the parent in the register (status ``Derived``).
The parent must be named first (``confirm``), so every piece carries a real drawing number and revision.
"""

from __future__ import annotations

import datetime
import shutil
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ezdxf.filemanagement import readfile

from structiq.drawing import paths, split
from structiq.project import record, register
from structiq.project.receive import SPLIT_FOLDER, _save, sha256
from structiq.project.register import DEFAULT_COLUMNS, DEFAULT_PATTERN


def _parent(data: dict[str, Any], rcv_no: str) -> dict[str, Any]:
    entry = next((e for e in data.get("received") or [] if e.get("rcv_no") == rcv_no), None)
    if entry is None:
        raise KeyError(f"{rcv_no} is not in the register")
    if "." in rcv_no:
        raise ValueError(f"{rcv_no} is itself a split piece; split the file it came from")
    if entry.get("format") not in ("DWG", "DXF"):
        raise ValueError(f"{rcv_no} is a {entry.get('format')} file; only DWG and DXF drawings can be split here")
    if not (entry.get("drawing_no") and entry.get("revision")):
        raise ValueError(f"{rcv_no} has no drawing number and revision yet: name it with 'confirm' first")
    result: dict[str, Any] = entry
    return result


def _next_index(received: list[dict[str, Any]], parent: str) -> int:
    nums = [int(str(e["rcv_no"]).split(".")[1]) for e in received if str(e.get("rcv_no", "")).startswith(parent + ".")]
    return max(nums) + 1 if nums else 1


def scan(project: str | Path, rcv_no: str, *, within: int | None = None, min_entities: int = 40) -> tuple[list[split.View], Path]:
    """The drawings found in a stored combined file (ids are what ``split_received`` takes)."""
    root = Path(project)
    data = record.read_record(root)
    entry = next((e for e in data.get("received") or [] if e.get("rcv_no") == rcv_no), None)
    if entry is None:
        raise KeyError(f"{rcv_no} is not in the register")
    dxf = split.load_dxf(root / entry["file"])
    doc = readfile(dxf)
    box = None
    if within:
        top = next((v for v in split.find_views(doc, min_entities=min_entities) if v.id == within), None)
        if top is None:
            raise ValueError(f"no view {within} in the first scan")
        box = top.box
    return split.find_views(doc, min_entities=min_entities, within=box), dxf


def split_received(
    project: str | Path,
    rcv_no: str,
    picks: Sequence[tuple[int, str]],
    *,
    within: int | None = None,
    margin: float = 0.0,
    dwg: bool = False,
    min_entities: int = 40,
    pattern: str = DEFAULT_PATTERN,
    columns: tuple[str, ...] = DEFAULT_COLUMNS,
    today: datetime.date | None = None,
) -> list[Path]:
    """Export the chosen views (``(view id, title)``) of a stored file; returns the new files."""
    root = Path(project)
    data = record.read_record(root)
    parent = _parent(data, rcv_no)
    views, dxf = scan(root, rcv_no, within=within, min_entities=min_entities)
    by_id = {v.id: v for v in views}
    missing = [i for i, _ in picks if i not in by_id]
    if missing:
        raise ValueError(f"no view {missing}; run 'views' first (found {sorted(by_id)})")
    if not picks:
        raise ValueError("no views chosen")

    received: list[dict[str, Any]] = list(data.get("received") or [])
    out_dir = (root / parent["file"]).parent / SPLIT_FOLDER
    today = today or datetime.date.today()
    ext = ".dwg" if dwg else ".dxf"
    index = _next_index(received, rcv_no)

    plan: list[tuple[int, str, Path, str]] = []
    for vid, title in picks:
        rcv = f"{rcv_no}.{index:02d}"
        name, _ = register.file_name(pattern, rcv, parent["drawing_no"], title, parent["revision"], parent["original_name"], ext)
        dest = out_dir / name
        register.check_path(dest)
        if dest.exists():
            raise FileExistsError(f"{dest} already exists; nothing was changed")
        plan.append((vid, title, dest, rcv))
        index += 1

    created: list[Path] = []
    new_entries: list[dict[str, Any]] = []
    try:
        for vid, title, dest, rcv in plan:
            view = by_id[vid]
            work = paths.work_dir() / "split" / f"{rcv}.dxf"
            report = split.export_window(dxf, view.box, work, margin=margin)
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dwg:
                from structiq.tools import autocad

                autocad.dxf_to_dwg(work, dest)
            else:
                shutil.copy2(work, dest)
            created.append(dest)
            new_entries.append(
                {
                    "rcv_no": rcv,
                    "file": dest.relative_to(root).as_posix(),
                    "original_name": parent["original_name"],
                    "discipline": parent.get("discipline", "ARC"),
                    "drawing_no": parent["drawing_no"],
                    "title": register.part(title),
                    "revision": parent["revision"],
                    "format": ext[1:].upper(),
                    "set": parent["set"],
                    "received_date": today.isoformat(),
                    "sha256": sha256(dest),
                    "note": f"view {vid}; {report.summary()}",
                    "derived_from": rcv_no,
                }
            )
    except Exception:
        for p in created:
            p.unlink(missing_ok=True)
        raise
    data["received"] = received + new_entries
    _save(root, data, columns)
    return created
