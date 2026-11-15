"""Store received architect drawings: dated set, running RCV number, standard file name, register.

Copies only: the source is never changed or removed. A file already received (same SHA-256) is refused, nothing is overwritten,
and nothing is deleted. A combined PDF is stored whole and also split into single-sheet copies; the split sheets are 'To confirm'
until someone names them with ``confirm``.
"""

from __future__ import annotations

import datetime
import hashlib
import os
import shutil
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from structiq.project import numbering, record, register
from structiq.project.register import DEFAULT_COLUMNS, DEFAULT_PATTERN

SUBFOLDER = {".pdf": "PDF", ".dwg": "DWG", ".dxf": "DWG"}
SPLIT_FOLDER = "Split Sheets"
REGISTER_FILE = "Received Register.csv"


@dataclass(frozen=True)
class Item:
    path: Path
    drawing_no: str | None = None
    title: str | None = None
    revision: str | None = None


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _item(x: Item | str | Path) -> Item:
    return x if isinstance(x, Item) else Item(Path(x))


def _page_count(path: Path) -> int:
    import pymupdf

    try:
        with pymupdf.open(path) as doc:  # type: ignore[no-untyped-call]
            return int(doc.page_count)
    except Exception:  # noqa: BLE001  (unreadable PDFs are still stored whole)
        return 1


def _csv_path(root: Path, data: dict[str, Any]) -> Path:
    mgmt = data["roles"].get("management")
    folder = root / mgmt if mgmt else root
    return folder / REGISTER_FILE


def _save(root: Path, data: dict[str, Any], columns: tuple[str, ...]) -> None:
    register.refresh_status(data["received"])
    rec = record.find_record(root)
    if rec is None:
        raise FileNotFoundError(f"project record disappeared in {root}")
    record.write_record(rec, data, replace=True)
    register.write_csv(_csv_path(root, data), data["received"], columns)


def receive(
    project: str | Path,
    items: Sequence[Item | str | Path],
    label: str,
    *,
    today: datetime.date | None = None,
    pattern: str = DEFAULT_PATTERN,
    columns: tuple[str, ...] = DEFAULT_COLUMNS,
    split: bool = True,
    discipline: str = "ARC",
) -> list[Path]:
    """Store ``items`` in ``<received_architect>/<date> <label>/{PDF,DWG}``; returns every new path (splits included)."""
    root = Path(project)
    data = record.read_record(root)
    today = today or datetime.date.today()
    set_name = f"{today.isoformat()} {numbering.clean_name(label)}"
    base = root / data["roles"]["received_architect"] / set_name
    received: list[dict[str, Any]] = list(data.get("received") or [])
    known = {str(e.get("sha256")): str(e.get("rcv_no")) for e in received}
    number = register.next_number(received)

    # ---- plan everything first, so a refusal copies nothing
    planned: list[tuple[Path, Path, dict[str, Any], int]] = []  # src, dest, entry, pages
    seen: dict[str, str] = {}
    for raw in items:
        it = _item(raw)
        src = it.path
        if not src.is_file():
            raise FileNotFoundError(f"{src} not found")
        ext = src.suffix.lower()
        sub = SUBFOLDER.get(ext)
        if sub is None:
            raise ValueError(f"{src.name}: only {', '.join(sorted(SUBFOLDER))} drawings are stored here")
        digest = sha256(src)
        if digest in known or digest in seen:
            raise FileExistsError(f"{src.name} was already received as {known.get(digest) or seen[digest]}; nothing was copied")
        rcv = register.rcv_id(number)
        name, confirmed = register.file_name(pattern, rcv, it.drawing_no, it.title, it.revision, src.name, ext)
        dest = base / sub / name
        register.check_path(dest)
        if dest.exists():
            raise FileExistsError(f"{dest} already exists: use a new label for a new set; nothing was copied")
        pages = _page_count(src) if ext == ".pdf" and split else 1
        entry = {
            "rcv_no": rcv,
            "file": dest.relative_to(root).as_posix(),
            "original_name": src.name,
            "discipline": discipline,
            "drawing_no": it.drawing_no if confirmed else "",
            "title": it.title if confirmed else "",
            "revision": register.revision_token(it.revision) if confirmed and it.revision else "",
            "format": ext[1:].upper(),
            "set": set_name,
            "received_date": today.isoformat(),
            "sha256": digest,
            "note": f"combined PDF, {pages} pages; split copies stored" if pages > 1 else "",
        }
        planned.append((src, dest, entry, pages))
        seen[digest] = rcv
        number += 1

    if not planned:
        raise ValueError("no files given")

    # ---- copy, verify, split; undo on any failure
    created: list[Path] = []
    new_entries: list[dict[str, Any]] = []
    try:
        for src, dest, entry, pages in planned:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            created.append(dest)
            if sha256(dest) != entry["sha256"]:
                raise OSError(f"copy of {src.name} did not match the original")
            new_entries.append(entry)
            if pages > 1:
                created += _split(dest, entry, pages, base, root, new_entries)
    except Exception:
        for p in created:
            p.unlink(missing_ok=True)
        raise

    data["received"] = received + new_entries
    _save(root, data, columns)
    return created


def _split(whole: Path, parent: dict[str, Any], pages: int, base: Path, root: Path, entries: list[dict[str, Any]]) -> list[Path]:
    import pymupdf

    number = int(parent["rcv_no"][4:7])
    out: list[Path] = []
    with pymupdf.open(whole) as doc:  # type: ignore[no-untyped-call]
        for i in range(pages):
            rcv = register.rcv_id(number, i + 1)
            dest = base / "PDF" / SPLIT_FOLDER / f"{rcv}_p{i + 1:02d}-of-{pages:02d}.pdf"
            register.check_path(dest)
            dest.parent.mkdir(parents=True, exist_ok=True)
            with pymupdf.open() as one:  # type: ignore[no-untyped-call]
                one.insert_pdf(doc, from_page=i, to_page=i)
                one.save(dest)
            out.append(dest)
            entries.append(
                {
                    "rcv_no": rcv,
                    "file": dest.relative_to(root).as_posix(),
                    "original_name": parent["original_name"],
                    "discipline": parent["discipline"],
                    "drawing_no": "",
                    "title": "",
                    "revision": "",
                    "format": "PDF",
                    "set": parent["set"],
                    "received_date": parent["received_date"],
                    "sha256": sha256(dest),
                    "note": f"page {i + 1} of {pages} of {parent['rcv_no']}",
                }
            )
    return out


def confirm(
    project: str | Path,
    rcv_no: str,
    drawing_no: str,
    title: str,
    revision: str,
    *,
    pattern: str = DEFAULT_PATTERN,
    columns: tuple[str, ...] = DEFAULT_COLUMNS,
) -> Path:
    """Give a stored file its drawing number, title and revision: renames it in place and updates the register."""
    root = Path(project)
    data = record.read_record(root)
    entry = next((e for e in data.get("received") or [] if e.get("rcv_no") == rcv_no), None)
    if entry is None:
        raise KeyError(f"{rcv_no} is not in the register")
    old: Path = root / entry["file"]
    if not old.is_file():
        raise FileNotFoundError(f"{old} is missing: the register and the folder disagree")
    name, _ = register.file_name(pattern, rcv_no, drawing_no, title, revision, old.name, old.suffix.lower())
    new = old.with_name(name)
    register.check_path(new)
    if new != old:
        if new.exists():
            raise FileExistsError(f"{new} already exists; nothing was changed")
        os.rename(old, new)
    entry.update(
        file=new.relative_to(root).as_posix(),
        drawing_no=drawing_no.strip(),
        title=title.strip(),
        revision=register.revision_token(revision),
    )
    _save(root, data, columns)
    return new
