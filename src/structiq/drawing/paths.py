"""Where Drawing Intelligence reads and writes files.

* Working cache (large, recreatable, never synced): ``STRUCTIQ_WORK_DIR``,
  default ``D:\\Dev\\_work``.
* Deliverables for a job: the project's folder for a role (``structiq_draft`` for StructIQ
  drafts), found in ``project.yaml``; old projects without one keep ``02-Structural Drawing``.
  Project = the ``PJR-YYYY-NNN_...`` folder on Google Drive.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import yaml

WORK_ENV_VAR = "STRUCTIQ_WORK_DIR"
DEFAULT_WORK_DIR = r"D:\Dev\_work"
OUTPUT_FOLDER_NAME = "02-Structural Drawing"  # old projects; new ones use the role in project.yaml
LEGACY_ROLES = {
    "structiq_draft": OUTPUT_FOLDER_NAME,
    "received_architect": "01-Architect drawing",
    "reference": "03-Reference",
}
_PROJECT_RE = re.compile(r"^PJR-\d{4}-\d{3}")


def work_dir() -> Path:
    return Path(os.environ.get(WORK_ENV_VAR, DEFAULT_WORK_DIR))


def project_root(source: str | os.PathLike[str]) -> Path:
    """Return the ``PJR-YYYY-NNN_...`` folder that contains ``source``."""
    path = Path(source).resolve()
    for parent in path.parents:
        if _PROJECT_RE.match(parent.name):
            return parent
    raise ValueError(f"{path} is not inside a PJR-YYYY-NNN project folder")


def _record_roles(root: Path) -> dict[str, str]:
    """Folder roles from the project's ``project.yaml`` (management folder or project root); empty if none."""
    for candidate in sorted(root.glob("*/project.yaml")) + [root / "project.yaml"]:
        if candidate.is_file():
            data = yaml.safe_load(candidate.read_text(encoding="utf-8")) or {}
            roles = data.get("roles") if isinstance(data, dict) else None
            return {str(k): str(v) for k, v in roles.items()} if isinstance(roles, dict) else {}
    return {}


def project_folder(source: str | os.PathLike[str], role: str) -> Path:
    """Folder for ``role`` in the project that contains ``source`` (not created).

    Uses the project's ``project.yaml``; an old project without one keeps its original folder names.
    """
    root = project_root(source)
    roles = _record_roles(root)
    if role in roles:
        return root / roles[role]
    if role in LEGACY_ROLES:
        return root / LEGACY_ROLES[role]
    raise KeyError(f"{root.name} has no folder recorded for role {role!r}")


def project_output_dir(source: str | os.PathLike[str]) -> Path:
    """Folder for StructIQ's drafts in the project that contains ``source`` (not created)."""
    return project_folder(source, "structiq_draft")
