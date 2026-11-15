---
name: drawing-split
description: Split a combined architect DWG or DXF (many floor plans, sections and elevations in one file) into one clean file per drawing, and register each piece in the project's Received Register. Use when the user wants a floor, section or elevation separated from a combined drawing, or asks to cut, extract or purge a drawing file.
---

# Drawing split

Does what the engineer does by hand: copy the file, delete everything that is not the wanted drawing, purge, save. One file per
drawing, so each can be revised and read on its own (project standard: one file per drawing).

Read the Core Brain first (`03-Safety Rules/safety-rules.md`). Everything produced is a working copy for the engineer to check.
The received file is never changed.

## Steps (from `D:\Dev\StructIQ`)

1. The combined file must already be stored and named in the project (`project-setup` skill: `receive`, then `confirm`; a combined DWG is
   `RCV-001_SET_Combined Drawing Set_RevA`). A file that is not named yet is refused.
2. List what is in it, with a picture to look at:
   ```bash
   .venv\Scripts\python.exe -m structiq.project views "<project folder>" RCV-001 --preview views.png
   ```
   Open the PNG and show it to the user. Each box is a view with a number and the title found in the drawing. A sheet that holds
   several drawings can be looked into with `--within N` (the numbers then refer to the drawings inside sheet N).
3. Ask the user which view is which drawing. Never guess a floor from a title that does not match (titles like "1st Floor Plan" can be
   level marks on a section, not a plan). Titles that are wrong or missing are given by the user.
4. Cut the chosen drawings:
   ```bash
   .venv\Scripts\python.exe -m structiq.project split "<project folder>" RCV-001 --view 9="Ground Floor Plan" --view 10="First Floor Plan" --margin 500
   ```
   Add `--dwg` to save a DWG through AutoCAD (needs AutoCAD; default is DXF). The pieces are `RCV-001.NN_SET_<title>_RevA` in
   `Split Sheets`, status `Derived`, with the parent's number in `derived_from`.
5. Tell the user how many entities were kept and dropped (the register note has it). Anything that crossed a drawing's edge is dropped
   and counted, not moved. Ask them to open one piece in AutoCAD and check it against the original before relying on it.

## What it does and does not do
- Finds drawings by grouping entities that lie close together; very large entities (long stray lines) are ignored so they do not join
  everything. It works on layout in model space, not on paper-space sheets.
- Builds a new clean file from the entities that lie fully inside a drawing's window, with only the blocks, layers and linetypes they use
  (this is the "purge"). A copy of a converted file cannot be used because it holds half-written objects that make AutoCAD reject it.
  File sizes drop a lot (a 30 MB combined file gave about 0.2 MB per drawing as DWG).
- A DWG is read through a DXF made by LibreDWG, which can miss detail (dimension associations, dynamic-block grips). Check the result.
- AutoCAD's own PURGE crashed on such a converted file, so it is off; `--dwg` runs AUDIT and SAVEAS only.
- Not for PDFs (`receive` splits PDF pages already), and not for combined DWGs that are laid out in paper space.

## Direct use without a project
```bash
.venv\Scripts\python.exe -m structiq.drawing.split scan "<file.dwg|.dxf>" --preview views.png
.venv\Scripts\python.exe -m structiq.drawing.split export "<file>" --view 9 --out "<new.dxf>" --margin 500
```
Tune with `--gap`, `--max-entity` and `--min-entities` if drawings are merged or missed.
