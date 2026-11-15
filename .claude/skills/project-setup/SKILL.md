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
.venv\Scripts\python.exe -m structiq.project new "Short Name" --received "C:\path\plan.pdf" "C:\path\plan.dwg" --label "Issue A"
.venv\Scripts\python.exe -m structiq.project receive "<project folder>" "<file>" ... --label "Issue B"
.venv\Scripts\python.exe -m structiq.project adopt "<old project folder>" --dry-run
.venv\Scripts\python.exe -m structiq.project where "<project folder>" structiq_draft
```

- `new` picks the next `PJR-YYYY-NNN` (counted per year from the folders in `01-Freelance`), builds the tree, and writes
  `00-Project Management\project.yaml`, `Drawing Register.csv` and `Project Tracker.xlsx` (the workflow steps).
- Always run `--dry-run` first and show the user the name and number before creating anything on Drive.
- `receive` copies drawings into `01-Received\Architectural\<date> <label>\{PDF,DWG}` and records their SHA-256 in `project.yaml`.
  A set is never overwritten: a revised drawing needs a new label. The originals are not touched.
- `adopt` is for projects made before this standard. It only writes `project.yaml` (at the project root) from the folders it recognises.
  It moves, renames and creates nothing. Show the detected roles to the user and say which are missing before writing it.
- Folders are found by role (`where`, or `structiq.drawing.paths.project_folder`), never by hard-coded name. The Drawing Intelligence
  pipeline writes into the `structiq_draft` role: `02-Design Review\Structural Concept\StructIQ Draft` in new projects, the drawing
  folder in adopted ones (`02-Structural Drawing` in old ones).

## Rules
- Never move, rename or delete a client file or an old project's folders. Superseded material goes to `99-Archive`.
- StructIQ output is DRAFT. `Issued` folders hold one subfolder per revision; what was issued is never changed.
- Do not guess the project name or the received set's label: ask.
- Creating folders on Google Drive is visible to anyone the parent folder is shared with: confirm before running `new` without `--dry-run`.
