---
name: rc-design
description: Entry point for discipline 3, reinforced concrete works (slabs, beams, columns, walls, foundations, ground slabs) to EN 1992-1-1, EN 206 and EN 13670. Use for any RC request - design workflow, anchorage and lap lengths, member checks, reinforcement drawings, bar schedules, concrete specification or calculation report. Not for post-tensioned floors (use pt-floor-design).
---

> **StructIQ merge.** Read the Core Brain first (`03-Safety Rules/safety-rules.md`, then `01-Master Prompt/master-prompt.md`; folder from `core_brain` in `config/paths.yaml`). If it cannot be read, stop and tell the user. Outputs are DRAFT; nothing here is approved, checked or issued, and sizes or values are never invented.
>
> Available: `src/structiq/calc/rc/ec2_anchorage.py`, `python -m structiq.calc.runs.anchorage_check`, the workbook modules in `structiq.qaqc.xlsx`. Beam arrangement is in `structiq.framing`.
>
> Knowledge files named below (`02_disciplines/...`, `01_standards/...`) come from the archived SDSA repository; they move into the Core Brain as DRAFT in the merge's last phase. Use them as reference, not as approved rules.

# Reinforced concrete design (discipline 3)

Read first: `02_disciplines/rc-works/README.md` and `02_disciplines/rc-works/knowledge/rc-design-workflow.md`, plus the repo `CLAUDE.md` / Core Brain safety rules.

## State
EARLY. Only the anchorage/lap check is built (`src/structiq/calc/rc/ec2_anchorage.py`). Member checks, bar-schedule format and registry values are missing (gap G28).

## Route the request
| Request | Do this |
|---|---|
| Design approach / what to check | Follow `02_disciplines/rc-works/knowledge/rc-design-workflow.md` |
| Anchorage and lap lengths | `src/structiq/calc/rc/ec2_anchorage.py`; run script `src/structiq/calc/runs/anchorage_check.py`; workbook `04_tools/xlsxgen/build_anchorage_workbook.py` |
| General notes (concrete, reinforcement) | Skill `structural-drawing`; notes library `01_standards/04-general-notes/04-02-eurocode-notes-library.yaml` |
| Member checks (flexure, shear, punching, columns) | No module yet. Engineer-supplied calculation, or build one in `src/structiq/calc/rc/` with hand-value tests |
| Analysis results | `src/structiq/tools/etabs/ (NOT YET PORTED: Phase 5) ` via skill `structural-calculation-report` |
| Concrete / reinforcement specification | Skill `structural-specification` |
| Package check | Skill `structural-document-qa` |

## Rules
- Concrete class, exposure class, cover, steel grade and loads come from the design basis only.
- Registry values that are null/UNVERIFIED make the dependent check NOT EVALUATED.
- Never mark anything APPROVED. Missing inputs are listed, not assumed.
