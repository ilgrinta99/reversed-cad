# CLAUDE.md

Reverse engineering CAD: da mesh OBJ Tinkercad a modello parametrico STEP + tavola quotata.

## Leggi prima
1. `STATE.md` — dove siamo, cosa blocca
2. `docs/lost+found_design.md` — tutte le quote, discrepanze D1–D8, ambiguità A–G
3. `LORE.md` — perché la geometria è "sporca" e perché la tavola non è affidabile
4. `docs/CONVENTIONS.md` — unità, datum, regole sul codice

## Regola non negoziabile
**Nessuna quota inventata.** Ogni numero che entra nel modello è (a) misurato dalla mesh con uno
script in `tools/`, oppure (b) approvato esplicitamente dal committente e registrato in `docs/lost+found_design.md`.
Se manca un valore e non è approvato: **fermarsi e chiedere**, non stimare.

## Attenzione
`docs/lost+found_design.md` §2.1 — la tavola TinkerCAD **non è** una fonte indipendente di quote: è generata
dalla mesh e contiene solo 6 ingombri esterni. Non usarla come arbitro.

## Comandi

```bash
.venv/bin/python tools/segment_features.py input/model.obj
.venv/bin/python tools/slice_mesh.py
.venv/bin/python tools/render_views.py input/model.obj /tmp
```

FreeCAD headless (una volta installato):
```bash
/Applications/FreeCAD.app/Contents/MacOS/FreeCAD -c cad/build_model.py
```

## Web app
Si carica un OBJ e si segue tutto dal browser. **Non si sceglie il pezzo:** la mesh
caricata è l'unica specifica. `core/mesh/` la misura (corpi, patch, quote) e ne
ricava le ambiguità di *quel* file; le schede di decisione compaiono dopo
l'analisi, non prima. La pipeline cablata del TAISER resta in `parts/teiser/` e si
raggiunge indicandone l'id all'API: lancia gli script esistenti puntandoli su una
cartella di run (vedi `docs/CONVENTIONS.md`, «Percorsi degli script»).

```bash
uvicorn webapp.backend.app.main:app --reload --port 8000
cd webapp/frontend && npm run dev
python -m pytest tests/ -q
```

- `core/` = generico, `parts/teiser/` = specifico del pezzo. Il confine è la regola
  in `docs/CONVENTIONS.md`: se c'è dentro un numero del TAISER, sta in `parts/`.
- `parts/auto/` è il percorso predefinito e non contiene numeri del pezzo: misura
  la mesh e la ricostruisce con un repertorio dichiarato (prisma, raccordo,
  cavità, fori). Quello che non sa fare lo dichiara come feature non
  ricostruibile: non lo approssima.
- La regola non negoziabile qui sopra è codice in `core/provenance/`, non una
  convenzione: una build con quote non misurate né approvate **non parte**.
- Architettura e stato: `docs/webapp-architecture.md`.

## Ambiente
- Python 3.13 in `.venv/` (numpy). FreeCAD via Homebrew cask, usato headless con `FreeCADCmd`.
- Nel container Linux, FreeCAD 1.1.3 da conda-forge: stessa minor, stessi risultati.
- `input/` è sola lettura. Gli output rigenerabili stanno in `output/`.
