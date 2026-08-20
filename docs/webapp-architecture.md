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

Il percorso normale non chiede quale pezzo si stia caricando: **la mesh è l'unica
specifica**. `parts/auto/` la misura così com'è, ne ricava le quote che esistono
davvero in quel file e le domande che quella geometria solleva. Due mesh diverse
danno due tabelle diverse e due elenchi di ambiguità diversi — vedi §3.2.

Le pipeline scritte su misura per un pezzo noto restano: `parts/teiser/` esegue
gli script già verificati del contenitore TAISER (cupola paraboloidica, 4
colonnine di cui una diversa, asole, tasche ellittiche) e si raggiunge indicandone
l'id all'API. Non è più il percorso predefinito.

## 2. Stack (confermato)

| Livello | Scelta |
|---|---|
| Backend | FastAPI (Python) |
| Coda job | in-process (worker pool asyncio/thread), stato e log su **SQLite** |
| Log live | SSE (`text/event-stream`) |
| Frontend | React + Vite, three.js per anteprima STL e mappa di scostamento |
| Tavola in browser | SVG prodotto da `core/drafting/` — FreeCAD proietta, l'impaginazione è Python puro |
| Packaging | Docker, FreeCAD da **conda-forge** in immagine Linux |
| Hosting | locale (docker compose) per ora; l'immagine resta deployabile altrove |

Motivo della coda in-process: lo scenario è mono-utente / piccolo team, i job durano
secondi–decine di secondi, e un solo container evita di trascinarsi Redis + worker
separato. Il confine `JobQueue` è comunque un'interfaccia: passare a RQ/Celery in
seguito non tocca gli endpoint.

## 3. Il confine che decide se il progetto scala

```
core/                     GENERICO — nessuna conoscenza del pezzo
  mesh/                   caricamento OBJ, segmentazione in corpi e patch,
                          riconoscimento delle primitive, sezioni piane,
                          analisi ad hoc e rilevamento delle ambiguità
  drafting/               motore di disegno: sheet.py (primitive 2D + backend
                          SVG/PDF/DXF), layout.py (cornice, cartiglio, scale
                          normalizzate, primo diedro), tavola.py (compositore),
                          hlr.py + project_script.py (proiezione TechDraw)
  compare/                distanza punto-superficie modello ↔ mesh
  provenance/             registro delle quote: misurato / usato / origine / approvazione
  freecad/                runner headless (§4)

parts/
  auto/                   NESSUN PEZZO — misura la mesh e la ricostruisce
                          con un repertorio dichiarato: prisma, raccordo,
                          cavità, fori
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

Il motore di disegno è poi passato da `cad/draft2d.py` a `core/drafting/`, che è
il posto che la regola di collocazione gli assegnava da sempre: non contiene un
solo numero del TAISER. `cad/draft2d.py` resta come guscio, così i comandi
documentati continuano a funzionare. `make_drawing.py` disegna gli stessi fogli di
prima e ne aggiunge un quarto, l'assonometria.

### 3.2 Analisi ad hoc: le quote e le domande vengono dalla mesh

Il difetto della prima versione non era architetturale, era di prodotto: si
sceglieva il pezzo da un menu *prima* di caricare il file, e da quella scelta
discendevano l'elenco delle quote e il catalogo delle ambiguità. Su una mesh
qualsiasi quel catalogo era semplicemente sbagliato — erano le ambiguità di un
altro pezzo.

Oggi il caricamento accetta un OBJ e nient'altro, e la lettura avviene in tre
passaggi, tutti in `core/mesh/`:

| Modulo | Cosa risponde |
|---|---|
| `patches.py` | di quanti corpi è fatta la mesh, e di quali superfici ogni corpo (piano, cilindro, sfera, libera) |
| `analysis.py` | quali quote quelle superfici *dimostrano*: ingombri, facce esterne, spessori di parete, cavità, arrotondamenti degli spigoli, fori e asole, simmetria, datum |
| `ambiguity.py` | dove la misura non è conclusiva, e con quali opzioni numeriche |
| `sections.py` | sezioni piane, aree dei contorni, fit di cerchi — il supporto alle prime due |

Due criteri reggono tutto il resto:

* **una quota misurata entra nel modello con il valore misurato.** Usare la
  misura non è mai un'invenzione, ed è il motivo per cui una mesh senza ambiguità
  arriva alla build senza chiedere niente all'utente;
* **una quota che non esiste come misura scalare resta vuota, e blocca.** Il caso
  tipico è il raccordo non circolare: lo spigolo è arretrato di due quantità
  diverse sui due lati, quindi *un* raggio non è misurabile. Va scelto, e la
  scelta è un'approvazione registrata.

Le famiglie di ambiguità che l'analizzatore riconosce — raccordo non circolare,
pareti asimmetriche, superfici non riconducibili a una primitiva, archi parziali,
asole, corpi multipli, datum arbitrario, arrotondamento congruente — sono le
stesse che l'analista umano aveva catalogato a mano come A–G in
`docs/lost+found_design.md`. La differenza è che ora le trova un algoritmo, su
qualunque mesh, e le trova con i numeri di *quella* mesh.

**Verifica sul pezzo vero.** Su `input/model.obj`, senza una riga di codice che
sappia cosa sia un TAISER, l'analisi ritrova gli spessori di parete 1.293 e 2.188
mm (§5-B del briefing), il fondo a 1.634 mm (§3.1), gli ingombri 80 × 46 × 26.999
e 74 × 46 × 2.5, le quattro colonnine come corpi separati di cui una diversa, e
solleva sei ambiguità fra cui la cupola come superficie non ricostruibile.
`tests/test_mesh_analysis.py` lo verifica.

**Il ricostruttore dichiara i propri limiti.** `parts/auto/build_script.py` sa
fare prisma, raccordo verticale, cavità e fori cilindrici. Quello che non sa fare
non lo approssima: l'analisi lo elenca fra le feature non ricostruibili, la UI lo
mostra come decisione («costruisci senza, lo scostamento resterà misurato» /
«fermati»), e il confronto modello ↔ mesh misura quanto è costata la
semplificazione. Una superficie libera approssimata in silenzio con una primitiva
sarebbe una quota inventata: è la stessa regola, applicata alle forme.

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
   lato GUI). Per questo esiste `core/drafting/sheet.py`, ed è la ragione per cui
   ricomporre una tavola già proiettata non richiede FreeCAD.
5b. `TechDraw.project` restituisce **quattro** gruppi di spigoli, in quest'ordine:
   vivi in vista, di tangenza in vista, vivi nascosti, di tangenza nascosti. Il
   quarto era finito fra i visibili, e disegnava come spigoli pieni le tangenti
   nascoste della cupola: due lunghe diagonali sulla pianta. Verificabile su un
   cubo e un cilindro, dove i gruppi 1 e 3 restano vuoti.
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
* Le schede di decisione compaiono **dopo** l'analisi, perché prima non esistono:
  non sono un catalogo scritto in anticipo, sono il risultato della misura. Se la
  mesh non solleva ambiguità, il pannello lo dice e il flusso prosegue.

Le 8 discrepanze catalogate (D1–D8) e le 7 ambiguità (A–G) sono dati in
`parts/teiser/decisions.py`: testo della domanda, evidenza, opzioni, decisione presa,
quote impattate — trascritte da `docs/lost+found_design.md`, non riassunte. La UI le
presenta come schede, e la decisione dell'utente viene registrata nella provenance.
Quel passaggio è il cuore del prodotto.

Le A–G risultano **già risolte** *nella pipeline `parts/teiser/`*, con la risposta
del committente del 2026-08-19 e la citazione del documento: non è un default
nascosto, è un fatto registrato, e resta modificabile. Cambiarne una riscrive le
quote che governa. Sul percorso `auto` non vale nulla di tutto questo: lì le
domande nascono dalla mesh caricata e nessuna arriva già risposta.

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
| 1 | Upload `model.obj` (+ `.mtl`, + tavola di riferimento opzionale). Nessun pezzo da scegliere | — | — |
| 2 | Analisi → corpi, patch, quote e ambiguità di *questa* mesh | `analyze` | < 1 s – 30 s |
| 3 | Ambiguità rilevate: una scheda per ciascuna, o «nessuna ambiguità» | sincrono | — |
| 3b | Tabella misurato → usato | sincrono | — |
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

Aggiunto per un link di prova pubblico: il Dockerfile costruisce ora anche il
frontend (stage Node separato, `dist/` copiato nell'immagine finale — prima
mancava, e l'immagine sarebbe partita senza interfaccia) e copia `tools/` e
`cad/`, che `parts/teiser/plugin.py` invoca via subprocess e che l'immagine non
portava. `render.yaml` in radice descrive un servizio Render a piano gratuito;
il bottone "Deploy to Render" è in README. Non ancora provato un deploy reale —
manca l'accesso a un account Render da questa sessione — quindi resta da
verificare sul campo, non solo per lettura del Dockerfile.

Da fare, in ordine:

1. **Primo deploy reale su Render**, per verificare che il fix del Dockerfile
   basti: build dell'immagine entro i tempi del piano gratuito, avvio entro i
   512 MB di RAM, smoke test FreeCAD nel build.
2. `docker build` locale, se mai disponibile un demone Docker: finora FreeCAD è
   stato verificato installando conda-forge direttamente, che è ciò che fa il
   Dockerfile ma non è la stessa prova.
3. Ripulitura dei run: 47 MB ciascuno, di cui 44 di STL a tassellazione fine. Su
   un piano gratuito senza disco persistente il problema è mitigato dal riavvio
   periodico, ma non risolto.
4. Impaginazione della tavola modificabile dal browser: oggi i tre fogli si
   sfogliano, non si ricompongono.
5. Un secondo pezzo della famiglia, per mettere alla prova il confine di §3.

## 9. Rischi aperti

* ~~**Versione FreeCAD.**~~ Risolto: conda-forge serve esattamente `freecad 1.1.3`,
  la stessa minor del Mac. Pinnata nel Dockerfile.
* **Peso dell'immagine** (~1–2 GB): irrilevante in locale, da rivedere se si passa a
  un PaaS.
* ~~**Riconciliazione col codice reale.**~~ Fatta: vedi §3.1 e §8.
* **Il ricostruttore automatico è elementare.** Prisma, raccordo verticale,
  cavità, fori: su una mesh con superfici libere il solido è una semplificazione.
  Il rischio non è che la semplificazione esista — è dichiarata e misurata dal
  confronto — ma che qualcuno la scambi per il modello finito. La UI la mostra
  come decisione, non come nota a piè di pagina.
* **Il fit delle primitive ha tolleranze di lettura, e sono numeri.** `patches.py`
  rifiuta un cilindro se l'errore supera il 2 % del raggio o 0.10 mm assoluti (la
  tolleranza del progetto sulle feature piane); `analysis.py` chiede a una faccia
  esterna almeno il 5 % della sezione del corpo. Sono soglie di lettura, non quote
  del pezzo, e stanno in cima ai rispettivi moduli con la ragione accanto. Una
  mesh molto più grossolana o molto più fine di quelle provate può richiedere di
  rivederle: sarebbe un cambio di taratura, e va fatto lì.
* **Il registro copre 46 quote su ~150 numeri di params.json** *nella pipeline
  `parts/teiser/`*. Le altre restano
  quelle che gli script misurano — la regola vale anche per loro — ma non hanno una
  riga in tabella. È una scelta di leggibilità, non una scappatoia: in tabella
  stanno le quote su cui misura e uso *possono* divergere. Se un domani il
  costruttore introducesse un valore non misurato fuori da quell'elenco, il registro
  non se ne accorgerebbe.
