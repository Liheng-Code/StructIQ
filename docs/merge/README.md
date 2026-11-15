# Merge of the SDSA project into StructIQ

On 2026-11-15 the "Structural Design Specialist AI Assistants" project (SDSA, 26 commits, last `8c75d5c`) was merged into
StructIQ. The code was **ported** into `src/structiq` with its tests; no git history was merged. SDSA stays as a read-only archive.

| Document | What it holds |
|---|---|
| [sdsa-inventory.md](sdsa-inventory.md) | Every SDSA file: where it went, or why it was not merged, by phase |
| [layer-mapping.md](layer-mapping.md) | Company layer standard vs StructIQ, and the decisions taken |
| `../adr/` | The SDSA architecture decisions with their StructIQ status |
| `../mcp.md` | The read-only MCP server (reworked from SDSA) |

## What went where
- `structiq.core`: units, check status, code registry (references only, values null / UNVERIFIED), schemas, design-basis validator.
- `structiq.calc`: PT screening, EN 1992 anchorage check.
- `structiq.qaqc`: specification and calculation-report generator, anchorage workbook, document register check, package QA.
- `structiq.drawing`: `layers`, `validate`, `restandardise` (company layer standard on top of StructIQ's A3 template).
- `structiq.tools`: ETABS/SAFE importers, software probe, MCP server.
- `.claude/skills`: the ten SDSA skills, each with a banner that sends the reader to the Core Brain first.
- Core Brain (Drive, 0.3.0-draft): the two PT rulesets as DRAFT / UNVERIFIED, default code basis, check status words.

## Not merged
- `03_projects` (three project folders): client and third-party data. The SDSA gap register is on Drive only
  (`docs\merge\sdsa-gap-register.md`).
- Company title block, cover / drawing-list / notes sheet builders, PT sheet builders (deferred), the generated NotebookLM pack,
  the SAFE `.inp` model, the PT design and detailing guides (long, may paraphrase published sources; left in the archive).

## Open items for the engineer
1. Review the PT rulesets (Core Brain `05-` and `06-`); accept, change or remove each rule. They conflict in places (shortening
   rate, delay-strip time) and some are ACI or practice rules, not Eurocode.
2. Fill the EN 1992-1-1 code registry values and mark them VERIFIED with a name and date; until then checks report NOT EVALUATED.
3. Install LibreOffice (or set `tools.libreoffice` in `config/paths.yaml`) to run the four PDF / workbook-recalculation tests.
4. Test the ETABS/SAFE importers on a real SAFE export and an ETABS export that includes results.
5. Decide when to archive or make private the SDSA GitHub repository: its history holds client and third-party project files.
