# Teiser — reverse engineering CAD del contenitore TAISER

Ricostruzione di un modello CAD **parametrico** (STEP) a partire da una mesh OBJ Tinkercad, con
tavola tecnica quotata in PDF e DXF generata dal modello.

L'oggetto è un contenitore per elettronica in due pezzi: scatola 80 × 46 × 27 mm con una cupola
paraboloidica sul fianco, e coperchio 73.86 × 46 × 2.5 mm.

Esiste in due forme, che condividono lo stesso codice di calcolo:

* la **pipeline da riga di comando**, completa e verificata (fasi 1–5);
* la **web app**, un runner della stessa pipeline in cui si carica una mesh (OBJ, STL, PLY, WRL) e si segue tutto dal
  browser — analisi, decisioni sulle quote, build, tavola, download.

## Struttura

```
input/     model.obj, model.mtl      sorgenti Tinkercad (sola lettura)
tools/     analisi della mesh        misura, segmentazione, sezioni, render, confronto
cad/       costruzione               params.json (quote misurate), build_model.py,
                                     make_drawing.py (tavola del TAISER)
output/    STEP, STL, FCStd, PDF, DXF, SVG
docs/      lost+found_design.md, BUILD-LOG.md, CONVENTIONS.md, webapp-architecture.md

core/      generico — non sa nulla del pezzo
  freecad/     runner headless: stdin chiuso, timeout, argomenti, sentinella
  mesh/        caricamento (OBJ, STL, PLY, WRL) e misura della mesh
  drafting/    motore di disegno: primitive 2D, backend SVG/PDF/DXF, cornice e
               cartiglio, proiezione con linee nascoste, compositore di tavole
  provenance/  registro quote e decisioni: la regola non negoziabile, in codice
  plugin.py    il contratto PartPlugin e il registry dei pezzi
parts/     specifico del pezzo
  auto/        nessun pezzo: misura la mesh, la ricostruisce con un repertorio
               dichiarato e ne compone la tavola (drawing.py)
  teiser/      contenitore TAISER: cabla tools/ e cad/ dentro la pipeline web
  demo_box/    implementazione di riferimento di PartPlugin
webapp/
  backend/   FastAPI, coda job in-process, SQLite, log SSE
  frontend/  React + Vite + three.js
```

Regola di collocazione: **se contiene un numero, un nome di feature o un'assunzione geometrica del
pezzo, sta in `parts/`. Tutto il resto è `core/`.**

## Come rigenerare (riga di comando)

```bash
.venv/bin/python tools/extract_params.py
/Applications/FreeCAD.app/Contents/MacOS/FreeCAD -c cad/build_model.py < /dev/null
/Applications/FreeCAD.app/Contents/MacOS/FreeCAD -c cad/make_drawing.py < /dev/null
/Applications/FreeCAD.app/Contents/MacOS/FreeCAD -c tools/compare_model_mesh.py < /dev/null
```

Il `< /dev/null` è necessario: senza, FreeCAD esegue lo script e resta appeso sulla console.
Nel backend web lo stesso vincolo è `stdin=DEVNULL` dentro `core/freecad/runner.py`, insieme alle
altre trappole verificate (vedi `docs/BUILD-LOG.md`).

## Web app

```bash
pip install -r webapp/backend/requirements.txt
export FREECAD_BIN=/Applications/FreeCAD.app/Contents/MacOS/FreeCAD   # macOS
export TEISER_DB_PATH=./data/teiser.db TEISER_RUNS_DIR=./data/runs
uvicorn webapp.backend.app.main:app --reload --port 8000

cd webapp/frontend && npm install && npm run dev     # http://localhost:5173
```

Il dev server inoltra `/api` al backend: niente CORS da configurare. Senza FreeCAD l'app parte lo
stesso — analisi, tabella delle quote e decisioni funzionano; build e tavola sono disabilitate, e
l'intestazione lo dice. La tavola si disegna sul solido costruito: senza build non c'è geometria da
proiettare, e lo step si ferma dicendolo invece di disegnare un ingombro a memoria.

In Docker:

```bash
docker compose -f docker/docker-compose.yml up --build
```

L'immagine porta FreeCAD 1.1.3 da conda-forge — la stessa minor del Mac di sviluppo — e il build
fallisce se lo smoke test headless non passa.

Test: `python -m pytest tests/ -q`. Quelli che richiedono FreeCAD si saltano da soli se non c'è.

### Deploy di prova (Render)

Per un link pubblico su cui provare la pipeline, senza tenere nulla acceso in locale:

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/ilgrinta99/reversed-cad)

Il bottone usa `render.yaml` in radice: build dell'immagine di `docker/Dockerfile` (FreeCAD
compreso), un solo servizio web, piano gratuito. Richiede un account Render collegato a GitHub —
lo crea Render al primo click, non serve prepararlo prima.

Limiti del piano gratuito, da sapere prima di usarlo:

- **Nessun disco persistente.** `/data` (i run, il database SQLite) viene azzerato a ogni riavvio
  o redeploy: va bene per provare la pipeline, non per tenere risultati.
- **Il servizio si addormenta dopo 15 minuti di inattività** e la prima richiesta successiva
  impiega un po' a risvegliarlo (l'immagine con FreeCAD è pesante).
- **512 MB di RAM.** La build di un pezzo con FreeCAD può avvicinarsi al limite; se un job va in
  errore senza un messaggio chiaro, è il primo sospetto.

Per un uso reale — dati persistenti, niente sospensione — serve un piano a pagamento con un disco
allegato al servizio.

## Il punto da sapere

La tavola TinkerCAD fornita come «fonte di verità per tutte le misure» **non lo è**: le sue 6 quote
coincidono al millesimo col bounding box della mesh perché è stata generata dalla mesh stessa, e
tace su tutto il resto — cavità, spessori, cupola, fori, colonnine. L'unica fonte reale di quote è
la mesh. Vedi [docs/lost+found_design.md](docs/lost+found_design.md) §2.1 e [LORE.md](LORE.md).

Da qui la regola non negoziabile: **nessuna quota inventata**. Nella web app non è una convenzione
ma `core/provenance/`: una build con anche una sola quota non misurata né approvata non parte.

## Stato

Fasi 1–5 completate. Scostamento modello ↔ mesh: mediana 0.015 mm (scatola), 0.013 mm (coperchio).
Dettagli e punti aperti in [STATE.md](STATE.md); architettura della web app in
[docs/webapp-architecture.md](docs/webapp-architecture.md).
