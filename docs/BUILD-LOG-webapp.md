# BUILD-LOG — parte web app

Addendum a `docs/BUILD-LOG.md`. **Da fondere nel BUILD-LOG principale** appena il
repo Teiser sarà stato pushato (vedi `docs/webapp-architecture.md` §0): tenerlo
separato serve solo a non creare un conflitto su un file che qui non esiste ancora.

Tutto quel che segue è stato verificato in esecuzione, non dedotto.

---

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
