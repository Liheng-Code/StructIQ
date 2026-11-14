# Copilot instructions for StructIQ

## Repository purpose

StructIQ is an AI-powered structural engineering assistant. The repository holds the implementation; the engineering identity, safety rules, and approved standards live in the external Core Brain on Google Drive and are referenced via `config/paths.yaml`.

The key workflow is:
- read the Core Brain before engineering work
- ingest the architect DWG/DXF drawing
- convert DWG to DXF when needed
- extract structural elements and produce a structural layout DXF + report
- optionally arrange preliminary beams from approved rules
- keep revisions incremental and never overwrite earlier deliverables

## Commands to run

Setup (from repo root):
```powershell
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install -e ".[dev]"
```

Run the full test suite:
```powershell
pytest
```

Run a single test file:
```powershell
pytest tests/test_drawing_pipeline.py -q
```

Run one specific test:
```powershell
pytest tests/test_framing_arrange.py -k "rules_must_be_approved" -q
```

Run the drawing pipeline directly:
```powershell
.\.venv\Scripts\python.exe -m structiq.drawing.pipeline "<drawing.dwg|.dxf>" [--rc-layers "REGEX"] [--out-dir "DIR"]
```

There is no separate lint command configured in `pyproject.toml`; validation in this repo is via pytest.

## High-level architecture

### External configuration and brain
- `config/paths.example.yaml` defines the local machine setup.
- `config/paths.yaml` is a git-ignored local override that points to Google Drive folders such as the Core Brain, reference library, and project folders.
- The Core Brain is the source of truth for safety rules, master prompts, engineering principles, and approved beam rules. Code must not duplicate those rules locally.

### Drawing Intelligence
- `src/structiq/drawing/` contains the DWG/DXF pipeline and structural drawing logic.
- `pipeline.py` is the main entry point for the drawing workflow; it validates the Core Brain, converts DWG to DXF as needed, extracts layout data, and writes a new revisioned `.dxf` plus report.
- `convert.py` handles conversion to DXF using ODA File Converter or LibreDWG.
- `layout.py`, `grids.py`, `columns.py`, `walls.py`, `slabs.py`, `openings.py`, `stairs.py`, and `template.py` are the extraction and document-generation pieces.

### Framing logic
- `src/structiq/framing/` manages preliminary beam arrangement.
- `rules.py` loads the engineer-approved `beam-rules.yaml` from the Core Brain and refuses draft rules.
- `learn.py` calibrates from the engineer’s sample design.
- `arrange.py` proposes beam lines and bands based on the plan.
- `draw.py` draws the preliminary framing.
- `compare.py` checks the arrangement against the sample.

### Shared services and project structure
- `src/structiq/core/` holds shared data models and services.
- `src/structiq/calc/` is for calculation logic.
- `src/structiq/tools/` is for adapters to external engineering software.
- `templates/` contains drawing/report templates.
- `tests/` contains the pytest coverage for drawing and framing workflows.
- `apps/` is reserved for app-level work; it is not the primary implementation in this repository yet.

## Key conventions and repo-specific rules

- Use Python 3.11+ and the `src` layout; the package name is `structiq`.
- Keep `config/paths.yaml` machine-local and git-ignored. Update `config/paths.example.yaml` for shared path changes.
- Treat the Core Brain as read-only source material for engineering rules. Do not duplicate or “recreate” those rules in repo files.
- DWG inputs are always converted to DXF before downstream processing. The DXF is the canonical input for the drawing logic.
- Never overwrite earlier deliverables. The pipeline writes the next revision with names like `S-LAYOUT <name> Rev 01.dxf` and a matching `-report.txt`.
- Generated reports include an unchecked engineer review checklist derived from flagged findings; it is a manual review aid and does not change the DRAFT status or imply approval.
- Structural output is written to project folders under the configured Drive path rather than into the repo itself.
- The repository does not keep codes, standards, or client project data. Those are stored in the configured knowledge/project folders outside the repo.
- Tests are the primary validation mechanism in this project; follow the existing pytest patterns for any new behavior.

## When working in this repo

- Prefer the project’s existing drawing and framing modules instead of introducing ad hoc scripts.
- Check the configured Core Brain and path setup before running engineering workflows that rely on the approved rules or output locations.
- For new tests, match the existing pytest style and focus on the drawing/framing behaviors that the change affects.
