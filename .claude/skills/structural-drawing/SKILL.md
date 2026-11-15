---
name: structural-drawing
description: Produce structural drawing sheets (cover page, drawing list, general notes, layouts, details) to company drawing standards for AutoCAD - DXF/DWG and PDF. Use for any request to create, revise or check structural drawings or sheets, or to apply the company title block, layers and text styles.
---

> **StructIQ merge.** Read the Core Brain first (`03-Safety Rules/safety-rules.md`, then `01-Master Prompt/master-prompt.md`; folder from `core_brain` in `config/paths.yaml`). If it cannot be read, stop and tell the user. Outputs are DRAFT; nothing here is approved, checked or issued, and sizes or values are never invented.
>
> Sheets: StructIQ's A3 template and pipeline (`python -m structiq.drawing.pipeline`; see skill `drawing-intelligence`). The company cover, drawing-list and notes builders (`cadgen/build_sheets`, `build_notes_and_details`) are NOT ported. Validate with `python -m structiq.drawing.validate`; move old sheets onto the standard with `python -m structiq.drawing.restandardise`.
>
> Knowledge files named below (`02_disciplines/...`, `01_standards/...`) come from the archived SDSA repository; they move into the Core Brain as DRAFT in the merge's last phase. Use them as reference, not as approved rules.

# Structural Drawing

## Before drawing
1. Read the project design basis (`03_projects/<code>.yaml`); take project code, name, client, prefix, stage, revision and date from it.
2. Read the standards, in this order, noting each file's status header:
   - `01_standards/01-title-block/`, `02-cover-page/`, `03-drawing-index/`, `04-general-notes/` (derived from the WH-STR-SD R00 drawing set; approved by the user 14-OCT-2026)
   - `05-drafting-styles/` (company standard: text, annotation, line types, layers CSV)
3. Read `references/drawing-package-format.md` (what each sheet type looks like) and `references/cad-workflow.md` (what can and cannot be claimed about outputs).

## Rules
- A3 landscape, two-row title block across the top, border and layout exactly per standard. Do not restyle.
- Text, dimensions, hatches, line weights and layers only from `05-drafting-styles`. Layer names/colours come from `05-04-layer-standards.csv`; if a needed layer does not exist, add it to the gap register - do not invent it silently.
- Separate geometry/data (member sizes, grid, levels) from presentation. Member data must come from the design basis/calc outputs; do not draw dimensions or reinforcement that no source supports. Mark unconfirmed values "TBC" on the sheet.
- Every sheet number must exist in the document register; update the drawing list (002) whenever sheets change.
- **Honesty about outputs:** only say "DWG generated/validated" if a native CAD tool produced and opened it. A DXF written by script is a DXF. A rendered PDF/PNG is a preview. Say which one you made and what was not checked (fonts, plot style, xrefs).

## Output pipeline (built for cover 001, drawing list 002, and Eurocode general notes & standard details 003-007)
- Cover (001) & Drawing List (002): `python 04_tools/cadgen/build_sheets.py --design-basis <db.yaml> --register <register.csv>  --out <dir> [--include-notes-details]`
- General Notes & Standard Details (003-007): `python 04_tools/cadgen/build_notes_and_details.py --design-basis <db.yaml> --register <register.csv>  --out <dir> [--overrides <notes-overrides.yaml>] [--dwg]`
- Standalone reusable CAD blocks & master sheet templates live in `01_standards/06-templates/` (`blocks/` and `sheets/`), driven by `04-general-notes/04-02-eurocode-notes-library.yaml` and `src/structiq/calc/rc/ec2_anchorage.py`. Rebuild templates with `python 04_tools/cadgen/build_notes_and_details.py --export-templates  [--dwg]`.
- Always validate every DXF with `python -m structiq.drawing.validate <sheet.dxf> --standards ... --design-basis ... --register ...` and run `python -m structiq.qaqc.doc_control` after changing the sheet list.
