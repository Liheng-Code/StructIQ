# StructIQ

AI-powered structural engineering assistant: design, analyse, deliver.

This folder is the **code** repository. Design documents, the brand and the
layer diagram live on Google Drive at
`G:\My Drive\04-Systems Development\06-StructIQ\docs`.

## Layout

| Path | Purpose | Layer in the design doc |
|---|---|---|
| `CLAUDE.md` | Engineering identity, principles and safety rules for Claude | 01 Core Brain |
| `.claude/skills/`, `.claude/agents/` | One skill or subagent per module (calculation note, specification, BOQ, RFI...) | 04 Execution Engine |
| `config/paths.example.yaml` | Pointers to the reference library and project folders on Drive | 02 Knowledge, 03 Project Intelligence |
| `src/structiq/drawing/` | Drawing Intelligence: DWG/DXF in, structural layout + report out (`pipeline.py` is the entry point) | 04 Execution Engine |
| `src/structiq/core/` | Units, data models, shared services | 04 shared services |
| `src/structiq/calc/` | Calculation code | 05 Engineering Tools (python) |
| `src/structiq/tools/` | Adapters for ETABS, SAFE, AutoCAD, Excel, document generation | 05 Engineering Tools |
| `src/structiq/qaqc/` | Validation rules and independent checks | 07 QA/QC |
| `templates/` | Calculation note, specification, BOQ and report templates | 06 Templates |
| `tests/` | Pytest test cases | 07 QA/QC test cases |
| `apps/` | Frontend (Next.js) and backend (FastAPI), to be added later | 08 Application |

Codes, standards and client project files are **not** stored here. They stay on
Drive and are referenced through `config/paths.yaml`.

## Getting started

Prerequisites: Git and Python 3.11 or newer.

```
git init
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
pytest
```

Copy `config/paths.example.yaml` to `config/paths.yaml` and adjust the paths.
