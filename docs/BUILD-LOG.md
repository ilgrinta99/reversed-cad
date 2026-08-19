# Build log

## 2026-08-19 — FASE 1: briefing

- Creato scheletro progetto, `git init`, venv con numpy.
- Copiati i sorgenti da `~/Downloads/CONTENIT TAISER P/` in `input/`
  (`tinker.obj` → `model.obj`, `obj.mtl` → `model.mtl`). Originali intatti.
- Scritti 4 tool di analisi: `analyze_mesh.py` (bbox + clustering piani),
  `segment_features.py` (segmentazione in patch + classificazione piano/cilindro),
  `slice_mesh.py` (sezioni piane → polilinee semplificate Douglas-Peucker),
  `render_views.py` (render ortografici z-buffer → PNG).
- **Risultato chiave**: le 6 quote della tavola TinkerCAD coincidono al millesimo con il bounding box
  della mesh. La tavola è generata dalla mesh, non è una fonte indipendente.
- Catalogate 8 discrepanze (D1–D8) e 7 ambiguità bloccanti (A–G) in `docs/lost+found_design.md`.
- Avviata installazione FreeCAD (`brew install --cask freecad`).

### Correzioni in corso d'opera
- Primo render aveva l'inquadratura calcolata su tutti i vertici invece che sui soli vertici
  dell'oggetto: corretto usando `np.unique(T)`.
- La classificazione aveva restituito «coperchio con fondo bombato R 81.44 mm» (fit cilindro con
  rms 0.59, quindi scadente). La sezione X = −9 ha smentito: **il fondo del coperchio è piano a Z = 0**,
  l'apparente bombatura era il patch di raccordo perimetrale fuso con il fondo.

## 2026-08-19 — FASE 2 (parziale): ambiente

- **FreeCAD 1.1.3** installato via `brew install --cask freecad`.
- Su macOS il binario `FreeCADCmd` non esiste più: la modalità headless è
  `/Applications/FreeCAD.app/Contents/MacOS/FreeCAD -c script.py`.
- Verificati importabili in console: `Part`, `Import` (STEP), `importDXF`, `Mesh`, `TechDraw`.
- All'avvio compare un errore innocuo su `3DconnexionNavlib` (driver SpaceMouse assente): ignorabile.

## 2026-08-19 — FASE 3: costruzione parametrica

- `tools/extract_params.py` misura la mesh e scrive `cad/params.json`; `cad/build_model.py` legge
  solo quel file. Nessuna quota è scritta a mano nel costruttore.
- **Trappola FreeCAD headless**: `FreeCAD -c script.py` esegue lo script e poi resta appeso sulla
  console interattiva. Serve `< /dev/null`. Il primo build sembrava impiegare 15+ minuti; la
  profilazione ha mostrato che ogni singolo passo costa ~0.01 s — era solo il processo che non usciva.
- **Seconda trappola**: `Shape.BoundBox` su superfici BSpline restituisce l'inviluppo dei punti di
  controllo. La cupola dava una bbox 80 × 60.2 × 32.6 su un pezzo che è 80 × 46 × 27. La geometria
  era corretta (volume 1374.24 contro il valore analitico π·a·b·c/2 = 1372.59): sbagliata era la
  misura. Va usato `optimalBoundingBox()`, che tassella.

## 2026-08-19 — FASE 5: verifica e correzioni

`tools/compare_model_mesh.py` calcola la distanza esatta punto-superficie fra i vertici della mesh
e il solido. Tre giri di correzione, ognuno guidato dai vertici peggiori:

1. Errori di 0.69 mm su un gruppo di vertici a x = −36.93 → **rilievo asolato non modellato** dentro
   la tasca sulla faccia X−. Un render ravvicinato più il conteggio dei vertici per piano X
   (111 a −36.93 e 111 a −36.24, nessuno in mezzo) ha stabilito che è un rilievo e non un foro passante.
2. Errori di 0.45 mm sulle colonnine → **le 4 colonnine non sono uguali**. Sezioni in pianta a
   Z = 25.5 / 22 / 20 hanno mostrato che quella (x<0, y<0) esiste solo da z = 24.002 in su.
   Il 4° piano di smusso che avevo ricostruito per simmetria era un'invenzione: rimosso, con un
   `assert len(cham) == 3` a presidio.
3. Errori di 0.68 mm sul fondo della tasca del coperchio → **le tasche annidate sono ellissi**,
   non rettangoli (fit d'angolo R 2.400 su una tasca 4.630 × 4.951 = raggio medio dell'ellisse).

Il rilievo era stato dapprima misurato come *due* asole separate (7.918 e un frammento): erano un
artefatto del concatenamento dei segmenti di sezione. Il conteggio dei vertici della faccia,
separati sul salto in Y, dà **una sola asola** con teste a y′ −12.890 e −6.433, R ≈ 1.50.

Esito finale: scatola mediana 0.015 / p90 0.056 mm, coperchio mediana 0.013 / p90 0.127 mm.
Tutti i residui oltre 0.5 mm sono il solo raccordo di base (decisione A).

## 2026-08-19 — FASE 4: tavola tecnica

- TechDraw funziona headless e fornisce la **geometria proiettata** (`TechDraw.project`), ma la
  grafica delle quote sta nel lato GUI: in console `DrawViewDimension` calcola il valore e non
  disegna nulla. Le viste sono quindi TechDraw; cornice, cartiglio, quote, campiture e
  impaginazione sono di `cad/draft2d.py` (motore 2D scritto qui, tre backend: SVG, PDF, DXF,
  senza dipendenze esterne).
- **L'HLR di TechDraw non genera la silhouette** della superficie BSpline della cupola in alcune
  viste: con revolve+transformGeometry manca in pianta, con makeLoft manca in prospetto.
  Dove la genera è però accuratissimo (errore 0.017 mm). Correzione di una diagnosi sbagliata fatta
  in corso d'opera: avevo concluso «HLR impreciso» misurando con `BoundBox` su edge BSpline —
  di nuovo l'inviluppo dei punti di controllo. Discretizzando, l'errore è 0.017 mm.
  Soluzione: si disegna **sempre** la silhouette analitica del paraboloide; dove l'HLR ce l'ha già,
  le due curve coincidono entro 0.02 mm e non si nota.
- Le curve analitiche fanno doppio servizio: in sezione A-A e C-C il contorno della cupola *è*
  esattamente la traccia del piano di sezione sul paraboloide.
- DXF: i tre fogli erano sovrapposti nello stesso modelspace (tutti con coordinate 0..420).
  Ora sono affiancati con 20 mm di margine. Verificato con `ezdxf`: 5338 entità, 8 layer.
- Simbolo di diametro e grado: nel PDF servono i font in `WinAnsiEncoding`, nel DXF i codici
  di controllo `%%c` e `%%d`.

## 2026-08-19 — FASE 6: web app

Runner web della stessa pipeline: gli script di `tools/` e `cad/` non sono stati
riscritti, sono stati resi puntabili su una cartella di run tramite le variabili
d'ambiente di `docs/CONVENTIONS.md`. Da riga di comando si comportano come prima.

Verificato in questo container Linux: `extract_params.py` riproduce il params.json
committato (scarto 0.0001 mm su un punto, dovuto a una versione diversa di numpy),
`build_model.py` gira in **5.9 s** — gli stessi ~6 s del Mac — e il confronto
modello ↔ mesh dà **esattamente** le cifre di lost+found_design.md §8:
scatola 0.0252 / 0.0150 / 0.0558 / 0.1395 / 0.6213, coperchio 0.0467 / 0.0131 /
0.1269 / 0.6002 / 0.6213. FreeCAD 1.1.3 da conda-forge su Linux dà lo stesso
risultato del cask su macOS.

## FreeCAD da conda-forge in Linux: funziona, e con la stessa minor del Mac

    micromamba create -p ./fcenv -c conda-forge python=3.11 freecad numpy

Risolve `freecad 1.1.3 py311h1922e53_0`, `occt 7.9.3`, `numpy 2.4.6`. È **la stessa
1.1.3** installata via Homebrew cask sul Mac, quindi la divergenza di minor fra
locale e container — la causa più probabile di «funziona sul Mac, non nel
container» — non si presenta. `import FreeCAD`, `Part`, `TechDraw` funzionano
headless con `QT_QPA_PLATFORM=offscreen`; export STEP e STL ok.

Il binario si chiama `freecad` (esiste anche `freecadcmd`). Uno script completo
gira in **~0.3 s** dall'avvio del processo alla fine: conferma dall'altra parte
che i 15 minuti del primo build erano solo il processo che non usciva.

Smoke test in `docker/freecad_smoke.py`, eseguito dentro il build dell'immagine:
un'immagine che non sa eseguire FreeCAD headless non viene prodotta.

## Trappola confermata: BoundBox mente sulle BSpline

Riprodotta nello smoke test con una BSpline interpolata su 4 punti:

    BoundBox naive YLen = 68.356    optimalBoundingBox() YLen = 62.010

Oltre 6 mm di differenza su una curva di 30 mm di corda. `optimalBoundingBox()`
sempre.

## Trappola nuova: gli argomenti NON passano da `sys.argv`

`FreeCAD -c script.py params.json out_dir` **non** è come lanciare python.

1. `sys.argv` contiene anche il binario e `-c`, quindi `sys.argv[1]` vale `'-c'`;
2. peggio: FreeCAD tratta gli argomenti posizionali come **file da aprire**. Un
   `params.json` finisce nell'importatore di mesh FEM (`importYamlJsonMesh.py`) e
   produce un traceback lungo e fuorviante:
   `<class 'AttributeError'>: 'float' object has no attribute 'items'`.

`--` non aiuta: viene passato pari pari. Soluzione adottata: gli argomenti
viaggiano **nell'ambiente**, in `TEISER_ARGS` come JSON, e lo script li rilegge con
`core.freecad.script.args()`. Le variabili d'ambiente arrivano intatte.

## Trappola nuova: FreeCAD azzera PYTHONPATH

Dentro lo script, `os.environ["PYTHONPATH"]` è **vuota** e la radice del repo non è
su `sys.path`: `import core...` fallisce con `No module named 'core'` anche
esportando PYTHONPATH nel processo padre. FreeCAD ricostruisce `sys.path` per conto
suo (ci mette i propri `Mod/*`).

Soluzione: il runner passa la radice in `TEISER_REPO_ROOT`, e ogni script inizia con

    import os, sys
    sys.path.insert(0, os.environ["TEISER_REPO_ROOT"])

## Trappola nuova: il codice di uscita mente

Un'eccezione non catturata nello script fa uscire FreeCAD con **rc = 0**. Un job
risulterebbe riuscito senza aver prodotto nulla — ed è successo, durante lo
sviluppo, prima di accorgersene. (`sys.exit(n)`, invece, propaga correttamente.)

Soluzione: ogni script termina con `core.freecad.script.done()`, che stampa
`TEISER_OK`; `run_script()` pretende quella riga e altrimenti solleva.

## Trappola nel runner, non in FreeCAD: il timeout va messo su un watchdog

Primo tentativo: controllare la scadenza dentro il ciclo che legge stdout. Non
funziona — `readline` blocca, e uno script appeso che smette di stampare non fa mai
un altro giro. È esattamente il caso della console interattiva, cioè il caso da
prevenire.

Soluzione: `threading.Timer` che uccide il gruppo di processi
(`start_new_session=True` + `os.killpg`). Verificato: timeout a 5.0 s esatti su uno
script che dorme 600 s, nessun processo orfano.

## Uscita pulita: `stdin=DEVNULL`

Il `< /dev/null` della riga di comando, nel backend, è `stdin=subprocess.DEVNULL`.
Confermato: senza, il processo resta sul prompt `>>>`; con, esce da solo.

---

## Note non-FreeCAD

* **SSE dietro proxy.** Lo stream dei log va servito con `Cache-Control: no-cache` e
  `X-Accel-Buffering: no`, altrimenti un reverse proxy accumula e le righe arrivano
  a blocchi a job finito. Il dev server di Vite inoltra `/api` al backend, così in
  sviluppo non c'è CORS di mezzo.
* **SQLite in WAL.** I job girano su thread, il lettore SSE sta sull'event loop:
  senza `journal_mode=WAL` il lettore blocca lo scrittore. Connessione per-thread,
  `busy_timeout=30000`.
* **Riproduci-poi-segui.** Lo stream riproduce prima i log già scritti e poi segue i
  nuovi: chi apre la pagina a job avviato non perde le righe iniziali.
* **Mappa di scostamento e ordine dei vertici.** I valori per-vertice sono
  indicizzati sull'ordine di lettura dell'OBJ. Un loader three.js generico
  riordina e duplica i vertici: la corrispondenza salterebbe. Il frontend rilegge
  quindi i `v` dell'OBJ nello stesso ordine del backend.


## FASE 6 — trappole trovate cablando la web app

### `preview.stl`: gli STL di consegna sono inservibili in una pagina web

`build_model.py` esporta a tassellazione fine: `model.stl` pesa **23 MB**, l'intero
run 47 MB. Per l'anteprima 3D serve una versione grossolana, quindi
`parts/teiser/preview_script.py` riapre il documento e ri-tassella a 0.25 mm:
34 044 triangoli, **1.6 MB**, indistinguibile a schermo. Gli STL di consegna non
vengono toccati.

### La mappa di scostamento non può indicizzare i vertici del file

Primo tentativo: un valore per vertice, allineato all'ordine di lettura dell'OBJ.
Fragile — un loader 3D riordina e duplica i vertici. Il formato comune
(`core/compare/deviation.py`) porta quindi le coordinate dentro ogni punto:
`[x, y, z, scostamento]`, nel riferimento dell'assieme. `compare_model_mesh.py`
scrive quel JSON quando `TAISER_REPORT` è impostata, e continua a stampare il
report a schermo come prima.
