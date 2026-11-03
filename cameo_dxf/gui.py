"""Interfaccia Tkinter: carica PDF, mappa stili -> Taglio/Piega/Scarta, anteprima, export."""
from __future__ import annotations
import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import geometry as g
from .exporters import write_dxf_r14, write_dxf_r2000, write_svg
from .cli import SHEETS, parse_pages
from .nesting import NestSettings, build_pieces, nest, usage
from .pdf_reader import page_count, read_page
from .processing import CUT, FOLD, SKIP, Settings, auto_roles, process

COLORS = {CUT: "#e00000", FOLD: "#0050ff", SKIP: "#999999"}


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PaperCraft Resolver – PDF → DXF Cameo 5")
        self.geometry("1250x780")
        self.pdf = None
        self.page = None
        self.roles: dict[str, str] = {}
        self.result = None
        self.sheets = None          # risultato nesting (lista di fogli)
        self._build()

    # ---------- UI ----------
    def _build(self):
        bar = ttk.Frame(self, padding=4); bar.pack(fill="x")
        ttk.Button(bar, text="Apri PDF…", command=self.open_pdf).pack(side="left")
        ttk.Label(bar, text=" Pagina:").pack(side="left")
        self.page_var = tk.IntVar(value=1)
        self.page_spin = ttk.Spinbox(bar, from_=1, to=1, width=5, textvariable=self.page_var,
                                     command=self.load_page)
        self.page_spin.pack(side="left")
        ttk.Button(bar, text="Carica pagina", command=self.load_page).pack(side="left", padx=4)
        ttk.Button(bar, text="Aggiorna anteprima", command=self.run).pack(side="left", padx=4)
        ttk.Button(bar, text="Esporta DXF…", command=self.export).pack(side="left", padx=4)
        self.file_lbl = ttk.Label(bar, text="Nessun file"); self.file_lbl.pack(side="left", padx=10)

        pw = ttk.PanedWindow(self, orient="horizontal"); pw.pack(fill="both", expand=True)
        left = ttk.Frame(pw, padding=4); pw.add(left, weight=1)
        right = ttk.Frame(pw); pw.add(right, weight=2)

        # tabella stili
        ttk.Label(left, text="Stili trovati nel PDF (seleziona e assegna il ruolo):").pack(anchor="w")
        cols = ("ruolo", "colore", "n", "stile")
        self.tree = ttk.Treeview(left, columns=cols, show="headings", height=6, selectmode="extended")
        for c, w, t in (("ruolo", 70, "Ruolo"), ("colore", 70, "Colore"), ("n", 50, "N."),
                        ("stile", 330, "Stile")):
            self.tree.heading(c, text=t); self.tree.column(c, width=w, anchor="w")
        for r, col in COLORS.items():
            self.tree.tag_configure(r, foreground=col)
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.draw())
        btns = ttk.Frame(left); btns.pack(fill="x", pady=3)
        for r in (CUT, FOLD, SKIP):
            ttk.Button(btns, text=f"→ {r}", command=lambda r=r: self.set_role(r)).pack(side="left", padx=2)
        ttk.Button(btns, text="Auto", command=self.reset_roles).pack(side="left", padx=2)

        # impostazioni
        lf = ttk.LabelFrame(left, text="Pulizia e ottimizzazione", padding=4); lf.pack(fill="x", pady=4)
        d = Settings()
        self.v = {
            "simplify_mm": tk.DoubleVar(value=d.simplify_mm),
            "flatten_tol_mm": tk.DoubleVar(value=d.flatten_tol_mm),
            "join_tol_mm": tk.DoubleVar(value=d.join_tol_mm),
            "min_length_mm": tk.DoubleVar(value=d.min_length_mm),
            "margin_mm": tk.DoubleVar(value=d.margin_mm),
            "long_line_ratio": tk.DoubleVar(value=d.long_line_ratio),
            "explode_dashes": tk.BooleanVar(value=d.explode_dashes),
            "remove_artifacts": tk.BooleanVar(value=d.remove_artifacts),
            "remove_duplicates": tk.BooleanVar(value=d.remove_duplicates),
            "join_cut": tk.BooleanVar(value=d.join_cut),
            "outer_only": tk.BooleanVar(value=d.outer_only),
            "detect_drawn_dashes": tk.BooleanVar(value=d.detect_drawn_dashes),
            "dash_max_mm": tk.DoubleVar(value=d.dash_max_mm),
            "dash_gap_mm": tk.DoubleVar(value=d.dash_gap_mm),
        }
        labels = {
            "simplify_mm": "Semplifica nodi (mm, 0=off)", "flatten_tol_mm": "Precisione curve (mm)",
            "join_tol_mm": "Unione frammenti (mm)", "min_length_mm": "Scarta frammenti < (mm)",
            "margin_mm": "Margine area disegno (mm)", "long_line_ratio": "Linea spuria se > % pagina",
            "explode_dashes": "Tratteggi → segmenti aperti", "remove_artifacts": "Rimuovi bordi/linee spurie",
            "remove_duplicates": "Rimuovi doppi contorni", "join_cut": "Unisci contorni di taglio",
            "outer_only": "Solo contorno esterno (elimina tagli interni)",
            "detect_drawn_dashes": "Riconosci tratteggi disegnati a segmentini",
            "dash_max_mm": "Trattino: lunghezza max (mm)", "dash_gap_mm": "Trattino: distanza max (mm)",
        }
        row = 0
        for k, var in self.v.items():
            if isinstance(var, tk.BooleanVar):
                ttk.Checkbutton(lf, text=labels[k], variable=var, command=self.run).grid(
                    row=row, column=0, columnspan=2, sticky="w")
            else:
                ttk.Label(lf, text=labels[k]).grid(row=row, column=0, sticky="w")
                e = ttk.Entry(lf, textvariable=var, width=8); e.grid(row=row, column=1, sticky="w")
                e.bind("<Return>", lambda ev: self.run())
            row += 1
        fmt = ttk.Frame(left); fmt.pack(fill="x")
        ttk.Label(fmt, text="Formato:").pack(side="left")
        self.fmt = tk.StringVar(value="R14")
        ttk.Radiobutton(fmt, text="DXF R14 (Inkscape)", value="R14", variable=self.fmt).pack(side="left")
        ttk.Radiobutton(fmt, text="DXF R2000 (ezdxf)", value="R2000", variable=self.fmt).pack(side="left")
        self.svg_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(left, text="Salva anche SVG di controllo", variable=self.svg_var).pack(anchor="w")

        nf = ttk.LabelFrame(left, text="Nesting su fogli (risparmio carta)", padding=4)
        nf.pack(fill="x", pady=4)
        self.nest_on = tk.BooleanVar(value=True)
        ttk.Checkbutton(nf, text="Disponi i pezzi sui fogli all'export", variable=self.nest_on).grid(
            row=0, column=0, columnspan=4, sticky="w")
        ttk.Label(nf, text="Foglio").grid(row=1, column=0, sticky="w")
        self.sheet_var = tk.StringVar(value="A4")
        ttk.Combobox(nf, textvariable=self.sheet_var, values=list(SHEETS), width=7).grid(row=1, column=1)
        ttk.Label(nf, text="Margine/Spazio mm").grid(row=1, column=2, sticky="e")
        self.margin_var = tk.DoubleVar(value=5.0); self.gap_var = tk.DoubleVar(value=2.0)
        mf = ttk.Frame(nf); mf.grid(row=1, column=3)
        ttk.Entry(mf, textvariable=self.margin_var, width=4).pack(side="left")
        ttk.Entry(mf, textvariable=self.gap_var, width=4).pack(side="left")
        ttk.Label(nf, text="Unisci pagine").grid(row=2, column=0, sticky="w")
        self.merge_var = tk.StringVar(value="")
        ttk.Entry(nf, textvariable=self.merge_var, width=12).grid(row=2, column=1, sticky="w")
        ttk.Label(nf, text="(es. 4-7, stesso colore carta)").grid(row=2, column=2, columnspan=2, sticky="w")
        self.nest_btn = ttk.Button(nf, text="Calcola nesting", command=self.run_nest)
        self.nest_btn.grid(row=3, column=0, columnspan=2, sticky="w", pady=2)

        # anteprima + statistiche
        self.canvas = tk.Canvas(right, bg="white", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: self.draw())
        self.stats = tk.Text(right, height=7, wrap="word", font=("TkFixedFont", 9))
        self.stats.pack(fill="x", side="bottom")
        ttk.Label(right, text="Rosso = Taglio (lama)   Blu = Piega (penna: Vel. 10, Forza 1)   "
                              "Arancio = stile selezionato").pack(anchor="w")

    # ---------- azioni ----------
    def open_pdf(self):
        path = filedialog.askopenfilename(filetypes=[("PDF", "*.pdf")])
        if not path:
            return
        self.pdf = path
        n = page_count(path)
        self.page_spin.config(to=n); self.page_var.set(1)
        self.file_lbl.config(text=f"{os.path.basename(path)}  ({n} pag.)")
        self.load_page()

    def load_page(self):
        if not self.pdf:
            return
        try:
            self.page = read_page(self.pdf, int(self.page_var.get()) - 1)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Errore", f"Impossibile leggere la pagina:\n{e}")
            return
        if not self.page.paths:
            messagebox.showwarning("Nessun vettore",
                                   "La pagina non contiene tracciati vettoriali (probabile PDF raster).\n"
                                   "Serve il PDF originale vettoriale: non usare PNG + Traccia.")
        self.reset_roles()

    def reset_roles(self):
        if self.page:
            self.roles = auto_roles(self.page)
            self.fill_tree(); self.run()

    def fill_tree(self):
        self.tree.delete(*self.tree.get_children())
        for k, (st, n) in sorted(self.page.styles().items(), key=lambda kv: -kv[1][1]):
            r = self.roles[k]
            self.tree.insert("", "end", iid=k, values=(r, st.stroke_hex, n, k), tags=(r,))

    def set_role(self, role):
        for iid in self.tree.selection():
            self.roles[iid] = role
            vals = list(self.tree.item(iid, "values")); vals[0] = role
            self.tree.item(iid, values=vals, tags=(role,))
        self.run()

    def settings(self) -> Settings:
        try:
            return Settings(**{k: v.get() for k, v in self.v.items()})
        except tk.TclError:
            messagebox.showerror("Valore non valido", "Controlla i campi numerici.")
            return Settings()

    def run(self):
        if not self.page:
            return
        self.result = process(self.page, self.roles, self.settings())
        self.sheets = None
        r = self.result
        red = 100 * (1 - r.nodes_after / r.nodes_before) if r.nodes_before else 0
        txt = (f"Contorni di taglio: {len(r.cut)}\nSegmenti di piega: {len(r.fold)}\n"
               f"Nodi: {r.nodes_before} → {r.nodes_after} (-{red:.0f}%)\n"
               f"Area di disegno: {r.size[0]:.1f} × {r.size[1]:.1f} mm\nEliminati:\n" +
               "\n".join(f"  · {k}: {v}" for k, v in r.removed.items()))
        if r.size[0] > 305 or r.size[1] > 305:
            txt += "\n⚠ Supera 30,5 cm: controlla il tappetino Cameo."
        self.stats.delete("1.0", "end"); self.stats.insert("1.0", txt)
        self.draw()

    def draw(self):
        c = self.canvas; c.delete("all")
        if self.sheets:
            return self.draw_sheets()
        r = self.result
        if not r or not r.size[0]:
            return
        cw, ch = c.winfo_width(), c.winfo_height()
        k = min((cw - 20) / r.size[0], (ch - 20) / r.size[1])
        tx = lambda p: (10 + p[0] * k, ch - 10 - p[1] * k)
        c.create_rectangle(*tx((0, 0)), *tx(r.size), outline="#ddd", dash=(2, 2))
        for polys, col in ((r.cut, COLORS[CUT]), (r.fold, COLORS[FOLD])):
            for p in polys:
                c.create_line(*[v for q in p for v in tx(q)], fill=col, width=1)
        # evidenzia lo stile selezionato (anche se scartato) per riconoscerlo
        sel = set(self.tree.selection())
        if sel and self.page:
            dx, dy = r.offset
            for vp in self.page.paths:
                if vp.style.key in sel:
                    for sp in vp.subpaths:
                        pts = g.flatten(sp.segments, 0.3)
                        if len(pts) > 1:
                            c.create_line(*[v for q in pts for v in tx((q[0] + dx, q[1] + dy))],
                                          fill="#ff8c00", width=2)

    def draw_sheets(self):
        c = self.canvas
        cw, ch = c.winfo_width(), c.winfo_height()
        W, H = self.sheets[0].size
        n = len(self.sheets)
        k = min((cw - 20) / (n * W + (n - 1) * 15), (ch - 30) / H)
        for i, sh in enumerate(self.sheets):
            ox = 10 + i * (W + 15) * k
            tx = lambda p, ox=ox: (ox + p[0] * k, ch - 20 - p[1] * k)
            c.create_rectangle(*tx((0, 0)), *tx(sh.size), outline="#888")
            c.create_text(ox + 4, ch - 18 - H * k, anchor="sw", text=f"Foglio {i + 1}")
            for polys, col in ((sh.cut, COLORS[CUT]), (sh.fold, COLORS[FOLD])):
                for p in polys:
                    c.create_line(*[v for q in p for v in tx(q)], fill=col)

    def nest_settings(self) -> NestSettings:
        sh = self.sheet_var.get().upper()
        w, h = SHEETS.get(sh) or tuple(float(v) for v in sh.lower().split("x"))
        return NestSettings(sheet_w=w, sheet_h=h, margin_mm=self.margin_var.get(), gap_mm=self.gap_var.get())

    def run_nest(self, then=None):
        if not self.result:
            return
        try:
            ns = self.nest_settings()
        except (ValueError, tk.TclError):
            messagebox.showerror("Foglio", "Formato foglio non valido (es. A4 o 210x297)."); return
        merge = self.merge_var.get().strip()
        pages = parse_pages(merge, page_count(self.pdf)) if merge else []
        roles, st, cur, pdf = dict(self.roles), self.settings(), self.page.index, self.pdf
        self.nest_btn.config(state="disabled", text="Calcolo in corso…")

        def work():
            try:
                pieces, rep_all = [], {}
                for pi in (pages or [cur]):
                    pg = self.page if pi == cur else read_page(pdf, pi)
                    rr = auto_roles(pg); rr.update({k: v for k, v in roles.items() if k in rr})
                    pcs, rep = build_pieces(process(pg, rr, st), ns)
                    pieces += pcs
                    for k2, v in rep.items():
                        rep_all[k2] = rep_all.get(k2, 0) + v
                sheets, warns = nest(pieces, ns)
                self.after(0, lambda: self._nest_done(sheets, pieces, ns, rep_all, warns, then))
            except Exception as e:  # noqa: BLE001
                self.after(0, lambda: (messagebox.showerror("Nesting", str(e)), self._nest_reset()))
        threading.Thread(target=work, daemon=True).start()

    def _nest_reset(self):
        self.nest_btn.config(state="normal", text="Calcola nesting")

    def _nest_done(self, sheets, pieces, ns, rep, warns, then):
        self._nest_reset()
        self.sheets = sheets
        txt = (f"\nNesting: {len(pieces)} pezzi su {len(sheets)} fogli "
               f"(occupazione {usage(sheets, pieces, ns):.0f}%)\n" +
               "".join(f"  · {k}: {v}\n" for k, v in rep.items() if v) +
               "".join(f"  ⚠ {w}\n" for w in warns))
        self.stats.insert("end", txt)
        self.draw()
        if then:
            then()

    def export(self):
        if not self.result or not (self.result.cut or self.result.fold):
            messagebox.showwarning("Niente da esportare", "Carica un PDF e assegna almeno un ruolo.")
            return
        if self.nest_on.get() and not self.sheets:
            return self.run_nest(then=self.export)
        base = os.path.splitext(self.pdf)[0] + f"_p{self.page_var.get()}.dxf"
        path = filedialog.asksaveasfilename(defaultextension=".dxf", initialfile=os.path.basename(base),
                                            filetypes=[("DXF", "*.dxf")])
        if not path:
            return
        writer = write_dxf_r2000 if self.fmt.get() == "R2000" else write_dxf_r14
        items = [(self.result, path)]
        if self.nest_on.get() and self.sheets:
            stem = os.path.splitext(path)[0]
            items = [(sh, f"{stem}_foglio{i}.dxf") for i, sh in enumerate(self.sheets, 1)]
        try:
            for res, p in items:
                writer(res, p)
                if self.svg_var.get():
                    write_svg(res, os.path.splitext(p)[0] + ".svg")
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Errore export", str(e)); return
        names = "\n".join(os.path.basename(p) for _, p in items)
        messagebox.showinfo("Esportato",
                            f"{names}\n\nIn Silhouette Studio: apri il DXF (NON usare Traccia).\n"
                            "Rosso/TAGLIO → lama, Velocità 4-6.\nBlu/PIEGHE → penna Schizzo, Velocità 10, Forza 1.")


def main():
    App().mainloop()
