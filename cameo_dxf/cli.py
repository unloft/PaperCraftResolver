"""Uso da riga di comando: python -m cameo_dxf input.pdf -p 1 -o out.dxf"""
from __future__ import annotations
import argparse
import os

from .exporters import write_dxf_r14, write_dxf_r2000, write_svg
from .pdf_reader import read_page
from .processing import Settings, auto_roles, process


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="PDF papercraft -> DXF R14 per Silhouette Cameo 5")
    ap.add_argument("pdf")
    ap.add_argument("-p", "--page", type=int, default=1, help="pagina (da 1)")
    ap.add_argument("-o", "--out", help="file DXF di uscita")
    ap.add_argument("--r2000", action="store_true", help="usa ezdxf/R2000 invece di R14")
    ap.add_argument("--svg", action="store_true", help="salva anche SVG di controllo")
    ap.add_argument("--simplify", type=float, default=0.05)
    ap.add_argument("--outer-only", action="store_true")
    ap.add_argument("--no-explode", action="store_true", help="non spezzare i tratteggi")
    a = ap.parse_args(argv)

    page = read_page(a.pdf, a.page - 1)
    roles = auto_roles(page)
    s = Settings(simplify_mm=a.simplify, outer_only=a.outer_only, explode_dashes=not a.no_explode)
    res = process(page, roles, s)
    out = a.out or os.path.splitext(a.pdf)[0] + f"_p{a.page}.dxf"
    (write_dxf_r2000 if a.r2000 else write_dxf_r14)(res, out)
    if a.svg:
        write_svg(res, os.path.splitext(out)[0] + ".svg")
    print("Stili:")
    for k, r in roles.items():
        print(f"  {r:7} {k}")
    print(f"Taglio: {len(res.cut)}  Pieghe: {len(res.fold)}  "
          f"Nodi: {res.nodes_before} -> {res.nodes_after}  "
          f"Area: {res.size[0]:.1f} x {res.size[1]:.1f} mm")
    print("Rimossi:", dict(res.removed))
    print("Salvato:", out)
    return 0
