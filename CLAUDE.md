# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

StructIQ is an AI-powered structural engineering assistant. This repository
holds the code. Design documents are on Google Drive at
`G:\My Drive\04-Systems Development\06-StructIQ\docs` (tech stack, folder
plan, six-layer diagram).

## The Core Brain is the source of truth

The engineering identity, principles, safety rules and workflows are **not**
stored in this repository. They live on Google Drive in the Core Brain
(path set by `core_brain` in `config/paths.yaml`; default
`G:\My Drive\04-Systems Development\06-StructIQ\01-Core Brain`).

Before any engineering work, read, in this order:

1. `03-Safety Rules/safety-rules.md` (hard limits; override everything)
2. `01-Master Prompt/master-prompt.md`
3. `02-Engineering Principles/*.md`
4. `04-Global Workflows/*.md`

Record the brain's `VERSION` in every deliverable you generate. If the brain
folder cannot be read (Drive offline, wrong drive letter), stop and tell the
user; do not fall back to rules from memory.

Do not duplicate brain rules in this file. Change them in the Core Brain.

## Drawing Intelligence

Architect drawings are read with the `drawing-intelligence` skill
(`.claude/skills/drawing-intelligence/SKILL.md`). One command does everything:
`.venv\Scripts\python.exe -m structiq.drawing.pipeline "<drawing.dwg|.dxf>"`.
Only RC walls are drawn; brick walls are counted in the report. Each run writes the
next `Rev NN` and never overwrites an earlier one.
Each generated report includes an unchecked engineer review checklist based on its
flagged findings; it remains a draft and the checklist does not imply approval.

Beams (`src/structiq/framing/`): `learn.py` measures the engineer's sample design, `rules.py` loads
the approved rules from the Core Brain (`beam-rules.yaml`), `arrange.py` proposes beams per plan,
`draw.py` draws them, `compare.py` checks them against the sample. Sizes are preliminary and are
never a design check; PT bands are only marked.

Merged from the SDSA project (see `docs/merge/`): `structiq.core` (units, status, code registry, schemas, design-basis
validator), `structiq.calc` (EC2 anchorage and PT screening), `structiq.qaqc` (docgen, calculation workbooks, document register,
package QA), `drawing/layers.py`, `validate.py` and `restandardise.py` (layer standard). Check status words are PASS, FAIL,
NOT EVALUATED, BLOCKED, WARNING, ENGINEER REVIEW REQUIRED: NOT EVALUATED is never PASS and nothing here produces APPROVED. The
code registry holds references only; every value is null and UNVERIFIED until an engineer verifies it. ETABS/SAFE importers are in `structiq.tools.etabs` (unverified on real SAFE exports) and a read-only MCP server is in
`structiq.tools.mcp` (`docs/mcp.md`). Skills for PT floors, RC,
steel, documentation, drawing, specification, calculation reports and QA are in `.claude/skills`; those that need unported tools
say so in their banner.

Project folders (`src/structiq/project/`): `python -m structiq.project new "Name"` creates the next `PJR-YYYY-NNN` folder from the layout
in the Core Brain (`04-Global Workflows/project-folder-layout.yaml`); `receive` stores architect drawings in a dated set; `adopt`
records the roles of an old project. Tools find folders by role (`structiq.drawing.paths.project_folder`), with the old folder names as a
fallback for projects that have no `project.yaml`. Skill: `.claude/skills/project-setup`.

## Where things live

- Code: this repository (`src/structiq`, `tests`, `.claude`, `apps`).
- Codes and standards: `knowledge.reference_library` in `config/paths.yaml`.
  Never copy them into this repository.
- Client project data: `projects` in `config/paths.yaml`. Never commit it.
- Deep recursive scans of `G:\My Drive` are slow and can time out; target
  specific folders.

## Conventions

- Python 3.11+, `src` layout, package name `structiq`.
- Run tests with `pytest`.
- `config/paths.yaml` is local and git-ignored; edit `paths.example.yaml` for
  shared changes.
- DWG input is always converted to DXF first (`structiq.drawing.convert.dwg_to_dxf`):
  ODA File Converter when installed, otherwise LibreDWG `dwg2dxf`
  (`D:\Dev\tools\libredwg-0.14.8969`). Code and skills only read DXF (ezdxf).
  Never edit the source DWG; write results to new files.
- Output locations (`structiq.drawing.paths`): the large converted DXF is a local
  cache in `D:\Dev\_work` (override with `STRUCTIQ_WORK_DIR`); deliverables
  (structural-layer DXF/DWG, review reports) go to
  the project's `structiq_draft` folder on Google Drive (`02-Structural Drawing` in old projects), named `... Rev NN`.
- ETABS, SAFE, AutoCAD and Revit adapters run only on a Windows desktop with
  the software installed; keep them in `src/structiq/tools` behind interfaces
  so the calculation core stays testable without them.
