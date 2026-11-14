import pymupdf
import pytest

from structiq.framing import learn

PT = 72 / 25.4  # points per mm
TEAL = (64 / 255, 128 / 255, 128 / 255)
BROWN = (128 / 255, 64 / 255, 0)


def _line(page, x0, y0, x1, y1, colour):
    page.draw_line((x0 * PT, y0 * PT), (x1 * PT, y1 * PT), color=colour, width=0.2)


def _text(page, x, y, text, size=6):
    page.insert_text((x * PT, y * PT), text, fontsize=size)


@pytest.fixture()
def sheet(tmp_path):
    """A 1:100 plan: gridlines A/B/C (x 50, 90, 160) and 01..04 (y 240, 189, 112, 35)."""
    doc = pymupdf.open()
    page = doc.new_page(width=420 * PT, height=297 * PT)
    for x in (50, 90, 160):
        _line(page, x, 30, x, 245, TEAL)
    for y in (240, 189, 112, 35):
        _line(page, 35, y, 190, y, TEAL)
    for x, label in ((50, "A"), (90, "B"), (160, "C")):
        _text(page, x - 1, 32, label)
    for y, label in ((240, "01"), (189, "02"), (112, "03"), (35, "04")):
        _text(page, 15, y + 1, label)
    # a 300 mm beam centred on x = 120 (faces 118.5 / 121.5), from y 60 to 200, tagged RCB3
    _line(page, 118.5, 60, 118.5, 200, BROWN)
    _line(page, 121.5, 60, 121.5, 200, BROWN)
    _text(page, 114, 130, "RCB3")
    # two unrelated brown lines 20 mm apart, no tag: not a beam
    _line(page, 140, 60, 140, 200, BROWN)
    _line(page, 160, 60, 160, 200, BROWN)
    # a tagged band whose width (2000) does not match the schedule size (300): not a beam
    _line(page, 70, 60, 70, 200, BROWN)
    _line(page, 90, 60, 90, 200, BROWN)
    _text(page, 66, 100, "RCB3")
    # schedule row under the plan
    _text(page, 300, 270, "1F RCB3 RCB3-(300x500)mm C30/37")
    path = tmp_path / "s.pdf"
    doc.save(path)
    return learn.read_sheet(pymupdf.open(path), 1)


def test_grid_is_calibrated_from_the_known_bay_widths(sheet):
    assert sheet.scale == pytest.approx(100, abs=1)
    assert sheet.grid_x == {"A": 0, "B": 4000, "C": 11000}
    assert sheet.grid_y["01"] == 0 and sheet.grid_y["02"] == pytest.approx(5100, abs=50)


def test_schedule_row_is_read(sheet):
    assert sheet.schedule["RCB3"] == {"w": 300, "d": 500, "fck": "C30/37", "level": "1F"}


def test_only_the_tagged_beam_with_the_scheduled_width_is_kept(sheet):
    (beam,) = sheet.beams
    assert (beam.mark, beam.orientation, beam.size) == ("RCB3", "V", "300x500")
    assert beam.centre == pytest.approx(7000, abs=50)  # x 120 - 50 = 70 mm = 7000 mm from A
    assert beam.width == 300
    assert beam.start == pytest.approx(4000, abs=50) and beam.end == pytest.approx(18000, abs=50)


def test_sheet_without_a_grid_is_skipped_with_a_warning(tmp_path):
    doc = pymupdf.open()
    doc.new_page(width=420 * PT, height=297 * PT)
    path = tmp_path / "blank.pdf"
    doc.save(path)
    s = learn.read_sheet(pymupdf.open(path), 1)
    assert s.scale is None and "skipped" in s.warnings[0]
