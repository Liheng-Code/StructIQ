"""The project folder layout: loaded from the Core Brain (``04-Global Workflows/project-folder-layout.yaml``).

One source of truth. The tree has named folders with optional ``role`` ids; tools find folders by role.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

LAYOUT_FILE = Path("04-Global Workflows") / "project-folder-layout.yaml"
ILLEGAL = set('<>:"/|?*') | {chr(92)}  # chr(92) is the backslash
REQUIRED_ROLES = (
    "management",
    "received_architect",
    "design_basis",
    "structiq_draft",
    "drawing_working",
    "drawing_issued",
    "archive",
)
_ROLE_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_TOP_RE = re.compile(r"^\d{2}-\S")


class LayoutError(ValueError):
    """The layout file is not valid."""


@dataclass(frozen=True)
class Node:
    name: str
    role: str | None = None
    children: tuple[Node, ...] = ()


@dataclass(frozen=True)
class Layout:
    version: int
    status: str
    code_pattern: str
    parent_folder: str
    register_columns: tuple[str, ...]
    workflow_steps: tuple[str, ...]
    folders: tuple[Node, ...] = field(default_factory=tuple)

    def paths(self) -> list[str]:
        """Every folder as a posix path relative to the project root, parents before children."""
        out: list[str] = []

        def walk(nodes: tuple[Node, ...], prefix: str) -> None:
            for n in nodes:
                p = f"{prefix}{n.name}"
                out.append(p)
                walk(n.children, p + "/")

        walk(self.folders, "")
        return out

    def roles(self) -> dict[str, str]:
        """role -> posix path relative to the project root."""
        out: dict[str, str] = {}

        def walk(nodes: tuple[Node, ...], prefix: str) -> None:
            for n in nodes:
                p = f"{prefix}{n.name}"
                if n.role:
                    out[n.role] = p
                walk(n.children, p + "/")

        walk(self.folders, "")
        return out

    def longest_path(self) -> int:
        return max((len(p) for p in self.paths()), default=0)


def _node(raw: Any, where: str) -> Node:
    if not isinstance(raw, dict) or not isinstance(raw.get("name"), str):
        raise LayoutError(f"{where}: each folder needs a 'name'")
    name = raw["name"]
    if not name.strip() or name != name.strip() or name.endswith("."):
        raise LayoutError(f"{where}: bad folder name {name!r}")
    if ILLEGAL & set(name):
        raise LayoutError(f"{where}: folder name {name!r} has a character Windows does not allow")
    role = raw.get("role")
    if role is not None and not (isinstance(role, str) and _ROLE_RE.match(role)):
        raise LayoutError(f"{where}/{name}: role {role!r} must be snake_case")
    kids = tuple(_node(c, f"{where}/{name}") for c in raw.get("children") or [])
    names = [k.name.lower() for k in kids]
    if len(names) != len(set(names)):
        raise LayoutError(f"{where}/{name}: duplicate sibling folder names")
    return Node(name, role, kids)


def parse_layout(data: Any) -> Layout:
    if not isinstance(data, dict):
        raise LayoutError("layout file must be a mapping")
    for key in ("version", "code_pattern", "parent_folder", "register_columns", "workflow_steps", "folders"):
        if key not in data:
            raise LayoutError(f"layout file is missing '{key}'")
    folders = tuple(_node(f, "folders") for f in data["folders"])
    numbers: list[str] = []
    for n in folders:
        if not _TOP_RE.match(n.name):
            raise LayoutError(f"top-level folder {n.name!r} must start with 'NN-'")
        numbers.append(n.name[:2])
    if len(numbers) != len(set(numbers)):
        raise LayoutError("two top-level folders share a number")
    layout = Layout(
        int(data["version"]),
        str(data.get("status", "DRAFT")),
        str(data["code_pattern"]),
        str(data["parent_folder"]),
        tuple(str(c) for c in data["register_columns"]),
        tuple(str(s) for s in data["workflow_steps"]),
        folders,
    )
    roles: list[str] = []

    def collect(nodes: tuple[Node, ...]) -> None:
        for n in nodes:
            if n.role:
                roles.append(n.role)
            collect(n.children)

    collect(folders)
    dupes = sorted({r for r in roles if roles.count(r) > 1})
    if dupes:
        raise LayoutError(f"duplicate roles: {dupes}")
    missing = [r for r in REQUIRED_ROLES if r not in roles]
    if missing:
        raise LayoutError(f"layout has no folder for required roles: {missing}")
    return layout


def load_layout(brain_dir: str | Path | None = None) -> tuple[Layout, str]:
    """(layout, Core Brain version). Stops (BrainNotFoundError) if the Core Brain cannot be read."""
    from structiq.drawing.pipeline import read_brain

    brain, version = read_brain(brain_dir)
    path = brain / LAYOUT_FILE
    if not path.is_file():
        raise LayoutError(f"{path} not found: the project folder layout is part of the Core Brain")
    return parse_layout(yaml.safe_load(path.read_text(encoding="utf-8"))), version


def check_length(root: Path, layout: Layout, margin: int = 60) -> list[str]:
    """Warn when the longest layout path plus a typical file name could pass Windows' 260-character limit."""
    longest = len(str(root)) + 1 + layout.longest_path() + margin
    if longest > 260:
        return [f"longest path would be about {longest} characters (limit 260): use a shorter project name"]
    return []
