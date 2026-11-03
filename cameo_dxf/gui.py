"""Interfaccia Tkinter: carica PDF, mappa stili -> Taglio/Piega/Scarta, anteprima, export."""
from __future__ import annotations
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import geometry as g
from .exporters import write_dxf_r14, write_dxf_r2000, write_svg
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
        self.tree = ttk.Treeview(left, columns=cols, show="headings", height=12, selectmode="extended")
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
        }
        labels = {
            "simplify_mm": "Semplifica nodi (mm, 0=off)", "flatten_tol_mm": "Precisione curve (mm)",
            "join_tol_mm": "Unione frammenti (mm)", "min_length_mm": "Scarta frammenti < (mm)",
            "margin_mm": "Margine area disegno (mm)", "long_line_ratio": "Linea spuria se > % pagina",
            "explode_dashes": "Tratteggi → segmenti aperti", "remove_artifacts": "Rimuovi bordi/linee spurie",
            "remove_duplicates": "Rimuovi doppi contorni", "join_cut": "Unisci contorni di taglio",
            "outer_only": "Solo contorno esterno (elimina tagli interni)",
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

        self.stats = tk.Text(left, height=9, wrap="word", font=("TkFixedFont", 9))
        self.stats.pack(fill="x", pady=4)

        # anteprima
        self.canvas = tk.Canvas(right, bg="white", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: self.draw())
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

    def export(self):
        if not self.result or not (self.result.cut or self.result.fold):
            messagebox.showwarning("Niente da esportare", "Carica un PDF e assegna almeno un ruolo.")
            return
        base = os.path.splitext(self.pdf)[0] + f"_p{self.page_var.get()}.dxf"
        path = filedialog.asksaveasfilename(defaultextension=".dxf", initialfile=os.path.basename(base),
                                            filetypes=[("DXF", "*.dxf")])
        if not path:
            return
        try:
            (write_dxf_r2000 if self.fmt.get() == "R2000" else write_dxf_r14)(self.result, path)
            if self.svg_var.get():
                write_svg(self.result, os.path.splitext(path)[0] + ".svg")
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Errore export", str(e)); return
        messagebox.showinfo("Esportato",
                            f"{path}\n\nIn Silhouette Studio: apri il DXF (NON usare Traccia).\n"
                            "Rosso/TAGLIO → lama, Velocità 4-6.\nBlu/PIEGHE → penna Schizzo, Velocità 10, Forza 1.")


def main():
    App().mainloop()
