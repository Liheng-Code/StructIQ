"""Create a new freelance project folder from the Core Brain layout. Never overwrites, never deletes."""

from __future__ import annotations

import csv
import datetime
from dataclasses import dataclass, field
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.worksheet.datavalidation import DataValidation

from structiq.project import numbering, record
from structiq.project.layout import Layout, check_length

STATUSES = ["Not started", "In progress", "Waiting for client", "Done"]
TRACKER_NAME = "Project Tracker.xlsx"
REGISTER_NAME = "Drawing Register.csv"


@dataclass
class NewProject:
    root: Path
    code: str
    folders: list[str]
    files: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    dry_run: bool = False


def _write_register(path: Path, columns: tuple[str, ...]) -> None:
    with open(path, "x", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerow(columns)


def _write_tracker(path: Path, steps: tuple[str, ...], created: datetime.date) -> None:
    wb = Workbook()
    ws = wb.create_sheet("Tracker", 0)
    del wb["Sheet"]  # the default empty sheet
    ws.append(["No", "Step", "Status", "Date", "Notes"])
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for i, step in enumerate(steps, 1):
        ws.append([i, step, "Not started", None, None])
    dv = DataValidation(type="list", formula1='"' + ",".join(STATUSES) + '"', allow_blank=False)
    ws.add_data_validation(dv)
    dv.add(f"C2:C{len(steps) + 1}")
    ws.column_dimensions["B"].width = 62
    ws.column_dimensions["C"].width = 20
    ws.column_dimensions["E"].width = 40
    ws["G1"] = "Created"
    ws["H1"] = created.isoformat()
    wb.save(path)  # a new, empty file: the caller has already refused an existing project


def new_project(
    name: str,
    parent: str | Path,
    layout: Layout,
    brain_version: str,
    *,
    year: int | None = None,
    today: datetime.date | None = None,
    dry_run: bool = False,
) -> NewProject:
    today = today or datetime.date.today()
    year = year or today.year
    parent = Path(parent)
    if not parent.is_dir():
        raise FileNotFoundError(f"parent folder {parent} does not exist: check projects in config/paths.yaml")
    seq = numbering.next_seq(parent, year)
    code = numbering.code_for(year, seq)
    root = parent / numbering.folder_name(layout.code_pattern, year, seq, name)
    if root.exists():
        raise FileExistsError(f"{root} already exists; nothing was changed")
    result = NewProject(root, code, layout.paths(), warnings=check_length(root, layout), dry_run=dry_run)
    roles = layout.roles()
    mgmt = roles["management"]
    result.files = [
        root / mgmt / record.RECORD_NAME,
        root / mgmt / REGISTER_NAME,
        root / mgmt / TRACKER_NAME,
    ]
    if dry_run:
        return result

    root.mkdir()
    for rel in result.folders:
        (root / rel).mkdir(parents=True)
    data = {
        "code": code,
        "name": numbering.clean_name(name),
        "created": today.isoformat(),
        "stage": "CONCEPT",
        "brain_version": brain_version,
        "layout_version": layout.version,
        "roles": roles,
        "received": [],
    }
    record.write_record(result.files[0], data)
    _write_register(result.files[1], layout.register_columns)
    _write_tracker(result.files[2], layout.workflow_steps, today)
    return result
