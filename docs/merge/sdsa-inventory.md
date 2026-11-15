# SDSA to StructIQ inventory (Phase 0)

Source: `Structural-Design-Specialist-AI-Assistants` (SDSA), 26 commits, last `8c75d5c`.
Method: code is ported into `src/structiq` with tests; no git history is merged; SDSA stays as a read-only archive.
Status values: **port** (code/tests move), **adapt** (content rewritten for StructIQ), **brain** (goes to the Core Brain on Drive as DRAFT),
**drive** (stays on Drive, not in git), **ref** (kept as reference only), **skip** (not merged).

| SDSA path | Destination | Status | Phase | Note |
|---|---|---|---|---|
| `04_tools/calc_lib/core/{units,status,registry,schemas}.py` | `src/structiq/core/` | port | 2 | pint, CheckStatus, registry loader, pydantic schemas. mypy strict. |
| `04_tools/calc_lib/pt/ec2_pt_screen.py` | `src/structiq/calc/pt/` | port | 2 | Hand-value tests move with it. |
| `04_tools/calc_lib/rc/ec2_anchorage.py` | `src/structiq/calc/rc/` | port | 2 | |
| `04_tools/calc_lib/runs/anchorage_check.py` | `src/structiq/calc/runs/` | port | 2 | Writes JSON result. |
| `04_tools/calc_lib/steel/` | `src/structiq/calc/steel/` | port | 2 | Empty stub (gap G27). |
| `04_tools/code_registry/*.yaml, README.md` | `config/code_registry/` | port | 2 | References only; all values null / UNVERIFIED. |
| `04_tools/design_basis/validate_design_basis.py` | `src/structiq/core/design_basis.py` | port | 2 | |
| `04_tools/paths.py` | merged into `structiq.drawing.paths` / `config/paths.yaml` | adapt | 1 | Hardcoded locations move to config. |
| `04_tools/cadgen/{build_sheets,common}.py` | none | skip | 3 | Builds the company title block (`STR_TITLEBLOCK_A3`). StructIQ keeps one A3 template (`drawing.template`), so these are not ported. `common` layer loading is replaced by `drawing.layers`. |
| `04_tools/cadgen/{pt_plan,pt_profiles,pt_notes,build_notes_and_details,validate_pt_basis}.py` | later, with the PT rules | deferred | 6+ | PT sheet builders sit on the company title block and the unreviewed PT rulesets (G33/G34). Revisit after the engineer reviews the PT rules. |
| `04_tools/cadgen/validate_dxf.py` | `src/structiq/drawing/validate.py` | adapt (done) | 3 | Rewritten for the StructIQ standard: layers, STIQ- Arial styles, A3 title block. Register / design-basis tie-out not ported. |
| `04_tools/cadgen/restandardise.py` | `src/structiq/drawing/restandardise.py` | adapt (done) | 3 | Layer remap, text style, override reset; no company title block or register. New file `drawing/layers.py` holds extras, aliases and the legacy map. |
| `04_tools/cadgen/probe_cad.py` | `src/structiq/tools/probe.py` | adapt | 1 | Hardcoded `C:\Program Files` paths go to `paths.yaml`. |
| `04_tools/model_builder/dxf_geometry.py` | ideas only | ref | 3 | StructIQ's `drawing/` readers stay; pour-strip / cast-later logic reviewed later. |
| `04_tools/docgen/build_document.py` | `src/structiq/qaqc/docgen.py` | port | 4 | Needs python-docx, LibreOffice for PDF. |
| `04_tools/xlsxgen/*` | `src/structiq/qaqc/xlsx/` | port | 4 | Needs openpyxl, LibreOffice recalculation. |
| `04_tools/qa/package_qa.py` | `src/structiq/qaqc/package_qa.py` | port | 4 | |
| `04_tools/doc_control/check_register.py` | `src/structiq/qaqc/doc_control.py` | port | 4 | |
| `04_tools/etabs/{etabs_import,etabs_db_import}.py` | `src/structiq/tools/etabs/` | port | 5 | Behind an interface; unverified on SAFE. |
| `04_tools/ai/{mcp_server,project_access}.py` | `src/structiq/tools/mcp/` | port | 5 | Optional extra `[mcp]`. |
| `04_tools/ai/ask_local.py` | `src/structiq/tools/mcp/ask_local.py` | port | 5 | Ollama helper, optional. |
| `04_tools/knowledge/build_knowledge_pack.py` | none | skip | - | The pack is generated for NotebookLM; rebuild is not needed in StructIQ. |
| `tests/test_*.py` (16) + fixtures | `tests/{core,calc,qaqc,tools,drawing}/` | port | 1-5 | unittest + `sys.path` converted to pytest + `structiq.*` imports. |
| `.claude/skills/{pt-floor-design,rc-design,steel-design}` | `.claude/skills/` | adapt | 4 | Read Core Brain first. |
| `.claude/skills/{structural-documentation,-drawing,-specification,-calculation-report,-document-qa}` | `.claude/skills/` | adapt | 4 | |
| `.claude/skills/{pt-drawings,pt-slab-package}` | `.claude/skills/` | adapt | 4 | Locked numeric defaults (gap G30) removed or marked ASSUMED/TBC. |
| `01_standards/00-overview.md, 01..05 *.md` | Drive `07-Drawing Templates` + `config/standards/` | adapt | 3 | Title block: StructIQ's sample-based block governs unless the user decides otherwise. |
| `01_standards/05-drafting-styles/*.csv` | `config/standards/layers/` | adapt | 3 | See `layer-mapping.md`. |
| `01_standards/06-templates/{blocks,sheets}` (DXF/DWG, 25 files) | Drive `07-Drawing Templates` | drive | 3 | Binary, company content; kept off git. |
| `01_standards/00-gap-register.md` | Drive `docs\merge\sdsa-gap-register.md` | drive | 0 | Contains client and personal names; not in the public repo. |
| `02_disciplines/pt-floor/knowledge/pt-master-ruleset.{md,yaml}` | Core Brain `02-Engineering Principles/` | brain | 6 | DRAFT, engineer reviews (gaps G33/G34). |
| `02_disciplines/pt-floor/knowledge/pt-tendon-profile-ruleset.*` | Core Brain `02-Engineering Principles/` | brain | 6 | DRAFT. |
| `02_disciplines/pt-floor/knowledge/pt-{design,detailing}-guide.md` | Core Brain `02-Engineering Principles/` | brain | 6 | Check for pasted standards text first. |
| `02_disciplines/{steel,rc-works}` | merged into skills | adapt | 4 | About one page each. |
| `AGENTS.md`, `CLAUDE.md` rules | Core Brain `03-Safety Rules` | brain | 6 | Map onto the existing 8 rules; add only what is missing (INDICATIVE / NOT EVALUATED / UNVERIFIED). |
| `05_docs/adr/*` (12) | `docs/adr/` | adapt | 6 | Mark superseded where StructIQ decided differently (storage, API, hosting). |
| `05_docs/{architecture-v2,development-plan-v2,product-roadmap-pt}.md` | Drive `docs\merge\` | drive | 6 | Planning documents. |
| `05_docs/*.png`, `05_docs/images/*` | Drive `docs\merge\images` | drive | 6 | |
| `05_docs/2FPT-original.inp`, `05_docs/INP Validator.png` | none | skip | - | Client SAFE model. |
| `05_docs/ai-access.md` | `docs/mcp.md` | adapt | 5 | Stale `D:\Structural Design...` path fixed. |
| `03_projects/PJR-2026-003, PJR-2F-PT, PJR-2026-004` | none | skip | - | Client / third-party data. |
| `03_projects/_template` | `templates/design-basis/` | port | 2 | Blank yaml only. |
| `06_knowledge-pack/*` | none | skip | - | Generated. |
| `.mcp.json`, `.vscode/*`, `setup.bat`, `pyproject.toml` | merged into StructIQ equivalents | adapt | 1 | Tool config only. |

## Counts
- port: calc core, EC2 checks, registry, design basis, validators, restandardise, docgen, xlsxgen, QA, ETABS importers, MCP, tests.
- adapt: cadgen sheets, skills, standards, ADRs.
- brain: PT rulesets, status vocabulary and rules from AGENTS.md.
- skip: three project folders, knowledge pack, SAFE `.inp`.

## Phase 4 outcome
- Ported: `docgen` -> `structiq.qaqc.docgen`; `xlsxgen` -> `structiq.qaqc.xlsx.{anchorage_workbook,verify}`; `check_register` ->
  `structiq.qaqc.doc_control`; `package_qa` -> `structiq.qaqc.package_qa` (DXF check now uses `structiq.drawing.validate`).
- Project-specific wording (drawing sheet names, an assumed fctk value) was removed from the report and workbook text.
- Tests are rewritten on made-up fixtures (`tests/qaqc/qaqc_fixtures.py`). Tests that need LibreOffice (PDF, workbook recalculation)
  are marked `requires_soffice` and were NOT run on this machine, because LibreOffice is not installed.
- The 10 skills are in `.claude/skills` with a banner that sends the reader to the Core Brain first and lists what is not ported.

## Phase 5 outcome
- Ported: ETABS/SAFE importers -> `structiq.tools.etabs.{table_import,db_import}` (40 tests on the synthetic fixtures; the test
  that read a real client `.db` was dropped). Still unverified against a real SAFE export or an export with results.
- Reworked: the MCP server and access layer -> `structiq.tools.mcp.{access,server,ask_local}`. The SDSA version served that repo's
  folders and manifest; the new one serves `repo/` and the Core Brain `brain/`, validates design bases without serving project
  files, and never serves `config/paths.yaml`. Documentation: `docs/mcp.md` (replaces SDSA `ai-access.md`).
- Not ported: `knowledge/build_knowledge_pack.py` (generated NotebookLM pack).

## Phase 6 outcome
- Core Brain 0.3.0-draft (Drive): added `05-pt-master-ruleset`, `06-pt-tendon-profile-ruleset` (md + yaml, DRAFT / UNVERIFIED), the default
  code basis in `01-codes-and-references`, and the design-basis rule and check status words in `03-assumptions-and-verification`.
  `safety-rules.md` is unchanged: SDSA rules 1-3 and 6 map onto Brain rules 1, 2, 3 and 6; the status vocabulary is now in `03-`.
- Not copied: the PT design and detailing guides (about 60 KB, may paraphrase published sources; stay in the archive).
- ADRs: `docs/adr/` with a StructIQ status note on each.
- Archive note added to the SDSA README (uncommitted there).
