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
| Pieghe disegnate a segmentini (PDF reali) | Riconosce i trattini *disegnati* (segmenti corti allineati) e li sposta in Piega |
| *(nuovo)* Risparmio carta | **Nesting** dei pezzi su fogli A4 (o A3, Letter, tappetino 12"): rotazioni, incastro sulla forma reale |
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
5. **Nesting**: lascia attivo *Disponi i pezzi sui fogli*, scegli il foglio, margine e spazio fra pezzi.
   In *Unisci pagine* puoi mettere es. `4-7` per disporre insieme i pezzi di più pagine
   (solo se usi **lo stesso colore di carta**: nei modelli multicolore ogni pagina è un colore).
   **Calcola nesting** mostra i fogli in anteprima.
6. **Esporta DXF…** → un file per foglio (`nome_foglio1.dxf`, `nome_foglio2.dxf`…).
   In Silhouette Studio apri il file direttamente (**non usare Traccia**); i pezzi sono impaginati dall'angolo in alto a sinistra.

CLI (ruoli automatici):
```bash
python main.py modello.pdf -p 2 -o stella.dxf --svg
python -m cameo_dxf modello.pdf --outer-only --simplify 0.1 --r2000
python main.py modello.pdf -p 4-7 --nest              # fogli A4 per ogni pagina
python main.py modello.pdf -p 4-7 --nest --merge      # tutte le pagine sugli stessi fogli
python main.py modello.pdf -p 4 --nest --sheet MAT12 --margin 10 --gap 3
```

## Struttura

```
cameo_dxf/
  pdf_reader.py   estrazione tracciati vettoriali + stili (PyMuPDF)
  geometry.py     Bézier→polilinea, semplificazione RDP, tratteggi, unione frammenti
  processing.py   ruoli taglio/piega, pulizia artefatti, contorno esterno, adattamento
  nesting.py      riconoscimento pezzi e disposizione sui fogli (numpy + Pillow)
  exporters.py    DXF R14 nativo, DXF R2000 (ezdxf), SVG di controllo
  gui.py          interfaccia Tkinter
  cli.py          riga di comando
tests/            test con PDF sintetico (pytest)
```

## Come funziona il nesting

1. I contorni di taglio vengono rasterizzati e riempiti dall'esterno: ogni zona chiusa è un pezzo
   (funziona anche se il contorno è spezzato in più tratti o ha incroci a T).
2. Pieghe e tagli interni vengono assegnati al pezzo che li contiene; le linee isolate fuori dai pezzi vengono scartate.
3. Ogni pezzo viene provato a più rotazioni (passo 15° + quella del minimo ingombro), **mai specchiato**
   (le pieghe monte/valle restano corrette), e messo nella posizione libera più in alto a sinistra;
   le collisioni sono calcolate sulla forma reale (FFT), quindi i pezzi concavi si incastrano.
4. Vengono provati 3 ordinamenti e tenuto quello con meno fogli.

## Note

- Le curve vengono linearizzate (LWPOLYLINE non contiene Bézier): *Precisione curve* 0,05 mm è invisibile al taglio.
- *Solo contorno esterno* elimina i tagli interni (finestre, fessure): usalo solo se il modello non ne ha.
- Se un PDF non ha vettori (scansione), l'app lo segnala: serve il PDF originale.
- Se Silhouette Studio rifiuta l'R14, prova il formato **R2000 (ezdxf)**.
