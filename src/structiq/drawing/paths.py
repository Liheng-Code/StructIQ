"""Where Drawing Intelligence reads and writes files.

* Working cache (large, recreatable, never synced): ``STRUCTIQ_WORK_DIR``,
  default ``D:\\Dev\\_work``.
* Deliverables for a job: ``<project>\\02-Structural Drawing`` inside the project
  folder on Google Drive (project = the ``PJR-YYYY-NNN_...`` folder).
"""

from __future__ import annotations

import os
import re
from pathlib import Path

WORK_ENV_VAR = "STRUCTIQ_WORK_DIR"
DEFAULT_WORK_DIR = r"D:\Dev\_work"
OUTPUT_FOLDER_NAME = "02-Structural Drawing"
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


def project_output_dir(source: str | os.PathLike[str]) -> Path:
    """Deliverables folder for the project that contains ``source`` (not created)."""
    return project_root(source) / OUTPUT_FOLDER_NAME
