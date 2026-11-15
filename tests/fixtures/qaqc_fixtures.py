"""Made-up fixtures for the qaqc tests (no project data). Values are for testing, not a design."""

from __future__ import annotations

import copy

DESIGN_BASIS = {
    "project": {
        "code": "PJR-2026-999",
        "name": "Test Building",
        "description": "Synthetic project used by the tests",
        "stage": "PRELIMINARY",
        "client": "Test Client",
        "drawing_prefix": "TB-STR",
        "revision": "R00",
        "issue_date": "01-JAN-2027",
        "structure_types": ["rc"],
    },
    "approval": {"status": "DRAFT", "prepared_by": "Test Author", "checked_by": None, "approved_by": None},
    "design_assumptions": {
        "design_working_life_years": 50,
        "consequence_class": "CC2",
        "units": {"length": "m", "section": "mm", "force": "kN", "stress": "MPa", "pressure": "kN/m2"},
    },
    "standards": [
        {"id": "EN 1990", "generation": "1st", "edition": "2002", "used_for": "Basis of design"},
        {"id": "EN 1991-1-1", "generation": "1st", "edition": "2002", "used_for": "Actions"},
        {"id": "EN 1992-1-1", "generation": "1st", "edition": "2004", "used_for": "Concrete"},
    ],
    "national_annex": {"mode": "CEN_RECOMMENDED", "country": None, "basis_note": "CEN recommended values (test)"},
    "materials": [
        {"id": "MAT-C1", "element": "Concrete", "spec": "C30/37", "status": "assumed", "source": "test"},
        {"id": "MAT-S1", "element": "Reinforcement", "spec": "fyk 390", "status": "assumed", "source": "test"},
    ],
    "open_items": [{"id": "F1", "status": "open", "description": "Confirm the concrete class with the client"}],
}

ANCHORAGE_INPUTS = {
    "id": "CALC-TEST-001",
    "title": "Synthetic anchorage check",
    "concrete_class": "C30/37",
    "fyk": 390,
    "bars": [12, 16, 20, 25, 32],
    "sources": {"concrete": "test input", "fyk": "test input"},
    "design_basis_refs": ["MAT-C1", "MAT-S1"],
    "compare_with": {
        "label": "Synthetic drawing table",
        "fctk005_override": 2.03,
        "note": "Made-up comparison values.",
        "rows": {
            "good": [350, 470, 590, 740, 940],
            "poor": [500, 670, 840, 1050, 1340],
            "lap_good": [520, 700, 880, 1100, 1410],
            "mandrel": [48, 64, 140, 175, 224],
        },
    },
}


def design_basis():
    return copy.deepcopy(DESIGN_BASIS)


def anchorage_inputs():
    return copy.deepcopy(ANCHORAGE_INPUTS)
