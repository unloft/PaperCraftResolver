# PaperCraft Resolver

PDF di papercraft → **DXF R14** pronto per **Silhouette Cameo 5 Alpha** (doppio carrello lama + penna).

Automatizza il workflow del manuale *Inkscape → DXF*, senza bisogno di Inkscape:

| Passo manuale (Inkscape) | Cosa fa l'app |
|---|---|
| Apri PDF, una pagina alla volta | Legge i **vettori reali** della pagina scelta con PyMuPDF (niente PNG/Traccia → niente doppi contorni) |
| Pulizia testi, immagini, istruzioni | Testi e immagini non vengono estratti; i riempimenti (colori, testi vettorializzati) sono *Scarta* di default |
| Separa gruppi (Ctrl+Maiusc+G) | I tracciati sono già esplosi in sotto‑tracciati singoli |
| Elimina artefatti | Rimuove bordi pagina, linee lunghissime, linee bianche/invisibili, doppioni, frammenti minuscoli |
| Semplifica (Ctrl+L) | Ramer‑Douglas‑Peucker con tolleranza in mm |
| Pieghe tratteggiate aperte | Il tratteggio del PDF diventa **segmenti aperti reali**; le pieghe sono sempre scritte aperte |
| Ridimensiona pagina al disegno | Area di disegno adattata al contenuto + margine |
| Salva come DXF R14, mm, LWPOLYLINE, no spline ROBO‑Master, no Appiattisci Bézier | Writer R14 nativo: `$INSUNITS=4` (mm), solo `LWPOLYLINE`, nessuna SPLINE |

Layer/colori in uscita:

- **TAGLIO – rosso (ACI 1)** → lama, velocità 4‑6
- **PIEGHE – blu (ACI 5)** → penna *Schizzo*, velocità 10, forza 1

## Installazione

```bash
pip install -r requirements.txt
```
Tkinter è incluso in Python per Windows/macOS (su Linux: `sudo apt install python3-tk`).

## Uso

GUI:
```bash
python main.py
```
1. **Apri PDF…** e scegli la pagina.
2. La tabella mostra gli **stili** trovati (colore, spessore, tratteggio, numero tracciati) con un ruolo proposto in automatico: tratteggio → *Piega*, linea continua → *Taglio*, riempimenti/bianco → *Scarta*.
3. Seleziona una riga per vederla in **arancio** nell'anteprima e correggi il ruolo con *→ Taglio / → Piega / → Scarta*.
4. Regola le opzioni (semplificazione, solo contorno esterno, ecc.) e controlla nodi eliminati e dimensioni.
5. **Esporta DXF…** → in Silhouette Studio apri il file direttamente (**non usare Traccia**).

CLI (ruoli automatici):
```bash
python main.py modello.pdf -p 2 -o stella.dxf --svg
python -m cameo_dxf modello.pdf --outer-only --simplify 0.1 --r2000
```

## Struttura

```
cameo_dxf/
  pdf_reader.py   estrazione tracciati vettoriali + stili (PyMuPDF)
  geometry.py     Bézier→polilinea, semplificazione RDP, tratteggi, unione frammenti
  processing.py   ruoli taglio/piega, pulizia artefatti, contorno esterno, adattamento
  exporters.py    DXF R14 nativo, DXF R2000 (ezdxf), SVG di controllo
  gui.py          interfaccia Tkinter
  cli.py          riga di comando
tests/            test con PDF sintetico (pytest)
```

## Note

- Le curve vengono linearizzate (LWPOLYLINE non contiene Bézier): *Precisione curve* 0,05 mm è invisibile al taglio.
- *Solo contorno esterno* elimina i tagli interni (finestre, fessure): usalo solo se il modello non ne ha.
- Se un PDF non ha vettori (scansione), l'app lo segnala: serve il PDF originale.
- Se Silhouette Studio rifiuta l'R14, prova il formato **R2000 (ezdxf)**.
