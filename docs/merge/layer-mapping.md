# Layer mapping: SDSA company standard vs StructIQ (Phase 0)

## Decisions (user, 2026-11-15: "Use my suggestions")

1. `S-GRID`: StructIQ's teal dash-dot, 0.13 mm stays (copied from the sample set). SDSA's red Centre / 0.25 is an alias in restandardise.
2. Concrete outlines stay split (`S-COLS`, `S-WALL`, `S-SLAB-EDGE`); `S-CONC-OUTLINE` is kept only for imported / restandardised sheets.
3. `S-ANNO-SECT` stays; `S-SECT-CUT` maps to it in restandardise.
4. `S-TTLB-*` stays; `S-TBLK-*` maps to it in restandardise.
5. Lineweights follow the sample set (0.09-0.35 mm).
6. Text stays Arial 1.5 mm at A3 (sample set); SDSA's 2.0 mm minimum is not applied to StructIQ sheets.
7. Layers that only SDSA has (leader, steel, rebar, soil, hidden, ISO view, ...) are added to StructIQ as written in the SDSA CSVs;
   `S-PT-TENDON` and `S-CONC-DROP` stay PROPOSED (not approved).

These are the user's choices, not an engineering review.

SDSA `05-04` has 10 layers; approved extensions 05-04a and 05-04b; 05-04c is proposed only (gap G23).
StructIQ draws on the layers listed in `structiq.drawing.template.LAYERS`.

**Gate:** rows marked DECIDE need the user's choice before Phase 3 touches layers.

| SDSA layer | Colour / lw | StructIQ layer | Result |
|---|---|---|---|
| `S-ANNO-TEXT` | 7, 0.18 | `S-ANNO-TEXT` | Same name. Keep. |
| `S-ANNO-DIMS` | 7, 0.18 | `S-ANNO-DIMS` | Same name. Keep. |
| `S-ANNO-LEADER` | 7, 0.18 | none | Add to StructIQ. |
| `S-GRID` | 1 (red), Centre, 0.25 | `S-GRID` teal, `STIQ-GRID` dash-dot, 0.13 | **DECIDE**: colour, linetype and weight differ. StructIQ copies the structural sample drawing. |
| `S-STEEL-OUTLINE` | 7, 0.50 | none | Add (steel not drawn yet). |
| `S-CONC-OUTLINE` | 7, 0.50 | `S-COLS`, `S-WALL`, `S-SLAB-EDGE` (0.25-0.35) | **DECIDE**: StructIQ splits concrete outlines by element. Option: keep the split and treat `S-CONC-OUTLINE` as the generic one for imported or restandardised sheets. |
| `S-HATCH-CONC` | 8, 0.18 | `S-HATCH-CONC` grey | Same name. Keep. |
| `S-HATCH-STEEL` | 7, 0.18 | none | Add. |
| `S-SECT-CUT` | 1, Phantom, 0.35 | `S-ANNO-SECT` dark red, `STIQ-SECTION` | **DECIDE**: same purpose, different name. Suggest `S-ANNO-SECT` stays and `S-SECT-CUT` becomes an alias in restandardise. |
| `Defpoints` | non-plot | `Defpoints` (AutoCAD) | Keep. |
| `S-TBLK-BORDER` (05-04a) | 7, 0.50 | `S-TTLB-FRAME` | **DECIDE**: `TBLK` vs `TTLB`. Suggest keep StructIQ names; alias in restandardise. |
| `S-TBLK-LINE` | 7, 0.25 | `S-TTLB-LINE` | As above. |
| `S-TBLK-TEXT` | 7, 0.18 | `S-TTLB-TEXT` | As above. |
| `S-ANNO-TABLE` | 7, 0.18 | `S-ANNO-TABLE` | Same name. Keep. |
| `S-VIEW-ISO` | 7, 0.25 | none | Add (cover-sheet isometric). |
| `S-REBAR` (05-04b) | 1, 0.35 | none | Add. |
| `S-STEEL-BRACE` | 6, 0.35 | none | Add. |
| `S-MASONRY` | 30, 0.25 | none (brick walls are not drawn) | Add for restandardise only. |
| `S-SOIL` | 8, 0.18 | none | Add. |
| `S-DETAIL-THIN` | 8, 0.18 | none | Add. |
| `S-HIDDEN` | 8, Dashed, 0.18 | none | Add. |
| `S-PT-TENDON` (05-04c, NOT approved) | 3, 0.25 | none | Add as PROPOSED only. |
| `S-CONC-DROP` (05-04c, NOT approved) | 4, 0.25 | none | Add as PROPOSED only. |

StructIQ layers with no SDSA equivalent (kept): `S-GRID-TXT`, `S-GRID-BUBBLE`, `S-COLS*`, `S-WALL*`, `S-OPEN*`, `S-SLAB-*`,
`S-BEAM*`, `S-STAIR*`, `S-ANNO-NOTE`, `S-ANNO-LEVEL`, `S-ANNO-TAG`, `S-ANNO-SECT-MARK`, `S-ANNO-VIEWTITLE`, `S-VPORT`.
Member layers (beam, column, wall, slab) are an open gap in SDSA (G03): StructIQ's layers can be proposed to fill it.

## Other differences to resolve with the user
- **Lineweight scale:** SDSA 0.18-0.50 mm; StructIQ 0.09-0.35 mm taken from the sample sheet. The sample set decides unless told otherwise.
- **Title block:** SDSA gap G22 says its "Office Title Block" governs; StructIQ's block is measured from the sample structural set
  (`PJR-2026-002`). Both fill project, drawing name, scale, revision, date. They may differ in geometry.
- **Revision scheme:** SDSA `R00` / `P01`; StructIQ `Rev NN` in the file name and `R00` in the title block. SDSA gap G08 is still open.
- **Text:** both use Arial at 1.5-2.0 mm; SDSA calls 2.0 mm the minimum (05-01), StructIQ uses 1.5 mm from the sample. Needs a decision.
