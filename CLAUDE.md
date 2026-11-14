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
  `<project>\02-Structural Drawing` on Google Drive, named `... Rev NN`.
- ETABS, SAFE, AutoCAD and Revit adapters run only on a Windows desktop with
  the software installed; keep them in `src/structiq/tools` behind interfaces
  so the calculation core stays testable without them.
