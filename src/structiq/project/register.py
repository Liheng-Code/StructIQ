"""The received-drawing register: numbering, file names and revision status.

Every file received gets a project-wide running number ``RCV-NNN`` that is never reused. Pages split out of a combined PDF
are ``RCV-NNN.PP``. The register lives in ``project.yaml`` (machine record) and is written as ``Received Register.csv`` (for people).
"""

from __future__ import annotations

import csv
import os
import re
from pathlib import Path
from typing import Any

from structiq.project.numbering import ILLEGAL

DEFAULT_COLUMNS = (
    "rcv_no",
    "file",
    "original_name",
    "discipline",
    "drawing_no",
    "title",
    "revision",
    "format",
    "set",
    "received_date",
    "sha256",
    "status",
    "note",
)
DEFAULT_PATTERN = "{rcv}_{drawing_no}_{title}_Rev{revision}"
CURRENT, SUPERSEDED, TO_CONFIRM = "Current", "Superseded", "To confirm"
MAX_PART = 40  # characters of one name part, to stay under the Windows path limit
MAX_PATH = 240

_RCV = re.compile(r"^RCV-(\d{3})(?:\.(\d{2}))?$")


def rcv_id(n: int, page: int | None = None) -> str:
    if not 1 <= n <= 999:
        raise ValueError(f"received number {n} is outside 001-999")
    return f"RCV-{n:03d}" + (f".{page:02d}" if page else "")


def next_number(received: list[dict[str, Any]]) -> int:
    nums = [int(m.group(1)) for e in received if (m := _RCV.match(str(e.get("rcv_no", ""))))]
    return max(nums) + 1 if nums else 1


def part(text: str) -> str:
    """One piece of a file name: illegal characters become '-', spaces are tidied, length is capped."""
    cleaned = "".join("-" if c in ILLEGAL else c for c in text)
    cleaned = " ".join(cleaned.split()).strip(" .")
    if not cleaned:
        raise ValueError("a name part is empty")
    return cleaned[:MAX_PART].rstrip(" .")


def revision_token(revision: str) -> str:
    """'B', 'rev B', 'Rev.B' and 'b' all give 'B'; '03' stays '03'."""
    token = re.sub(r"^\s*rev(?:ision)?[\s._-]*", "", revision.strip(), flags=re.I)
    token = part(token).replace(" ", "")
    return token.upper()


def file_name(
    pattern: str,
    rcv: str,
    drawing_no: str | None,
    title: str | None,
    revision: str | None,
    original: str,
    ext: str,
) -> tuple[str, bool]:
    """(file name, confirmed). Without drawing number, title and revision the name keeps the original
    name after the RCV number and the entry is flagged 'To confirm'."""
    if drawing_no and title and revision:
        stem = pattern.format(
            rcv=rcv, drawing_no=part(drawing_no), title=part(title), revision=revision_token(revision)
        )
        return stem + ext, True
    return f"{rcv}_{part(Path(original).stem)}{ext}", False


def refresh_status(received: list[dict[str, Any]]) -> None:
    """Newest received revision of each drawing number is Current, older ones Superseded; unnamed ones To confirm."""
    latest: dict[tuple[str, str], int] = {}
    for i, e in enumerate(received):
        if e.get("drawing_no") and e.get("revision"):
            latest[(str(e.get("discipline", "ARC")), str(e["drawing_no"]).upper())] = i
    for i, e in enumerate(received):
        if not (e.get("drawing_no") and e.get("revision")):
            e["status"] = TO_CONFIRM
        elif latest[(str(e.get("discipline", "ARC")), str(e["drawing_no"]).upper())] == i:
            e["status"] = CURRENT
        else:
            e["status"] = SUPERSEDED


def write_csv(path: Path, received: list[dict[str, Any]], columns: tuple[str, ...] = DEFAULT_COLUMNS) -> None:
    """Write the human copy. It is derived from ``project.yaml``, so it is replaced in one step each time."""
    tmp = path.with_suffix(".csv.tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(columns)
        for e in received:
            w.writerow(["" if e.get(c) is None else e.get(c) for c in columns])
    os.replace(tmp, path)


def check_path(path: Path) -> None:
    if len(str(path)) > MAX_PATH:
        raise ValueError(f"path would be {len(str(path))} characters (limit {MAX_PATH}): shorten the title or the project name")
