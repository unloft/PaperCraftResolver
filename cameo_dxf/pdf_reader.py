"""Estrazione dei vettori reali dal PDF con PyMuPDF (niente raster, niente Traccia)."""
from __future__ import annotations
import math
import re
from dataclasses import dataclass, field

import pymupdf

from .geometry import Pt, dist

PT2MM = 25.4 / 72.0


def _hex(c) -> str:
    if c is None:
        return "nessuno"
    return "#" + "".join(f"{int(round(max(0, min(1, v)) * 255)):02x}" for v in c[:3])


@dataclass(frozen=True)
class Style:
    stroke: tuple | None          # RGB 0-1 della linea (None = solo riempimento)
    fill: tuple | None            # RGB 0-1 del riempimento
    width: float                  # spessore linea in mm
    dashes: tuple = ()            # pattern tratteggio in mm
    dash_phase: float = 0.0
    stroke_opacity: float = 1.0

    @property
    def dashed(self) -> bool:
        return bool(self.dashes) and sum(self.dashes) > 1e-6

    @property
    def key(self) -> str:
        kind = "TRATTEGGIO" if self.dashed else ("LINEA" if self.stroke else "RIEMPIMENTO")
        s = f"{kind} | linea {_hex(self.stroke)} {self.width:.2f}mm"
        if self.dashed:
            s += " [" + " ".join(f"{d:.1f}" for d in self.dashes) + "]"
        if self.fill is not None:
            s += f" | riemp. {_hex(self.fill)}"
        return s

    @property
    def stroke_hex(self) -> str:
        return _hex(self.stroke)


@dataclass
class SubPath:
    segments: list = field(default_factory=list)   # ('l',p0,p1) | ('c',p0,p1,p2,p3) in mm
    closed: bool = False

    @property
    def start(self) -> Pt:
        return self.segments[0][1]

    @property
    def end(self) -> Pt:
        return self.segments[-1][-1]


@dataclass
class VPath:
    style: Style
    subpaths: list[SubPath]


@dataclass
class TextItem:
    text: str
    center: Pt          # mm, Y verso l'alto
    angle: float        # gradi, antiorario
    size: float         # corpo del font in mm


@dataclass
class PageData:
    index: int
    width_mm: float
    height_mm: float
    paths: list[VPath]
    n_text: int = 0
    n_images: int = 0
    texts: list = field(default_factory=list)

    def styles(self) -> dict[str, tuple[Style, int]]:
        out: dict[str, tuple[Style, int]] = {}
        for p in self.paths:
            st, n = out.get(p.style.key, (p.style, 0))
            out[p.style.key] = (st, n + len(p.subpaths))
        return out


def _parse_dashes(s) -> tuple[tuple, float]:
    if not s:
        return (), 0.0
    m = re.match(r"\s*\[(.*?)\]\s*([-\d.]+)?", str(s))
    if not m:
        return (), 0.0
    nums = tuple(float(x) * PT2MM for x in re.findall(r"[-\d.]+", m.group(1)))
    phase = float(m.group(2)) * PT2MM if m.group(2) else 0.0
    return nums, phase


def page_count(pdf_path: str) -> int:
    with pymupdf.open(pdf_path) as doc:
        return doc.page_count


def read_page(pdf_path: str, page_index: int = 0) -> PageData:
    """Legge una pagina (0-based) e restituisce i tracciati vettoriali in mm, Y verso l'alto."""
    with pymupdf.open(pdf_path) as doc:
        page = doc[page_index]
        r = page.rect
        T = lambda p: ((p.x - r.x0) * PT2MM, (r.y1 - p.y) * PT2MM)
        paths: list[VPath] = []
        for d in page.get_drawings():
            stroke = d.get("color") if d.get("type") in ("s", "fs") else None
            fill = d.get("fill") if d.get("type") in ("f", "fs") else None
            dashes, phase = _parse_dashes(d.get("dashes"))
            so = d.get("stroke_opacity")
            style = Style(
                stroke=tuple(stroke) if stroke else None,
                fill=tuple(fill) if fill else None,
                width=float(d.get("width") or 0) * PT2MM,
                dashes=dashes, dash_phase=phase,
                stroke_opacity=1.0 if so is None else float(so),
            )
            subs: list[SubPath] = []
            cur: SubPath | None = None
            for it in d["items"]:
                k = it[0]
                if k in ("re", "qu"):
                    if cur and cur.segments:
                        subs.append(cur)
                    cur = None
                    if k == "re":
                        q = it[1]
                        c = [T(q.tl), T(q.tr), T(q.br), T(q.bl)]
                    else:
                        q = it[1]
                        c = [T(q.ul), T(q.ur), T(q.lr), T(q.ll)]
                    subs.append(SubPath([("l", c[i], c[(i + 1) % 4]) for i in range(4)], True))
                    continue
                pts = [T(p) for p in it[1:]]
                if cur is None or dist(cur.end, pts[0]) > 1e-4:
                    if cur and cur.segments:
                        subs.append(cur)
                    cur = SubPath()
                cur.segments.append(("l", *pts) if k == "l" else ("c", *pts))
            if cur and cur.segments:
                subs.append(cur)
            if d.get("closePath") and subs and not subs[-1].closed:
                sp = subs[-1]
                if dist(sp.start, sp.end) > 1e-4:
                    sp.segments.append(("l", sp.end, sp.start))
                sp.closed = True
            for sp in subs:
                if not sp.closed and len(sp.segments) > 1 and dist(sp.start, sp.end) < 1e-4:
                    sp.closed = True
            if subs:
                paths.append(VPath(style, subs))
        texts = []
        for b in page.get_text("rawdict")["blocks"]:
            for ln in b.get("lines", []):
                dx, dy = ln["dir"]
                ang = math.degrees(math.atan2(-dy, dx))
                for sp in ln["spans"]:
                    t = "".join(ch["c"] for ch in sp["chars"]).strip()
                    if not t:
                        continue
                    x0, y0, x1, y1 = sp["bbox"]
                    c = T(pymupdf.Point((x0 + x1) / 2, (y0 + y1) / 2))
                    texts.append(TextItem(t, c, ang, sp["size"] * PT2MM))
        return PageData(
            index=page_index,
            width_mm=r.width * PT2MM, height_mm=r.height * PT2MM,
            paths=paths,
            n_text=len(page.get_text("words")),
            n_images=len(page.get_images(full=True)),
            texts=texts,
        )
