"""Funzioni geometriche pure (mm, asse Y verso l'alto)."""
from __future__ import annotations
import math
from collections import defaultdict

Pt = tuple[float, float]


def dist(a: Pt, b: Pt) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def lerp(a: Pt, b: Pt, t: float) -> Pt:
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def length(pts: list[Pt]) -> float:
    return sum(dist(a, b) for a, b in zip(pts, pts[1:]))


def bbox(pts: list[Pt]) -> tuple[float, float, float, float]:
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def is_closed(pts: list[Pt], tol: float = 1e-3) -> bool:
    return len(pts) > 2 and dist(pts[0], pts[-1]) <= tol


def cubic(p0: Pt, p1: Pt, p2: Pt, p3: Pt, tol: float) -> list[Pt]:
    """Linearizza una Bézier cubica con errore massimo ~tol."""
    m = max(math.hypot(p0[0] - 2 * p1[0] + p2[0], p0[1] - 2 * p1[1] + p2[1]),
            math.hypot(p1[0] - 2 * p2[0] + p3[0], p1[1] - 2 * p2[1] + p3[1]))
    n = max(1, min(256, math.ceil(math.sqrt(0.75 * m / max(tol, 1e-6)))))
    out = []
    for i in range(n + 1):
        t = i / n; u = 1 - t
        a, b, c, d = u**3, 3 * u * u * t, 3 * u * t * t, t**3
        out.append((a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0],
                    a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1]))
    return out


def flatten(segments: list, tol: float) -> list[Pt]:
    pts: list[Pt] = []
    for s in segments:
        seq = [s[1], s[2]] if s[0] == "l" else cubic(s[1], s[2], s[3], s[4], tol)
        if pts and dist(pts[-1], seq[0]) < 1e-6:
            pts.extend(seq[1:])
        else:
            pts.extend(seq)
    return pts


def rdp(pts: list[Pt], eps: float) -> list[Pt]:
    """Ramer-Douglas-Peucker iterativo (= Tracciato > Semplifica)."""
    if len(pts) < 3 or eps <= 0:
        return list(pts)
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        i, j = stack.pop()
        a, b = pts[i], pts[j]
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy)
        dmax, idx = -1.0, -1
        for k in range(i + 1, j):
            p = pts[k]
            d = (abs(dy * p[0] - dx * p[1] + b[0] * a[1] - b[1] * a[0]) / L) if L > 1e-12 else dist(p, a)
            if d > dmax:
                dmax, idx = d, k
        if dmax > eps:
            keep[idx] = True
            stack += [(i, idx), (idx, j)]
    out = [p for p, k in zip(pts, keep) if k]
    # un chiuso ridotto a 2-3 punti degenera: mantieni l'originale
    if is_closed(pts) and len(out) < 4:
        return list(pts)
    return out


def explode_dashes(pts: list[Pt], pattern: list[float], phase: float = 0.0,
                   min_len: float = 0.05) -> list[list[Pt]]:
    """Trasforma un tracciato con stile tratteggiato in segmenti aperti reali."""
    pat = [max(0.0, p) for p in pattern]
    if len(pat) % 2:
        pat *= 2
    if not pat or sum(pat) <= 1e-6 or len(pts) < 2:
        return [pts]
    n = len(pat)
    idx, rem = 0, pat[0]
    phase %= sum(pat)
    while phase > 1e-9:
        if phase >= rem:
            phase -= rem; idx = (idx + 1) % n; rem = pat[idx]
        else:
            rem -= phase; phase = 0
    on = idx % 2 == 0
    out: list[list[Pt]] = []
    cur = [pts[0]] if on else None
    for a, b in zip(pts, pts[1:]):
        seg = dist(a, b)
        if seg < 1e-12:
            continue
        t = 0.0
        while seg - t > 1e-9:
            step = min(rem, seg - t)
            t += step; rem -= step
            p = lerp(a, b, t / seg)
            if on and cur is not None:
                cur.append(p)
            if rem <= 1e-9:
                if on and cur and length(cur) >= min_len:
                    out.append(cur)
                idx = (idx + 1) % n; rem = pat[idx]; on = idx % 2 == 0
                cur = [p] if on else None
    if on and cur and len(cur) >= 2 and length(cur) >= min_len:
        out.append(cur)
    return out


def join_polylines(polys: list[list[Pt]], tol: float) -> list[list[Pt]]:
    """Unisce frammenti con estremi coincidenti (entro tol) in tracciati continui."""
    polys = [p for p in polys if len(p) >= 2]
    if tol <= 0:
        return polys
    used = [False] * len(polys)
    cell = tol * 2
    grid: dict = defaultdict(list)
    key = lambda p: (int(p[0] // cell), int(p[1] // cell))
    for i, p in enumerate(polys):
        if not is_closed(p, tol):
            grid[key(p[0])].append((i, 0)); grid[key(p[-1])].append((i, 1))

    def find(pt):
        kx, ky = key(pt)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for i, e in grid.get((kx + dx, ky + dy), ()):
                    if not used[i]:
                        q = polys[i][0] if e == 0 else polys[i][-1]
                        if dist(pt, q) <= tol:
                            return i, e
        return None

    out = []
    for i, p in enumerate(polys):
        if used[i]:
            continue
        used[i] = True
        chain = list(p)
        for _ in range(2):
            while not is_closed(chain, tol):
                r = find(chain[-1])
                if not r:
                    break
                j, e = r; used[j] = True
                seg = polys[j] if e == 0 else polys[j][::-1]
                chain.extend(seg[1:])
            chain.reverse()
        if is_closed(chain, tol):
            chain[-1] = chain[0]
        out.append(chain)
    return out


def area(pts: list[Pt]) -> float:
    return abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(pts, pts[1:] + pts[:1]))) / 2


def point_in_polygon(p: Pt, poly: list[Pt]) -> bool:
    x, y = p; inside = False
    for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside
