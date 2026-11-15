---
name: steel-design
description: Entry point for discipline 2, structural steelwork (frames, beams, columns, bracing, connections, base plates) to the EN 1993 series and EN 1090-2. Use for any steel structure request - design workflow, member or connection checks, steel drawings, steelwork specification or calculation report. Guidance only; no automated steel checks exist yet.
---

> **StructIQ merge.** Read the Core Brain first (`03-Safety Rules/safety-rules.md`, then `01-Master Prompt/master-prompt.md`; folder from `core_brain` in `config/paths.yaml`). If it cannot be read, stop and tell the user. Outputs are DRAFT; nothing here is approved, checked or issued, and sizes or values are never invented.
>
> No steel calculation modules exist yet (stub `src/structiq/calc/steel/`).
>
> Knowledge files named below (`02_disciplines/...`, `01_standards/...`) come from the archived SDSA repository; they move into the Core Brain as DRAFT in the merge's last phase. Use them as reference, not as approved rules.

# Steel structure design (discipline 2)

Read first: `02_disciplines/steel/README.md` and `02_disciplines/steel/knowledge/steel-design-workflow.md`, plus the repo `CLAUDE.md` / Core Brain safety rules.

## State
SKELETON. No steel calculation module, code-registry file, steel drawing standard or example exists (gap G27). Say so in every answer that relies on automation.

## Route the request
| Request | Do this |
|---|---|
| Design approach / what to check | Follow `02_disciplines/steel/knowledge/steel-design-workflow.md` |
| Analysis results (ETABS/SAFE export) | `src/structiq/tools/etabs/ (NOT YET PORTED: Phase 5) etabs_import.py` via skill `structural-calculation-report` |
| Member or connection check | No module yet. Either the engineer supplies a verified calculation, or build a new module in `src/structiq/calc/steel/` with hand-value tests (see below) |
| GA / connection drawings | Skill `structural-drawing` (no steel layers or notes standard yet: propose them, mark PROPOSED, log a gap) |
| Steelwork specification | Skill `structural-specification` |
| Package check | Skill `structural-document-qa` |

## Building a steel check
1. Parameters (partial factors, imperfection factors, limits) go in `config/code_registry/EN1993-<part>_<edition>_CEN.yaml` with `value: null`, `status: UNVERIFIED`. An engineer enters and verifies them.
2. Code in `src/structiq/calc/steel/<check>.py`: pure functions, units via `src/structiq/core/units.py`, status via `src/structiq/core/status.py`.
3. Tests in `tests/test_steel_<check>.py` against hand calculations the engineer supplies or checks.

## Rules
- Never quote EN 1993 clauses, factors or section properties from memory. Section properties come from a supplier table or the engineer.
- Never mark anything APPROVED. Missing inputs are listed, not assumed.
