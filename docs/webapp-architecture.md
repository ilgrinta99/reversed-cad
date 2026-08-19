# Teiser Web App — architettura

Stato: **bozza operativa**, scritta prima che il codice Teiser fosse disponibile nel
repo cloud (vedi §0). Le decisioni di stack sono confermate dall'utente; i confini
architetturali qui descritti vanno verificati contro il codice reale al primo merge.

---

## 0. Premessa sul contesto (leggere per prima)

Il repo `ilgrinta99/reversed-cad` era vuoto quando questo documento è stato scritto:
nessun commit, nessun ref sul remote. Il progetto Teiser (~1900 righe di Python,
`STATE.md`, `LORE.md`, `docs/lost+found_design.md`, `docs/BUILD-LOG.md`,
`docs/CONVENTIONS.md`, `CLAUDE.md`) vive solo su
`/Users/macmini003/Documents/doc/develop/Teiser`.

Conseguenza pratica: quanto segue è progettato **dai vincoli dichiarati dall'utente**,
non dalla lettura del codice. Ogni punto marcato `[DA VERIFICARE]` è un'assunzione
sull'interfaccia dei moduli esistenti, da confermare quando il codice arriva.

Per allineare:

```bash
cd /Users/macmini003/Documents/doc/develop/Teiser
git remote add origin https://github.com/ilgrinta99/reversed-cad
git push -u origin master
```

---

## 1. Scopo, e i suoi confini

Un **runner web della pipeline Teiser esistente**: l'utente carica un OBJ, l'app
esegue analisi → parametri → modello → tavola, mostra il passaggio decisionale sulle
quote, restituisce STEP/STL/PDF/DXF/SVG e il report di verifica, e consente di
modificare i parametri e rilanciare.

**Non** è, oggi, uno strumento generico di reverse engineering con riconoscimento
automatico delle feature su una mesh qualsiasi. Le feature del contenitore TAISER
(cupola paraboloidica, 4 colonnine di cui una diversa, asole, tasche ellittiche)
restano codificate — ma isolate dietro il confine di §3.

## 2. Stack (confermato)

| Livello | Scelta |
|---|---|
| Backend | FastAPI (Python) |
| Coda job | in-process (worker pool asyncio/thread), stato e log su **SQLite** |
| Log live | SSE (`text/event-stream`) |
| Frontend | React + Vite, three.js per anteprima STL e mappa di scostamento |
| Tavola in browser | SVG prodotto da `draft2d.py` — nessun FreeCAD nel percorso di anteprima |
| Packaging | Docker, FreeCAD da **conda-forge** in immagine Linux |
| Hosting | locale (docker compose) per ora; l'immagine resta deployabile altrove |

Motivo della coda in-process: lo scenario è mono-utente / piccolo team, i job durano
secondi–decine di secondi, e un solo container evita di trascinarsi Redis + worker
separato. Il confine `JobQueue` è comunque un'interfaccia: passare a RQ/Celery in
seguito non tocca gli endpoint.

## 3. Il confine che decide se il progetto scala

```
core/                     GENERICO — nessuna conoscenza del pezzo
  mesh/                   caricamento OBJ, bbox, clustering piani, sezioni,
                          segmentazione patch, render ortografici
  drafting/               draft2d.py — primitive 2D + backend SVG/PDF/DXF
  compare/                distanza punto-superficie modello ↔ mesh
  provenance/             registro delle quote: misurato / usato / origine / approvazione
  freecad/                runner headless (§4)

parts/
  teiser/                 SPECIFICO DEL PEZZO
    schema.py             schema di params.json (pydantic) — quote e loro provenienza
    extract.py            orchestrazione dei tools/ di misura per questo pezzo
    build.py              costruzione dei solidi (ex cad/build_model.py)
    drawing.py            impaginazione della tavola (ex cad/make_drawing.py)
    decisions.py          D1–D8 e A–G dichiarate come dati, non come if sparsi

webapp/
  backend/                API, job runner, storage, adattatori verso parts/*
  frontend/               React/Vite
```

`parts/*` espone un unico protocollo (`PartPlugin`): `extract()`, `decisions()`,
`build()`, `draw()`, `compare()`. Il backend web non importa mai `parts.teiser`
direttamente: passa per il registry. Quando arriverà un secondo pezzo, o il
riconoscimento automatico delle feature, si aggiunge un plugin — non si riscrive
il runner.

Regola di collocazione, per non dover discutere caso per caso: **se un modulo
contiene un numero, un nome di feature o un'assunzione geometrica specifici del
contenitore TAISER, sta in `parts/teiser/`.** Tutto il resto è `core/`.

`[DA VERIFICARE]` La ripartizione dei `tools/*.py` esistenti fra `core/mesh` e
`parts/teiser`: `extract_params.py`, `fit_superellipsoid.py` e le `probe_*.py`
sono con ogni probabilità specifiche; `slice_mesh.py`, `analyze_mesh.py`,
`render_views.py`, `segment_features.py` e `compare_model_mesh.py` dovrebbero
essere generiche o rese tali con poche modifiche.

## 4. FreeCAD headless: le regole non negoziabili del runner

Raccolte dal `BUILD-LOG` dell'utente. Il modulo `core/freecad/runner.py` le
incorpora così che non possano essere dimenticate da chi chiama:

1. **stdin chiuso.** `FreeCAD -c script.py` senza `< /dev/null` esegue lo script e poi
   resta appeso sulla console interattiva. Nel backend: `stdin=DEVNULL`, sempre.
2. **Timeout esplicito** su ogni invocazione, con kill del gruppo di processi.
   Un job che non esce non deve poter bloccare il worker.
3. `Shape.BoundBox` **mente** sulle superfici BSpline (restituisce l'inviluppo dei
   punti di controllo): usare `optimalBoundingBox()`. Stesso inganno su
   `Compound(edges).BoundBox` — per misurare edge BSpline vanno discretizzati.
4. L'**HLR di TechDraw** non genera la silhouette delle BSpline in alcune viste.
   Per la cupola si disegna sempre la curva analitica del paraboloide.
5. In headless **TechDraw calcola le quote ma non le disegna** (la grafica sta nel
   lato GUI). Per questo esiste `draft2d.py`, ed è la ragione per cui l'anteprima
   della tavola nel browser non richiede FreeCAD.
6. Simboli: nel PDF servono font in `WinAnsiEncoding`; nel DXF i codici `%%c`
   (diametro) e `%%d` (grado).

## 5. La regola non negoziabile, nella UI

> Nessuna quota inventata. Ogni numero che entra nel modello è (a) misurato dalla mesh
> da uno script in `tools/`, oppure (b) approvato esplicitamente dall'utente e
> registrato. Se manca un valore e non è approvato: fermarsi e chiedere, non stimare.

Traduzione in prodotto — `core/provenance/`:

* Ogni quota è un record: `{id, valore_misurato, valore_usato, origine, stato, nota}`.
* `origine` ∈ `{misurato:<script>, approvato:<utente,timestamp>, derivato:<formula>}`.
* `stato` ∈ `{concorde, divergente, mancante-non-approvato}`.
* Una build con anche **una** quota `mancante-non-approvato` **non parte**: il job
  fallisce con l'elenco delle quote da risolvere. Non esiste un default silenzioso.
* La tabella «misurato → usato» con le divergenze evidenziate è uno **step esplicito
  del flusso**, non un pannello avanzato da aprire.

Le 8 discrepanze catalogate (D1–D8) e le 7 ambiguità (A–G) diventano dati in
`parts/teiser/decisions.py`: testo della domanda, opzioni, decisione presa, quote
impattate. La UI le presenta come form, e la decisione dell'utente viene registrata
nella provenance. Quel passaggio è il cuore del prodotto.

**Tranello del dominio** (`docs/lost+found_design.md` §2.1): la tavola tecnica
TinkerCAD non è una fonte di verità, perché è generata dalla mesh stessa. Un
disegno caricato dall'utente entra nell'app come **riferimento visivo**, mai come
sorgente di quote, ed è etichettato come tale nell'interfaccia.

## 6. Flusso e job

| # | Step | Job | Durata attesa |
|---|---|---|---|
| 1 | Upload `model.obj` (+ `.mtl`, + tavola di riferimento opzionale) | — | — |
| 2 | Analisi → feature, render ortografici, sezioni | `analyze` | 10–30 s |
| 3 | Tabella misurato → usato + risoluzione ambiguità | sincrono | — |
| 4 | Build → STEP/STL/FCStd + mappa di scostamento | `build`, `compare` | ~6 s + confronto |
| 5 | Tavola → SVG in browser, impaginazione modificabile | `draw` | secondi |
| 6 | Download STEP/STL/PDF/DXF/SVG + report di verifica | — | — |

Ogni job: record su SQLite (`id`, `kind`, `stato`, `params_hash`, `started/ended`),
log append-only in streaming SSE, artefatti su disco in `runs/<run_id>/`.
Rilanciare con parametri modificati crea un **nuovo run** — i run precedenti
restano, così il confronto fra varianti è possibile e la provenance non viene
sovrascritta.

## 7. Deploy

Immagine Linux con FreeCAD da conda-forge (versione pinnata), `docker compose`
con un solo servizio + volume per `runs/`. L'immagine è grossa (FreeCAD + Qt);
lo smoke test di §4.1 gira nel build come `RUN`, così un'immagine che non riesce a
importare FreeCAD headless non viene mai prodotta.

## 8. Stato al termine della prima sessione

Fatto e verificato in esecuzione:

* `core/freecad/runner.py` — unico punto di ingresso a FreeCAD headless, con tutte
  le trappole incorporate (§4, più le tre nuove scoperte qui: argomenti, PYTHONPATH,
  codice di uscita — vedi `docs/BUILD-LOG-webapp.md`).
* `core/provenance/` — registro quote e decisioni, con il cancello sulla build.
* `webapp/backend` — API, coda job su SQLite, log SSE. Provati su HTTP reale.
* `webapp/frontend` — React + Vite + three.js: upload, schede delle decisioni,
  tabella misurato → usato, log in streaming, anteprima 3D con mappa di
  scostamento, anteprima SVG della tavola, download.
* `docker/` — immagine con FreeCAD 1.1.3 da conda-forge; smoke test nel build.
* 32 test verdi (30 + 2 skip senza FreeCAD).

Da fare, in ordine:

1. **Push del repo Teiser** (§0). Senza, il resto non può iniziare.
2. Ripartizione dei `tools/*.py` fra `core/mesh/` e `parts/teiser/` (§3).
3. `cad/draft2d.py` → `core/drafting/`, invariato: è verificato, non va riscritto.
4. `cad/compare_model_mesh.py` → `core/compare/`, con l'aggiunta del valore per
   vertice per la mappa di scostamento.
5. Cablaggio di `parts/teiser/` nell'ordine documentato in `parts/teiser/plugin.py`.
   Le D1–D8 e le A–G vanno **trascritte** da `docs/lost+found_design.md`, con la
   decisione già presa dall'utente come scelta di partenza.
6. Merge di `docs/BUILD-LOG-webapp.md` dentro `docs/BUILD-LOG.md`, e aggiornamento
   di `STATE.md` e `docs/CONVENTIONS.md`.
7. Build reale dell'immagine Docker (nel container di sviluppo non c'era un demone
   Docker: FreeCAD è stato verificato installando conda-forge direttamente, che è
   la stessa cosa che fa il Dockerfile, ma il `docker build` non è ancora stato
   eseguito).

## 9. Rischi aperti

* ~~**Versione FreeCAD.**~~ Risolto: conda-forge serve esattamente `freecad 1.1.3`,
  la stessa minor del Mac. Pinnata nel Dockerfile.
* **Peso dell'immagine** (~1–2 GB): irrilevante in locale, da rivedere se si passa a
  un PaaS.
* **Riconciliazione col codice reale**: tutti i `[DA VERIFICARE]` sopra.
