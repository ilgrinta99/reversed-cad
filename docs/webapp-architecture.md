# Teiser Web App — architettura

Stato: **in piedi e verificato end-to-end** sul contenitore TAISER. La prima stesura
è precedente all'arrivo del codice della pipeline nel repo; le assunzioni che
conteneva sono state confrontate col codice reale e questo documento le riflette.

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

### 3.1 Come è andata a finire, col codice vero in mano

I `tools/*.py` non sono stati spostati né riscritti. Si è rivelata migliore una
strada meno invasiva: restano dove sono, e `parts/teiser/plugin.py` li lancia
puntandoli sulla cartella del run tramite `TAISER_MESH`, `TAISER_PARAMS`,
`TAISER_OUT`, `TAISER_REPORT` (docs/CONVENTIONS.md). Da riga di comando si
comportano esattamente come prima — verificato.

La ripartizione «generico contro specifico» è quindi passata dai file alle
interfacce:

* in `core/` è finito ciò che serviva davvero a tutti: il runner FreeCAD, il
  registro delle quote, il formato del confronto, il caricamento OBJ;
* `parts/teiser/` porta lo `schema.py` (46 quote mappate sui percorsi di
  params.json), le `decisions.py` (A–G e D1–D8 trascritte) e il cablaggio.

`cad/draft2d.py` non è stato toccato: `make_drawing.py` lo usa com'è, e l'SVG che
produce è quello che il browser mostra. Nessun FreeCAD nel percorso di anteprima,
come previsto.

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
  Lo schema di `params.json` portava già questa distinzione per convenzione — le
  chiavi con l'underscore iniziale (`_t_x_misurato`, `_L_mesh`, `_misurato_ellittico`)
  sono la misura, il valore accanto è quello che entra nel modello. `schema.py` la
  rende esplicita e verificabile invece che implicita.
* `origine` ∈ `{misurato:<script>, approvato:<utente,timestamp>, derivato:<formula>}`.
* `stato` ∈ `{concorde, divergente, mancante-non-approvato}`.
* Una build con anche **una** quota `mancante-non-approvato` **non parte**: il job
  fallisce con l'elenco delle quote da risolvere. Non esiste un default silenzioso.
* La tabella «misurato → usato» con le divergenze evidenziate è uno **step esplicito
  del flusso**, non un pannello avanzato da aprire.

Le 8 discrepanze catalogate (D1–D8) e le 7 ambiguità (A–G) sono dati in
`parts/teiser/decisions.py`: testo della domanda, evidenza, opzioni, decisione presa,
quote impattate — trascritte da `docs/lost+found_design.md`, non riassunte. La UI le
presenta come schede, e la decisione dell'utente viene registrata nella provenance.
Quel passaggio è il cuore del prodotto.

Le A–G risultano **già risolte**, con la risposta del committente del 2026-08-19 e la
citazione del documento: non è un default nascosto, è un fatto registrato, e resta
modificabile. Cambiarne una riscrive le quote che governa.

Cablando lo schema è emersa una scelta che nessuna lettera copriva: gli
arrotondamenti proposti in §3.1 del briefing (26.999 → 27.0, fondo 1.634 → 1.6,
cavità, e il centro della cupola portato a 0 per simmetria). Compare come **S1**, con
lo stesso standing della decisione A: «default proposto nel briefing, non contestato».
Senza il registro sarebbe rimasta invisibile — è esattamente ciò per cui il registro
esiste.

Un'opzione può dire «usa la misura» senza portare numeri (`accept_measured`): il
valore non è noto prima di misurare, e inventarlo nel catalogo delle decisioni
sarebbe la stessa violazione che il progetto vieta.

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
  codice di uscita — vedi `docs/BUILD-LOG.md`, FASE 6).
* `core/provenance/` — registro quote e decisioni, con il cancello sulla build.
* `webapp/backend` — API, coda job su SQLite, log SSE. Provati su HTTP reale.
* `webapp/frontend` — React + Vite + three.js: upload, schede delle decisioni,
  tabella misurato → usato, log in streaming, anteprima 3D con mappa di
  scostamento, anteprima SVG della tavola, download.
* `docker/` — immagine con FreeCAD 1.1.3 da conda-forge; smoke test nel build.
* `parts/teiser/` — cablaggio completo: 46 quote, 16 schede di decisione, i quattro
  step che lanciano gli script esistenti.
* 44 test verdi.

Verificato girando davvero, su Linux con FreeCAD conda-forge:

* `extract_params.py` riproduce il `cad/params.json` committato (scarto 0.0001 mm su
  un punto, versione diversa di numpy);
* il confronto modello ↔ mesh dà **le stesse identiche cifre** di §8 di
  `lost+found_design.md`, macOS e Linux;
* pipeline completa dal browser su una mesh caricata: analisi 10 s, build 6 s,
  tavola 2 s, confronto 10 s.

Da fare, in ordine:

1. `docker build` vero: FreeCAD conda-forge è stato verificato installandolo
   direttamente — è quel che fa il Dockerfile — ma nel container di sviluppo non
   c'era un demone Docker.
2. Ripulitura dei run: 47 MB ciascuno, di cui 44 di STL a tassellazione fine.
3. Impaginazione della tavola modificabile dal browser: oggi i tre fogli si
   sfogliano, non si ricompongono.
4. Un secondo pezzo della famiglia, per mettere alla prova il confine di §3.

## 9. Rischi aperti

* ~~**Versione FreeCAD.**~~ Risolto: conda-forge serve esattamente `freecad 1.1.3`,
  la stessa minor del Mac. Pinnata nel Dockerfile.
* **Peso dell'immagine** (~1–2 GB): irrilevante in locale, da rivedere se si passa a
  un PaaS.
* ~~**Riconciliazione col codice reale.**~~ Fatta: vedi §3.1 e §8.
* **Il registro copre 46 quote su ~150 numeri di params.json.** Le altre restano
  quelle che gli script misurano — la regola vale anche per loro — ma non hanno una
  riga in tabella. È una scelta di leggibilità, non una scappatoia: in tabella
  stanno le quote su cui misura e uso *possono* divergere. Se un domani il
  costruttore introducesse un valore non misurato fuori da quell'elenco, il registro
  non se ne accorgerebbe.
