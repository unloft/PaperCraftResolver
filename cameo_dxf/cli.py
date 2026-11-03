"""Riga di comando.

  python -m cameo_dxf modello.pdf -p 4 -o pezzo.dxf
  python -m cameo_dxf modello.pdf -p 4-7 --nest            # un set di fogli A4 per pagina
  python -m cameo_dxf modello.pdf -p 4-7 --nest --merge    # tutte le pagine sugli stessi fogli
"""
from __future__ import annotations
import argparse
import os

from .exporters import write_dxf_r14, write_dxf_r2000, write_svg
from .nesting import NestSettings, build_pieces, nest, usage
from .pdf_reader import page_count, read_page
from .processing import Settings, auto_roles, process

SHEETS = {"A4": (210, 297), "A3": (297, 420), "LETTER": (215.9, 279.4), "MAT12": (304.8, 304.8)}


def parse_pages(spec: str, n: int) -> list[int]:
    """'1,3,5-7' -> [0,2,4,5,6] (0-based)."""
    out = []
    for part in str(spec).replace(" ", "").split(","):
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-")
            out += range(int(a or 1), int(b or n) + 1)
        else:
            out.append(int(part))
    return [p - 1 for p in dict.fromkeys(out) if 1 <= p <= n]


def parse_sheet(s: str) -> tuple[float, float]:
    s = s.upper()
    if s in SHEETS:
        return SHEETS[s]
    w, h = s.lower().split("x")
    return float(w), float(h)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="PDF papercraft -> DXF R14 per Silhouette Cameo 5")
    ap.add_argument("pdf")
    ap.add_argument("-p", "--pages", default="1", help="pagine, es. 4 oppure 4-7 oppure 1,3")
    ap.add_argument("-o", "--out", help="file DXF di uscita (base del nome)")
    ap.add_argument("--r2000", action="store_true", help="usa ezdxf/R2000 invece di R14")
    ap.add_argument("--svg", action="store_true", help="salva anche SVG di controllo")
    ap.add_argument("--simplify", type=float, default=0.05)
    ap.add_argument("--outer-only", action="store_true")
    ap.add_argument("--no-explode", action="store_true", help="non spezzare i tratteggi")
    ap.add_argument("--nest", action="store_true", help="disponi i pezzi su fogli (default A4)")
    ap.add_argument("--merge", action="store_true", help="con --nest: unisci le pagine sugli stessi fogli")
    ap.add_argument("--sheet", default="A4", help="A4, A3, LETTER, MAT12 o LxH in mm (es. 210x297)")
    ap.add_argument("--margin", type=float, default=5.0)
    ap.add_argument("--gap", type=float, default=2.0)
    a = ap.parse_args(argv)

    pages = parse_pages(a.pages, page_count(a.pdf))
    if not pages:
        ap.error("nessuna pagina valida")
    s = Settings(simplify_mm=a.simplify, outer_only=a.outer_only, explode_dashes=not a.no_explode)
    w, h = parse_sheet(a.sheet)
    ns = NestSettings(sheet_w=w, sheet_h=h, margin_mm=a.margin, gap_mm=a.gap)
    base = os.path.splitext(a.out or a.pdf)[0]
    writer = write_dxf_r2000 if a.r2000 else write_dxf_r14

    def save(res, path):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        writer(res, path)
        if a.svg:
            write_svg(res, os.path.splitext(path)[0] + ".svg")
        print(f"  -> {path}  (taglio {len(res.cut)}, pieghe {len(res.fold)})")

    results = []
    for pi in pages:
        page = read_page(a.pdf, pi)
        res = process(page, auto_roles(page), s)
        print(f"Pagina {pi + 1}: taglio {len(res.cut)}, pieghe {len(res.fold)}, "
              f"nodi {res.nodes_before}->{res.nodes_after}, eliminati {dict(res.removed)}")
        results.append((pi, res))

    if not a.nest:
        for pi, res in results:
            save(res, base + (f"_p{pi + 1}" if len(results) > 1 or not a.out else "") + ".dxf")
        return 0

    groups = [("tutte", results)] if a.merge else [(f"p{pi + 1}", [(pi, r)]) for pi, r in results]
    for name, grp in groups:
        pieces = []
        for _, res in grp:
            pcs, rep = build_pieces(res, ns)
            pieces += pcs
        sheets, warns = nest(pieces, ns)
        print(f"Nesting {name}: {len(pieces)} pezzi su {len(sheets)} fogli {w:g}x{h:g} mm "
              f"(occupazione {usage(sheets, pieces, ns):.0f}%)")
        for wmsg in warns:
            print("  !", wmsg)
        for k, sh in enumerate(sheets, 1):
            save(sh, f"{base}_{name}_foglio{k}.dxf")
    return 0
