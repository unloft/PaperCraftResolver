"""Numeri ed etichette del PDF ridisegnati con font a tratto singolo (Hershey),
ideale per la penna: una sola passata, niente contorni doppi delle lettere."""
from __future__ import annotations
import math
from functools import lru_cache

from . import geometry as g

CAP_RATIO = 0.72          # altezza maiuscole / corpo del font


@lru_cache(maxsize=1)
def _font():
    from HersheyFonts import HersheyFonts
    f = HersheyFonts()
    f.load_default_font("futural")
    f.normalize_rendering(10)        # maiuscole alte 7.5 unità (y 2.5..10)
    return f


@lru_cache(maxsize=512)
def _glyphs(text: str):
    segs = [tuple(map(tuple, s)) for s in _font().lines_for_text(text)]
    polys = g.join_polylines([list(s) for s in segs], 1e-6)
    if not polys:
        return [], (0, 0, 0, 0)
    return polys, g.bbox([p for poly in polys for p in poly])


def render(text: str, center, angle_deg: float, size_mm: float, scale: float = 1.0) -> list:
    """Polilinee (mm) del testo centrato in `center`, ruotato di `angle_deg`."""
    polys, (x0, y0, x1, y1) = _glyphs(text)
    if not polys:
        return []
    k = size_mm * CAP_RATIO * scale / 7.5
    cx, cy = (x0 + x1) / 2, 2.5 + 7.5 / 2          # centro su larghezza e altezza maiuscole
    t = math.radians(angle_deg); c, s = math.cos(t), math.sin(t)
    out = []
    for p in polys:
        q = []
        for x, y in p:
            lx, ly = (x - cx) * k, (y - cy) * k
            q.append((center[0] + lx * c - ly * s, center[1] + lx * s + ly * c))
        out.append(q)
    return out


def available() -> bool:
    try:
        _font()
        return True
    except Exception:  # noqa: BLE001
        return False
