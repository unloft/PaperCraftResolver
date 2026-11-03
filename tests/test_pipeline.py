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
