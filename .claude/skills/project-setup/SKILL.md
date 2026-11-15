---
name: project-setup
description: Create a new freelance project folder in the standard layout, store received architect drawings in a dated set, or record the folder roles of an older project. Use when the user starts a new project, receives an architect drawing (PDF or DWG), asks where a project file belongs, or asks to create or standardise a project folder.
---

# Project setup

Creates and maintains the standard freelance project folder. The layout is in the Core Brain
(`04-Global Workflows/project-folder-layout.yaml`, explained in `project-folder-standard.md`), not in code. Read the Core Brain first
(`03-Safety Rules/safety-rules.md`); the commands stop if it cannot be read.

## Commands (from `D:\Dev\StructIQ`)

```bash
.venv\Scripts\python.exe -m structiq.project new "Short Name" --dry-run     # show the tree, change nothing
.venv\Scripts\python.exe -m structiq.project new "Short Name"
.venv\Scripts\python.exe -m structiq.project receive "<project folder>" "<file>" ... --label "Issue A" --meta meta.csv
.venv\Scripts\python.exe -m structiq.project confirm "<project folder>" RCV-007.03 --drawing-no A-201 --title "East Elevation" --revision A
.venv\Scripts\python.exe -m structiq.project register "<project folder>"
.venv\Scripts\python.exe -m structiq.project adopt "<old project folder>" --dry-run
.venv\Scripts\python.exe -m structiq.project where "<project folder>" structiq_draft
```

- `new` picks the next `PJR-YYYY-NNN` (counted per year from the folders in `01-Freelance`), builds the tree, and writes
  `00-Project Management\project.yaml`, `Drawing Register.csv`, `Received Register.csv` and `Project Tracker.xlsx`.
  Always run `--dry-run` first and show the user the name and number before creating anything on Drive.
- `receive` stores received architect drawings (see "Receiving drawings"). `adopt` is for projects made before this standard: it only
  writes `project.yaml` at the project root from the folders it recognises, and moves, renames and creates nothing; show the detected
  roles and what is missing before writing it.
- Folders are found by role (`where`, or `structiq.drawing.paths.project_folder`), never by hard-coded name. The Drawing Intelligence
  pipeline writes into the `structiq_draft` role: `02-Design Review\Structural Concept\StructIQ Draft` in new projects, the drawing
  folder in adopted ones (`02-Structural Drawing` in old ones).

## Receiving drawings
- One file per drawing (plan, section, elevation separate). Never merge drawings. A combined PDF is stored whole and also split into
  single-sheet copies in `PDF\Split Sheets`.
- Files are copied into `01-Received\Architectural\<date> <label>\{PDF,DWG}` as `RCV-NNN_<drawing no>_<title>_Rev<rev>.<ext>`. `RCV-NNN` is a
  running number for the project, never reused. The original name, SHA-256, set and date are in `Received Register.csv` and `project.yaml`.
- Ask the user for the architect's drawing number, title and revision of each file (or read them from the drawing's title block and show
  them to the user). Never invent them. Give them with `--meta` (CSV columns `file, drawing_no, title, revision`) or `--revision`.
  Files without them are stored as `RCV-NNN_<original name>` and marked "To confirm"; name them later with `confirm` (it renames the file).
- A file already received (same hash) is refused. A newer revision of a drawing number goes in a new set with a new label: the register
  marks it "Current" and the older one "Superseded". Nothing is moved, renamed or deleted when a revision arrives.

## Rules
- Never move, rename or delete a client file or an old project's folders. Superseded material goes to `99-Archive`.
- StructIQ output is DRAFT. `Issued` folders hold one subfolder per revision; what was issued is never changed.
- Do not guess the project name or the received set's label: ask.
- Creating folders on Google Drive is visible to anyone the parent folder is shared with: confirm before running `new` without `--dry-run`.
