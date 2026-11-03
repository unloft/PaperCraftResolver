import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.dirname(__file__))

from cameo_dxf.exporters import write_dxf_r14
from cameo_dxf.geometry import is_closed
from cameo_dxf.pdf_reader import read_page
from cameo_dxf.processing import Settings, auto_roles, process
from sample_pdf import make_pdf


def test_pipeline(tmp_path):
    pdf = tmp_path / "t.pdf"; make_pdf(str(pdf))
    page = read_page(str(pdf), 0)
    res = process(page, auto_roles(page), Settings())
    assert len(res.cut) == 3                       # stella, cerchio, quadrato riunito
    assert all(is_closed(p) for p in res.cut)
    assert len(res.fold) > 20                      # tratteggi spezzati
    assert all(not is_closed(p) for p in res.fold)
    for k in ("bordi pagina", "linee lunghissime", "duplicati"):
        assert res.removed[k] == 1
    out = tmp_path / "o.dxf"; write_dxf_r14(res, str(out))
    txt = out.read_text()
    assert "AC1014" in txt and "SPLINE" not in txt and "LWPOLYLINE" in txt
    try:
        import ezdxf
        doc = ezdxf.readfile(str(out))
        assert {e.dxf.layer for e in doc.modelspace()} == {"TAGLIO", "PIEGHE"}
    except ImportError:
        pass


def test_outer_only(tmp_path):
    pdf = tmp_path / "t.pdf"; make_pdf(str(pdf))
    page = read_page(str(pdf), 0)
    res = process(page, auto_roles(page), Settings(outer_only=True))
    assert len(res.cut) == 2                       # il cerchio interno sparisce


def test_drawn_dashes_and_nesting(tmp_path):
    """Pieghe disegnate come segmentini (come nei PDF reali) + nesting su A4."""
    import pymupdf
    from cameo_dxf.nesting import NestSettings, build_pieces, nest
    doc = pymupdf.open(); p = doc.new_page()
    for k in range(3):                                   # 3 pezzi quadrati 60x60 mm circa
        x0 = 60 + k * 180
        p.draw_rect(pymupdf.Rect(x0, 100, x0 + 170, 270), color=(0, 0, 0), width=1.4)
        x = x0 + 5
        while x < x0 + 165:                              # diagonale "tratteggiata a mano"
            p.draw_line((x, 185), (x + 4, 185), color=(0, 0, 0), width=1.4); x += 8
    pdf = tmp_path / "d.pdf"; doc.save(str(pdf))
    page = read_page(str(pdf), 0)
    res = process(page, auto_roles(page), Settings())
    assert len(res.cut) == 3 and len(res.fold) > 40
    ns = NestSettings()
    pieces, _ = build_pieces(res, ns)
    assert len(pieces) == 3
    sheets, warns = nest(pieces, ns)
    assert len(sheets) == 1 and not warns
    for poly in sheets[0].cut + sheets[0].fold:
        for x, y in poly:
            assert ns.margin_mm - 1 <= x <= ns.sheet_w - ns.margin_mm + 1
            assert ns.margin_mm - 1 <= y <= ns.sheet_h - ns.margin_mm + 1
