"""Riconoscimento dei pezzi e nesting su fogli (A4) con rotazioni, sulla forma reale.

1. Tutti i contorni di taglio vengono rasterizzati e "riempiti" dall'esterno:
   ogni zona chiusa = un pezzo (anche se il contorno è fatto di più tratti).
2. Ogni linea (taglio o piega) viene assegnata al pezzo che la contiene.
3. Nesting su griglia: per ogni pezzo si provano più rotazioni e si sceglie la
   posizione libera più in alto a sinistra (come l'origine del tappetino Silhouette); collisioni calcolate
   con correlazione FFT (numpy). Niente specchiature: le pieghe monte/valle restano corrette.
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field

import numpy as np
from PIL import Image, ImageDraw

from . import geometry as g
from .processing import Result

OUT = -1


@dataclass
class Piece:
    cut: list
    fold: list
    area_mm2: float = 0.0


@dataclass
class NestSettings:
    sheet_w: float = 210.0      # A4 verticale
    sheet_h: float = 297.0
    margin_mm: float = 5.0      # bordo foglio non usato
    gap_mm: float = 2.0         # distanza minima fra pezzi
    step_deg: float = 15.0      # passo rotazioni provate
    res_mm: float = 1.0         # risoluzione griglia nesting
    tries: int = 3              # ordinamenti provati (tiene il migliore)


def _raster(polys, res, stroke, origin, size, mode="L"):
    img = Image.new(mode, size, 0)
    dr = ImageDraw.Draw(img)
    wpx = max(1, int(round(stroke / res)))
    ox, oy = origin
    for p in polys:
        pts = [((x - ox) / res, (y - oy) / res) for x, y in p]
        dr.line(pts, fill=255, width=wpx, joint="curve")
        if wpx > 2:
            r = wpx / 2
            for x, y in (pts[0], pts[-1]):
                dr.ellipse((x - r, y - r, x + r, y + r), fill=255)
    return img


def _filled(polys, res, stroke):
    """Maschera piena (linee + interno) dei poligoni, con origine e dimensioni."""
    pts = [q for p in polys for q in p]
    x0, y0, x1, y1 = g.bbox(pts)
    pad = stroke + 2 * res
    origin = (x0 - pad, y0 - pad)
    size = (int(math.ceil((x1 - x0 + 2 * pad) / res)) + 1, int(math.ceil((y1 - y0 + 2 * pad) / res)) + 1)
    img = _raster(polys, res, stroke, origin, size)
    ImageDraw.floodfill(img, (0, 0), 128)
    a = np.asarray(img)
    return a != 128, a == 255, origin


def build_pieces(res_: Result, ns: NestSettings) -> tuple[list[Piece], dict]:
    report = {"pezzi spuri": 0, "linee orfane": 0}
    if not res_.cut:
        return [], report
    r = 0.5                            # risoluzione fissa per il riconoscimento
    stroke = 0.8           # chiude micro-interruzioni del contorno
    filled, lines, origin = _filled(res_.cut, r, stroke)
    lab = Image.fromarray(filled.astype(np.int32) * OUT, mode="I")   # -1 = da etichettare
    n = 0
    arr = np.asarray(lab)
    while True:
        idx = np.argwhere(np.asarray(lab) == OUT)
        if not len(idx):
            break
        n += 1
        y, x = idx[0]
        ImageDraw.floodfill(lab, (int(x), int(y)), n)
    arr = np.asarray(lab)
    H, W = arr.shape

    def label(p):
        m = p[len(p) // 2] if len(p) > 2 else g.lerp(p[0], p[-1], 0.5)
        x = int(round((m[0] - origin[0]) / r)); y = int(round((m[1] - origin[1]) / r))
        win = arr[max(0, y - 2):y + 3, max(0, x - 2):x + 3]   # intorno 5x5: robusto ai mezzi pixel
        v = win[win > 0]
        return int(np.bincount(v).argmax()) if v.size else 0

    groups: dict[int, Piece] = {}
    for p in res_.cut:
        groups.setdefault(label(p), Piece([], [])).cut.append(p)
    for p in res_.fold:
        lb = label(p)
        if lb in groups and lb:
            groups[lb].fold.append(p)
        else:
            report["linee orfane"] += 1
    pieces = []
    for lb, pc in groups.items():
        if lb == 0:
            report["linee orfane"] += len(pc.cut); continue
        blob = arr == lb
        interior = (blob & ~lines).sum() * r * r
        if interior < 20 and sum(g.length(p) for p in pc.cut) < 100:
            report["pezzi spuri"] += 1          # linea aperta isolata (residuo grafico)
            continue
        pc.area_mm2 = blob.sum() * r * r
        pieces.append(pc)
    return pieces, report


def _hull(pts):
    pts = sorted(set(pts))
    if len(pts) < 3:
        return pts
    cross = lambda o, a, b: (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, up = [], []
    for p in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(up) >= 2 and cross(up[-2], up[-1], p) <= 0:
            up.pop()
        up.append(p)
    return lo[:-1] + up[:-1]


def _min_rect_angle(pts) -> float:
    """Angolo (gradi) che rende minimo il rettangolo d'ingombro."""
    h = _hull(pts)
    best, ang = float("inf"), 0.0
    for a, b in zip(h, h[1:] + h[:1]):
        t = -math.atan2(b[1] - a[1], b[0] - a[0])
        c, s = math.cos(t), math.sin(t)
        xs = [x * c - y * s for x, y in h]; ys = [x * s + y * c for x, y in h]
        ar = (max(xs) - min(xs)) * (max(ys) - min(ys))
        if ar < best:
            best, ang = ar, math.degrees(t)
    return ang


def _rot(polys, deg):
    t = math.radians(deg); c, s = math.cos(t), math.sin(t)
    return [[(x * c - y * s, x * s + y * c) for x, y in p] for p in polys]


def _collisions(occ: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """coll[y,x] > 0 se il pezzo posto in (x,y) tocca celle occupate."""
    H, W = occ.shape; h, w = mask.shape
    s = (H + h, W + w)
    c = np.fft.irfft2(np.fft.rfft2(occ, s) * np.conj(np.fft.rfft2(mask, s)), s)
    return c[: H - h + 1, : W - w + 1]


ORDERS = (
    lambda p: -p.area_mm2,                                   # area
    lambda p: -max(_dims(p)),                                # lato più lungo
    lambda p: -(_dims(p)[0] * _dims(p)[1]),                  # ingombro
)


def _dims(p: Piece):
    x0, y0, x1, y1 = g.bbox([q for c in p.cut for q in c])
    return x1 - x0, y1 - y0


def nest(pieces: list[Piece], ns: NestSettings) -> tuple[list[Result], list[str]]:
    """Prova più ordinamenti e tiene quello con meno fogli (e ultimo foglio più vuoto)."""
    best = None
    for key in ORDERS[:max(1, ns.tries)]:
        res, warn = _nest_once(sorted(pieces, key=key), ns)
        last = sum(g.area(p) for p in res[-1].cut if g.is_closed(p)) if res else 0
        score = (len(res), last)
        if best is None or score < best[0]:
            best = (score, res, warn)
    return best[1], best[2]


def _nest_once(order: list[Piece], ns: NestSettings) -> tuple[list[Result], list[str]]:
    r = ns.res_mm
    gap = max(ns.gap_mm, 2 * r)
    UW, UH = ns.sheet_w - 2 * ns.margin_mm, ns.sheet_h - 2 * ns.margin_mm
    gw, gh = int(UW / r), int(UH / r)
    sheets: list[tuple[np.ndarray, Result]] = []
    warnings = []
    for k, pc in enumerate(order):
        base = _min_rect_angle([q for p in pc.cut for q in p])
        n = max(1, int(round(360 / ns.step_deg)))
        angles = sorted({round((base + i * 360 / n) % 360, 3) for i in range(n)} |
                        {round((base + a) % 360, 3) for a in (0, 90, 180, 270)})
        cands = []
        for a in angles:
            cut, fold = _rot(pc.cut, a), _rot(pc.fold, a)
            mask, _, origin = _filled(cut, r, gap)
            # righe griglia contate dall'alto del foglio: impaginazione alto-sinistra
            cands.append((a, cut, fold, mask[::-1].astype(np.float32), origin))

        def try_sheet(occ):
            best = None
            for a, cut, fold, m, origin in cands:
                h, w = m.shape
                if h > occ.shape[0] or w > occ.shape[1]:
                    continue
                coll = _collisions(occ, m)
                ys, xs = np.nonzero(coll < 0.5)
                if not len(ys):
                    continue
                score = (ys + h) * 4 + xs * 1.0           # più in alto, poi più a sinistra
                i = int(np.argmin(score))
                sc = float(score[i])
                if best is None or sc < best[0]:
                    best = (sc, int(xs[i]), int(ys[i]), cut, fold, m, origin)
            return best

        placed = False
        for occ, out in sheets:
            b = try_sheet(occ)
            if b:
                _place(occ, out, b, r, ns); placed = True; break
        if not placed:
            occ = np.zeros((gh, gw), np.float32)
            out = Result(size=(ns.sheet_w, ns.sheet_h))
            b = try_sheet(occ)
            if b is None:
                warnings.append(f"Pezzo {k + 1} più grande del foglio: messo su un foglio a parte.")
                a, cut, fold, m, origin = cands[0]
                x0, y0, x1, y1 = g.bbox([q for p in cut for q in p])
                dx, dy = ns.margin_mm - x0, ns.sheet_h - ns.margin_mm - y1
                out.cut += [[(x + dx, y + dy) for x, y in p] for p in cut]
                out.fold += [[(x + dx, y + dy) for x, y in p] for p in fold]
                out.size = (max(ns.sheet_w, x1 - x0 + 2 * ns.margin_mm), max(ns.sheet_h, y1 - y0 + 2 * ns.margin_mm))
                sheets.append((np.ones((gh, gw), np.float32), out))
                continue
            _place(occ, out, b, r, ns)
            sheets.append((occ, out))
    results = [out for _, out in sheets]
    for out in results:
        out.nodes_after = sum(len(p) for p in out.cut + out.fold)
    return results, warnings


def _place(occ, out: Result, b, r, ns: NestSettings):
    _, x, y, cut, fold, m, origin = b
    h, w = m.shape
    occ[y:y + h, x:x + w] = np.maximum(occ[y:y + h, x:x + w], m)
    dx = ns.margin_mm + x * r - origin[0]
    dy = ns.sheet_h - ns.margin_mm - origin[1] - (y + h - 1) * r   # maschera capovolta
    out.cut += [[(px + dx, py + dy) for px, py in p] for p in cut]
    out.fold += [[(px + dx, py + dy) for px, py in p] for p in fold]


def usage(results: list[Result], pieces: list[Piece], ns: NestSettings) -> float:
    """Percentuale di foglio occupata dai pezzi."""
    tot = len(results) * ns.sheet_w * ns.sheet_h
    return 100 * sum(p.area_mm2 for p in pieces) / tot if tot else 0.0
