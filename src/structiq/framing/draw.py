"""Draw the proposed beams on the structural layout.

RC beams as rectangles (width x length) on S-BEAM, PT bands on S-BEAM-PT (marked only), a tag
per beam on S-BEAM-TXT: Arial, 1.5 mm at A3 (the caller passes the per-plan model height).
"""

from __future__ import annotations

from ezdxf.enums import TextEntityAlignment

from structiq.drawing import template
from structiq.framing.arrange import BeamResult

TAG_MIN_LENGTH = 1500.0  # mm: shorter pieces are not tagged


def _tag(msp, text, x, y, height, rotation=0.0):
    msp.add_text(
        text,
        height=height,
        rotation=rotation,
        dxfattribs={"layer": "S-BEAM-TXT", "style": "STIQ-TEXT"},
    ).set_placement((x, y), align=TextEntityAlignment.MIDDLE_CENTER)


def add_beams(doc, result: BeamResult, text_height=None) -> None:
    template.define_styles(doc)
    msp = doc.modelspace()
    for band in result.bands:
        h = text_height(band.plan) if text_height else 150.0
        y0, y1 = band.y - band.width / 2, band.y + band.width / 2
        msp.add_lwpolyline(
            [(band.x0, y0), (band.x1, y0), (band.x1, y1), (band.x0, y1)],
            close=True,
            dxfattribs={"layer": "S-BEAM-PT"},
        )
        _tag(msp, band.mark, (band.x0 + band.x1) / 2, band.y, h)
    for b in result.beams:
        h = text_height(b.plan) if text_height else 150.0
        half = b.width / 2
        if b.orientation == "V":
            pts = [(b.centre - half, b.start), (b.centre + half, b.start),
                   (b.centre + half, b.end), (b.centre - half, b.end)]
        else:
            pts = [(b.start, b.centre - half), (b.end, b.centre - half),
                   (b.end, b.centre + half), (b.start, b.centre + half)]
        msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": "S-BEAM"})
        if b.length >= TAG_MIN_LENGTH:
            mid = (b.start + b.end) / 2
            if b.orientation == "V":
                _tag(msp, b.mark, b.centre + half + h, mid, h, rotation=90.0)
            else:
                _tag(msp, b.mark, mid, b.centre + half + h, h)
