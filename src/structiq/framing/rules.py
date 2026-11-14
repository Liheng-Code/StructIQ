"""Beam arrangement rules, loaded from the Core Brain (``beam-rules.yaml``).

The rules are the engineer's, learned from the sample design and approved by them. The file
must say ``status: approved``; a draft is refused unless the caller opts in. Sizes are the
engineer's preliminary sizes, not the result of a calculation.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

RULES_FILE = Path("02-Engineering Principles") / "beam-rules.yaml"


class RulesNotApprovedError(RuntimeError):
    """The beam rules are missing, unreadable or still a draft."""


@dataclass(frozen=True)
class BeamSize:
    mark: str
    width: float
    depth: float

    @property
    def type_name(self) -> str:
        return f"{self.mark}-({self.width:.0f}x{self.depth:.0f})mm"


@dataclass
class BeamRules:
    column_lines: tuple[str, ...]
    max_clear_span: float
    slab_floor: float
    slab_roof: float
    fck_beam: str
    band_width_by_line: dict[str, float]
    band_depth: float
    band_mark_by_width: dict[float, str]
    band_line_tolerance: float
    sizes: dict[str, BeamSize]  # role -> size
    min_segment: float
    stair_edge_role: str
    stair_end_role: str
    shaft_trimmers: bool
    position_match: float
    cantilever_role: str | None = None  # beam role for a slab edge past a column line
    cantilever_min_overhang: float = 300.0

    def band_width(self, line_label: str) -> float | None:
        return self.band_width_by_line.get(_norm(line_label))

    def band_mark(self, width: float) -> str:
        return self.band_mark_by_width.get(width, "PTB")


def _norm(label: str) -> str:
    """Gridline labels compare without leading zeros ("01" and "1" are the same line)."""
    s = str(label).strip()
    return s.lstrip("0") or "0" if s.isdigit() else s


def from_dict(data: dict, allow_draft: bool = False) -> BeamRules:
    if data.get("status") != "approved" and not allow_draft:
        raise RulesNotApprovedError(
            "beam-rules.yaml is not marked 'status: approved'. The engineer must approve the "
            "rules before StructIQ arranges beams."
        )
    pt = data["pt_bands"]
    beams = data["beams"]
    openings = data["openings"]
    return BeamRules(
        column_lines=tuple(str(x) for x in data["frame"]["column_lines"]),
        max_clear_span=float(data["slab"]["max_clear_span"]),
        slab_floor=float(data["slab"]["thickness_floor"]),
        slab_roof=float(data["slab"]["thickness_roof"]),
        fck_beam=str(data["concrete"]["beam"]),
        band_width_by_line={_norm(k): float(v) for k, v in pt["width_by_line"].items()},
        band_depth=float(pt["depth"]),
        band_mark_by_width={float(k): str(v) for k, v in pt["mark_by_width"].items()},
        band_line_tolerance=float(pt["line_tolerance"]),
        sizes={
            role: BeamSize(str(v["mark"]), float(v["width"]), float(v["depth"]))
            for role, v in beams.items()
        },
        min_segment=float(data["interior_beams"]["min_segment"]),
        stair_edge_role=str(openings["stair"]["edge_beam"]),
        stair_end_role=str(openings["stair"]["end_beam"]),
        shaft_trimmers=bool(openings["shaft"]["trimmers"]),
        position_match=float(data["tolerances"]["position_match"]),
        cantilever_role=str(cant["beam"]) if (cant := data.get("cantilever_edge")) else None,
        cantilever_min_overhang=float(cant["min_overhang"]) if cant else 300.0,
    )


def load_rules(brain_dir: str | Path, allow_draft: bool = False) -> BeamRules:
    path = Path(brain_dir) / RULES_FILE
    if not path.is_file():
        raise RulesNotApprovedError(f"beam rules not found at {path}")
    return from_dict(yaml.safe_load(path.read_text(encoding="utf-8")), allow_draft)
