---
name: structural-specification
description: Write structural technical specifications (general requirements, materials, workmanship, quality control, inspection and testing) as DOCX and PDF following company specification standards. Use when asked to create, revise or check a structural specification or a specification section.
---

> **StructIQ merge.** Read the Core Brain first (`03-Safety Rules/safety-rules.md`, then `01-Master Prompt/master-prompt.md`; folder from `core_brain` in `config/paths.yaml`). If it cannot be read, stop and tell the user. Outputs are DRAFT; nothing here is approved, checked or issued, and sizes or values are never invented.
>
> Available: `python -m structiq.qaqc.docgen`. The example content file named below was client project data and is not in this repository: write a new content file.
>
> Knowledge files named below (`02_disciplines/...`, `01_standards/...`) come from the archived SDSA repository; they move into the Core Brain as DRAFT in the merge's last phase. Use them as reference, not as approved rules.

# Structural Specification

## Status
`01_standards/07_Structural-Specification/` has NOT been authored yet. Until it exists, follow `references/spec-format.md` (PROPOSED, derived from the lettered-section structure of the WH-STR-SD general notes) and say so in the document control block. If `07_*` files exist later, they override the reference.

## Workflow
1. Read the design basis (codes, National Annex mode, materials, loads, stage, revision). Specification clauses must agree with it and with drawing general notes.
2. Read `references/spec-format.md`, and the relevant general-note sheets of the drawing set (003-007) so the spec does not contradict them.
3. Draft by section. Every requirement cites its source: Eurocode/EN clause, design-basis item, or drawing sheet. If no source can be named, mark `[SOURCE TBC]` - never invent a clause number, test frequency, tolerance or class.
4. Anything the design basis marks `assumed`/`to_confirm` stays visibly flagged in the text.
5. Generate DOCX + PDF with the generator: write a content file (see `03_projects/PJR-2026-003/content/specification.yaml`) and run `python -m structiq.qaqc.docgen <content.yaml> --design-basis <db.yaml> --out <dir>`. It numbers clauses itself, stops on any clause without a source, stamps DRAFT, appends open items, and never fills checked/approved cells. Clauses copied from issued drawings must carry `status: seed`.
6. Check: heading numbering continuous; cross-references resolve; no unresolved placeholders except flagged ones; project code/revision/date match the register; open and render the output files.
7. Hand to `structural-document-qa`; final issue needs authorised engineering review.

Never state compliance ("complies with EN 1090-2") without naming the verified basis.
