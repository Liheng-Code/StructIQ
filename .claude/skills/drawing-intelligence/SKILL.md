---
name: drawing-intelligence
description: Read an architect DWG or DXF and produce the structural layout (gridlines, columns, RC walls, slab boundary, MEP shafts, stairs) as a DXF on S- layers plus a DRAFT review report. Use when the user sends or mentions an architect drawing, layout, section or elevation, or asks for gridlines, column positions, RC walls, slab boundaries, shafts, openings or stairs from a drawing.
---

# Drawing Intelligence

Turns an architect drawing into a draft structural layout for the engineer to check.
Everything it produces is a **DRAFT for engineer review**, never approved.

## Before you start

1. Read the Core Brain, in this order: `03-Safety Rules/safety-rules.md`, then
   `01-Master Prompt/master-prompt.md`. The folder is `core_brain` in `config/paths.yaml`.
   The pipeline also refuses to run if the brain cannot be read; if it stops, tell the
   user and do not work from memory.
2. Confirm the drawing is inside a `PJR-YYYY-NNN_...` project folder on Drive
   (`G:\My Drive\01-Projects\...`), so the output lands in that project's
   `02-Structural Drawing` folder. Otherwise pass `--out-dir`.

## Run it

From `D:\Dev\StructIQ`:

```bash
.venv\Scripts\python.exe -m structiq.drawing.pipeline "G:\My Drive\01-Projects\01-Freelance\PJR-2026-000_Test Project\01-Architect drawing\<file>.dwg"
```

- `.dwg` is converted to DXF first (ODA File Converter if installed, otherwise LibreDWG
  at `D:\Dev\tools\libredwg-0.14.8969`). The big DXF is a local cache in `D:\Dev\_work`.
  The source drawing is never modified.
- Add `--rc-layers "REGEX"` to name the layers that hold RC walls. Without it only layers
  matching `STRUCT|RC|SHEAR|CONCRETE WALL` count as RC.
- Each run writes the **next revision**: `S-LAYOUT <name> Rev NN.dxf` and
  `...Rev NN-report.txt`. Existing revisions are never overwritten.
- Each plan is also placed on its own A3 sheet (layout tabs `A3-PLAN-1`, `A3-PLAN-2`...) from
  the StructIQ template: title block filled (project reference from the `PJR-` folder name,
  revision R00.., issue date, stage DRAFT FOR REVIEW, scale fitted to the plan), grid
  bubbles, general notes. Drawing numbers and client are left blank on purpose. Plan
  numbers follow the order found, not floor levels; tell the engineer to name them.

## What it extracts

| Item | Layers written | How |
|---|---|---|
| Gridlines + labels | `S-GRID`, `S-GRID-TXT` | orthogonal lines on GRID layers, labels from block attributes |
| Columns | `S-COLS`, `S-COLS-TXT` | blocks of simple geometry with a solid hatch, column-sized; related to the grid |
| RC walls | `S-WALL` | wall layers matching the RC pattern. **Brick walls are counted, not drawn.** |
| Slab boundary | `S-SLAB-EDGE`, `S-SLAB-CHECK`, `S-SLAB-TXT` | outline polylines on the slab layer, area, grid coverage |
| MEP shafts | `S-OPEN`, `S-OPEN-ROOM`, `S-OPEN-CHECK`, `S-OPEN-TXT` | text labels enclosed by walls/columns |
| Stairs | `S-STAIR`, `S-STAIR-TXT` | stacked tread rectangles (flights, tread depth, footprint) |
| Lift cores | `S-WALL` (core wall), `S-OPEN` (clear shaft), `S-OPEN-TXT` | block holding a lift car symbol on an ELEVATOR/LIFT layer; the wall body outline in it is the RC core |

All text in the output is Arial (`STIQ-TEXT`) at 1.5 mm at A3: model-space height = 1.5 x the
plan's sheet scale. Gridlines are trimmed to 2.5 m beyond the outermost crossing gridline so
each plan fits its sheet at a standard scale.

## After it runs

Read the report and give the engineer a short summary: counts per plan, then **every line
marked `!`** as a question. Typical ones: no RC walls identified, stair or shaft with no
slab void drawn, plans with no slab outline, labels with no closed boundary, off-grid
columns, columns missing at grid intersections, no lift found. Do not hide a flag, do not
adjust a result to make it look consistent, and never say the layout is approved or safe.

Tell the engineer to overlay the output DXF on the architect drawing in AutoCAD before
relying on it. DXF can be saved as DWG from AutoCAD (or converted with the ODA File
Converter once installed).

## Known limits

- RC walls are only recognised by layer name. Architects often draw RC and brick on the
  same layers; ask the engineer which layers or areas are RC rather than guessing.
- Detection is geometric and tuned on one drawing; layer and block names differ between
  architects. Treat the first run on a new drawing as a test.
- Curved slab edges, non-orthogonal grids and walls rotated off 90 degrees are flagged,
  not followed.
- Sections and elevations are not interpreted yet (only plans with gridlines).
