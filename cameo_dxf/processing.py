"""Pulizia, classificazione taglio/piega, semplificazione e adattamento."""
from __future__ import annotations
from collections import Counter
from dataclasses import dataclass, field

from . import geometry as g
from .pdf_reader import PageData, Style

CUT, FOLD, SKIP = "Taglio", "Piega", "Scarta"
ROLES = (CUT, FOLD, SKIP)


@dataclass
class Settings:
    flatten_tol_mm: float = 0.05     # precisione linearizzazione curve
    simplify_mm: float = 0.05        # tolleranza "Semplifica" (0 = off)
    join_tol_mm: float = 0.10        # unione frammenti del contorno
    min_length_mm: float = 0.5       # elimina frammenti minuscoli
    margin_mm: float = 5.0           # margine dopo adattamento
    explode_dashes: bool = True      # tratteggio -> segmenti aperti reali
    remove_artifacts: bool = True    # bordi pagina, linee lunghissime, degeneri
    long_line_ratio: float = 0.90    # soglia "linea lunghissima" (frazione pagina)
    remove_duplicates: bool = True   # evita i doppi contorni
    join_cut: bool = True
    outer_only: bool = False         # tieni solo il contorno più esterno


@dataclass
class Result:
    cut: list = field(default_factory=list)
    fold: list = field(default_factory=list)
    offset: tuple = (0.0, 0.0)       # traslazione applicata (adattamento pagina)
    size: tuple = (0.0, 0.0)         # area di disegno finale in mm
    nodes_before: int = 0
    nodes_after: int = 0           # nodi dopo Semplifica (prima di spezzare i tratteggi)
    removed: Counter = field(default_factory=Counter)


def auto_role(st: Style) -> str:
    if st.stroke is None or st.stroke_opacity <= 0.01:
        return SKIP                                   # riempimenti: colori, testi vettoriali
    if all(c > 0.95 for c in st.stroke[:3]):
        return SKIP                                   # linee bianche/invisibili
    return FOLD if st.dashed else CUT


def auto_roles(page: PageData) -> dict[str, str]:
    return {k: auto_role(st) for k, (st, _) in page.styles().items()}


def _artifact(pts, page: PageData, s: Settings) -> str | None:
    x0, y0, x1, y1 = g.bbox(pts)
    w, h = x1 - x0, y1 - y0
    W, H = page.width_mm, page.height_mm
    r = s.long_line_ratio
    if w < 0.01 and h < 0.01:
        return "degeneri"
    if w >= r * W and h >= r * H:
        return "bordi pagina"
    if len(g.rdp(pts, 0.2)) == 2 and (g.length(pts) >= r * H or g.length(pts) >= r * W):
        return "linee lunghissime"
    return None


def _sig(pts):
    a = tuple((round(x, 2), round(y, 2)) for x, y in pts)
    return min(a, a[::-1])


def _outer_only(cut, removed):
    closed = sorted([p for p in cut if g.is_closed(p)], key=g.area, reverse=True)
    opened = [p for p in cut if not g.is_closed(p)]
    keep = []
    for p in closed:
        if any(g.point_in_polygon(p[len(p) // 2], q) for q in keep):
            removed["contorni interni"] += 1
        else:
            keep.append(p)
    for p in opened:
        if any(g.point_in_polygon(p[len(p) // 2], q) for q in keep):
            removed["contorni interni"] += 1
        else:
            keep.append(p)
    return keep


def process(page: PageData, roles: dict[str, str], s: Settings) -> Result:
    res = Result()
    res.removed["testi (ignorati)"] = page.n_text
    res.removed["immagini (ignorate)"] = page.n_images
    seen = set()
    for vp in page.paths:
        role = roles.get(vp.style.key, SKIP)
        if role == SKIP:
            res.removed["tracciati stile scartato"] += len(vp.subpaths)
            continue
        for sp in vp.subpaths:
            pts = g.flatten(sp.segments, s.flatten_tol_mm)
            if len(pts) < 2:
                continue
            if sp.closed and g.dist(pts[0], pts[-1]) > 1e-6:
                pts.append(pts[0])
            if s.remove_artifacts:
                why = _artifact(pts, page, s)
                if why:
                    res.removed[why] += 1
                    continue
            if g.length(pts) < s.min_length_mm:
                res.removed["frammenti"] += 1
                continue
            if s.remove_duplicates:
                sig = _sig(pts)
                if sig in seen:
                    res.removed["duplicati"] += 1
                    continue
                seen.add(sig)
            res.nodes_before += len(pts)
            pts = g.rdp(pts, s.simplify_mm)
            res.nodes_after += len(pts)
            if role == CUT:
                res.cut.append(pts)
            elif vp.style.dashed and s.explode_dashes:
                res.fold.extend(g.explode_dashes(pts, list(vp.style.dashes), vp.style.dash_phase))
            else:
                res.fold.append(pts)
    if s.join_cut:
        res.cut = g.join_polylines(res.cut, s.join_tol_mm)
    if s.outer_only:
        res.cut = _outer_only(res.cut, res.removed)
    _fit(res, s.margin_mm)
    res.removed = Counter({k: v for k, v in res.removed.items() if v})
    return res


def _fit(res: Result, margin: float) -> None:
    """Adatta l'area di disegno al contenuto (Ridimensiona pagina al disegno)."""
    allp = [p for poly in res.cut + res.fold for p in poly]
    if not allp:
        return
    x0, y0, x1, y1 = g.bbox(allp)
    dx, dy = margin - x0, margin - y0
    mv = lambda polys: [[(x + dx, y + dy) for x, y in p] for p in polys]
    res.cut, res.fold = mv(res.cut), mv(res.fold)
    res.offset = (dx, dy)
    res.size = (x1 - x0 + 2 * margin, y1 - y0 + 2 * margin)
