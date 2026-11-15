---
name: pt-floor-design
description: Entry point for discipline 1, post-tensioned floors (PT slabs and band beams; bonded by default, unbonded allowed) to EN 1992-1-1. Use for any PT floor request - scheme design, tendon layout, PT screening checks, PT drawings, PT calculation notes, or checking a PT design or drawing set. Routes to the PT tools and the shared production skills.
---

> **StructIQ merge.** Read the Core Brain first (`03-Safety Rules/safety-rules.md`, then `01-Master Prompt/master-prompt.md`; folder from `core_brain` in `config/paths.yaml`). If it cannot be read, stop and tell the user. Outputs are DRAFT; nothing here is approved, checked or issued, and sizes or values are never invented.
>
> Available: `src/structiq/calc/pt/ec2_pt_screen.py`, `python -m structiq.core.design_basis`. PT rulesets are unreviewed DRAFT (gaps G33/G34): do not apply them as code requirements.
>
> Knowledge files named below (`02_disciplines/...`, `01_standards/...`) come from the archived SDSA repository; they move into the Core Brain as DRAFT in the merge's last phase. Use them as reference, not as approved rules.

# PT floor design (discipline 1)

Read first: `02_disciplines/pt-floor/README.md` (what exists and what is missing) and the repo `CLAUDE.md` / Core Brain safety rules.

## Scope
- Bonded post-tensioning is the company default; unbonded is also allowed (EN 1992-1-1 covers both). Use what the PT basis `system.type` states; if it is not stated, assume bonded and list it as an open item. Never switch a stated system silently.
- Eurocodes, CEN recommended values unless the design basis records a National Annex.
- Tendon forces, strand counts, profiles and losses come from a PT analysis or the engineer. Never fill them in.

## Route the request
| Request | Do this |
|---|---|
| Preliminary scheme from a plan | Follow `02_disciplines/pt-floor/knowledge/pt-design-guide.md` |
| Tendon arrangement / profile rules | `02_disciplines/pt-floor/knowledge/pt-detailing-guide.md` |
| Type A layout choice (banded direction), shortening, delay strips, restraint and crack mitigation | Ruleset `02_disciplines/pt-floor/knowledge/pt-master-ruleset.yaml` (guide: `pt-master-ruleset.md`). Quote rule IDs. All rules UNVERIFIED; ACI / practice rules are not Eurocode requirements (gap G33) |
| Tendon profile shape, CGS heights, minimum radius, friction / wobble plausibility, checks triggered by bonded / unbonded | Ruleset `02_disciplines/pt-floor/knowledge/pt-tendon-profile-ruleset.yaml` (guide: `pt-tendon-profile-ruleset.md`). Quote rule IDs. All rules UNVERIFIED; friction values come from the ETA / supplier (gap G34) |
| PT drawings (PT-001 notes, PT-101 plan, PT-102 profiles, schedule) | Skill `pt-drawings` |
| Full 10-sheet PT slab package from a draft layout (body layout, beam / drop-panel / slab reinforcement, tendon plan and profiles) | Skill `pt-slab-package`. Its "defaults" section lists numbers (materials, partial factors, friction, wobble): treat every one as ASSUMED / TBC unless the design basis records it (gap G30). Use the PT basis system type (bonded default) |
| Screening checks (stresses at transfer/service, balanced load) | `src/structiq/calc/pt/ec2_pt_screen.py`; pattern in `03_projects/PJR-2F-PT/runs/`. Label every result INDICATIVE |
| Calculation note / workbook | Skill `structural-calculation-report` |
| Specification | Skill `structural-specification` |
| Package check before issue | Skill `structural-document-qa` |
| More than one deliverable | Skill `structural-documentation` (coordinator) |

## Before any work
1. Locate `<project folder>/design-basis.yaml` and the PT basis `<project folder>/pt-basis.yaml`. Validate both (`04_tools/design_basis/validate_design_basis.py`, `04_tools/cadgen/validate_pt_basis.py`).
2. List missing inputs in plain language and stop on anything that drives a result.

## Rules
- A check whose inputs are ASSUMED reports INDICATIVE; a check whose registry value is UNVERIFIED reports NOT EVALUATED.
- Never mark anything APPROVED. Log new gaps in `the SDSA gap register on Drive (`docs\merge\sdsa-gap-register.md`)`.
- Run `python -m unittest discover -s tests` after changing any code.
