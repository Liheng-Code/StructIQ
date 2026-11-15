"""Record which existing folder of an OLD project plays which role. Moves, renames and creates nothing."""

from __future__ import annotations

import datetime
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from structiq.project import record

# role -> pattern on the folder name. The first folder that matches a role wins; a folder serves one role
# (the drawing folder also serves structiq_draft).
KEYWORDS: tuple[tuple[str, str], ...] = (
    ("received_architect", r"architect"),
    ("received_client", r"client|document from"),
    ("received_site", r"soil|survey|geotech|site data"),
    ("calc_note", r"calculation|calc note"),
    ("etabs", r"etabs|structural analysis"),
    ("revit", r"revit|bim"),
    ("boq", r"boq|quantit|take.?off"),
    ("submission", r"submission|transmittal"),
    ("drawing", r"structural drawing|^\d+[-_ ]*drawing"),
    ("reference", r"reference"),
)
_CODE = re.compile(r"^(PJR-\d{4}-\d{3})_?(.*)$")


@dataclass
class AdoptPlan:
    root: Path
    roles: dict[str, str] = field(default_factory=dict)
    unmatched: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    written: Path | None = None


def plan_adopt(root: str | Path) -> AdoptPlan:
    root = Path(root)
    if not root.is_dir() or not _CODE.match(root.name):
        raise ValueError(f"{root} is not a PJR-YYYY-NNN project folder")
    plan = AdoptPlan(root)
    used: set[str] = set()
    children = sorted(p.name for p in root.iterdir() if p.is_dir())
    for role, pattern in KEYWORDS:
        for name in children:
            if name not in used and re.search(pattern, name, re.I):
                plan.roles[role] = name
                used.add(name)
                break
    if "drawing" in plan.roles:
        plan.roles["structiq_draft"] = plan.roles["drawing"]  # StructIQ drafts go in the drawing folder of an old project
    plan.unmatched = [n for n in children if n not in used]
    plan.missing = [r for r, _ in KEYWORDS if r not in plan.roles]
    return plan


def adopt(root: str | Path, *, today: datetime.date | None = None) -> AdoptPlan:
    """Write ``project.yaml`` at the project root from the detected roles. Refuses if a record already exists."""
    plan = plan_adopt(root)
    if record.find_record(plan.root) is not None:
        raise FileExistsError(f"{plan.root} already has a {record.RECORD_NAME}; nothing was changed")
    m = _CODE.match(plan.root.name)
    if m is None:
        raise ValueError(f"{plan.root} is not a PJR-YYYY-NNN project folder")
    data: dict[str, Any] = {
        "code": m.group(1),
        "name": m.group(2),
        "created": (today or datetime.date.today()).isoformat(),
        "adopted": True,
        "roles": dict(plan.roles),
        "received": [],
    }
    path = record.record_path(plan.root, None)
    record.write_record(path, data)
    plan.written = path
    return plan
