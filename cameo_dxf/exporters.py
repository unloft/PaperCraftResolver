"""Export DXF R14 (stile 'Desktop Cutting Plotter' di Inkscape) e SVG di controllo.

Equivalenza con le opzioni Inkscape del manuale:
  - Unità mm ($INSUNITS=4)          - LWPOLYLINE abilitato (unica entità scritta)
  - Spline ROBO-Master disabilitate  - Appiattisci Bézier disabilitato (nessuna SPLINE)
Layer TAGLIO = rosso (ACI 1)  ->  Silhouette: lama
Layer PIEGHE = blu   (ACI 5)  ->  Silhouette: penna (Schizzo, Vel. 10, Forza 1)
"""
from __future__ import annotations

from .geometry import is_closed
from .processing import Result

LAYERS = (("TAGLIO", 1, "cut"), ("PIEGHE", 5, "fold"))


class _Dxf:
    def __init__(self):
        self.lines: list[str] = []
        self.h = 0x20

    def g(self, code, value):
        self.lines += [f"{code:>3}", str(value)]

    def handle(self):
        self.h += 1
        self.g(5, f"{self.h:X}")


def _f(v: float) -> str:
    return f"{v:.4f}"


def write_dxf_r14(res: Result, path: str) -> None:
    d = _Dxf()
    W, H = res.size
    d.g(0, "SECTION"); d.g(2, "HEADER")
    for name, code, val in (("$ACADVER", 1, "AC1014"), ("$INSUNITS", 70, 4), ("$MEASUREMENT", 70, 1)):
        d.g(9, name); d.g(code, val)
    d.g(9, "$EXTMIN"); d.g(10, _f(0)); d.g(20, _f(0)); d.g(30, _f(0))
    d.g(9, "$EXTMAX"); d.g(10, _f(W)); d.g(20, _f(H)); d.g(30, _f(0))
    d.g(9, "$HANDSEED"); d.g(5, "FFFFF")
    d.g(0, "ENDSEC")
    # TABLES
    d.g(0, "SECTION"); d.g(2, "TABLES")
    d.g(0, "TABLE"); d.g(2, "LTYPE"); d.handle(); d.g(100, "AcDbSymbolTable"); d.g(70, 1)
    d.g(0, "LTYPE"); d.handle(); d.g(100, "AcDbSymbolTableRecord"); d.g(100, "AcDbLinetypeTableRecord")
    d.g(2, "CONTINUOUS"); d.g(70, 0); d.g(3, "Solid line"); d.g(72, 65); d.g(73, 0); d.g(40, "0.0")
    d.g(0, "ENDTAB")
    d.g(0, "TABLE"); d.g(2, "LAYER"); d.handle(); d.g(100, "AcDbSymbolTable"); d.g(70, 3)
    for name, color in (("0", 7),) + tuple((n, c) for n, c, _ in LAYERS):
        d.g(0, "LAYER"); d.handle(); d.g(100, "AcDbSymbolTableRecord"); d.g(100, "AcDbLayerTableRecord")
        d.g(2, name); d.g(70, 0); d.g(62, color); d.g(6, "CONTINUOUS")
    d.g(0, "ENDTAB")
    d.g(0, "ENDSEC")
    # ENTITIES
    d.g(0, "SECTION"); d.g(2, "ENTITIES")
    for layer, color, attr in LAYERS:
        for poly in getattr(res, attr):
            closed = attr == "cut" and is_closed(poly)   # le pieghe restano SEMPRE aperte
            pts = poly[:-1] if closed else poly
            d.g(0, "LWPOLYLINE"); d.handle(); d.g(100, "AcDbEntity"); d.g(8, layer); d.g(62, color)
            d.g(100, "AcDbPolyline"); d.g(90, len(pts)); d.g(70, 1 if closed else 0)
            for x, y in pts:
                d.g(10, _f(x)); d.g(20, _f(y))
    d.g(0, "ENDSEC"); d.g(0, "EOF")
    with open(path, "w", encoding="ascii", newline="\r\n") as fh:
        fh.write("\n".join(d.lines) + "\n")


def write_dxf_r2000(res: Result, path: str) -> None:
    """Alternativa via ezdxf (AC1015) se qualche software rifiuta l'R14."""
    import ezdxf
    doc = ezdxf.new("R2000")
    doc.units = 4
    msp = doc.modelspace()
    for layer, color, attr in LAYERS:
        doc.layers.add(layer, color=color)
        for poly in getattr(res, attr):
            closed = attr == "cut" and is_closed(poly)
            msp.add_lwpolyline(poly[:-1] if closed else poly, close=closed,
                               dxfattribs={"layer": layer, "color": color})
    doc.saveas(path)


def write_svg(res: Result, path: str) -> None:
    """SVG di controllo (apribile in Inkscape), in mm."""
    W, H = res.size
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W:.2f}mm" height="{H:.2f}mm" '
           f'viewBox="0 0 {W:.3f} {H:.3f}">']
    for layer, _, attr in LAYERS:
        col = "#ff0000" if attr == "cut" else "#0000ff"
        out.append(f'<g id="{layer}" fill="none" stroke="{col}" stroke-width="0.2">')
        for poly in getattr(res, attr):
            pts = " ".join(f"{x:.3f},{H - y:.3f}" for x, y in poly)
            out.append(f'<polyline points="{pts}"/>')
        out.append("</g>")
    out.append("</svg>")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out))
