# Prompt per la sessione successiva — trasformare Teiser in una web app

> Copia tutto il blocco qui sotto come primo messaggio della nuova sessione.

---

Progetto **Teiser**: `/Users/macmini003/Documents/doc/develop/Teiser` (repo git, branch `master`,
3 commit, nessun remote configurato).

Oggi è una **pipeline da riga di comando** che fa reverse engineering CAD: prende una mesh OBJ
esportata da Tinkercad e produce un modello parametrico STEP più una tavola tecnica quotata in
PDF/DXF. Voglio trasformarla in una **web app con interfaccia grafica, ospitata su git**, in cui
l'utente carica i file di partenza e segue tutto dal browser.

## Leggi prima di toccare qualsiasi cosa

1. `STATE.md` — dove siamo e cosa resta aperto
2. `docs/lost+found_design.md` — quote, discrepanze D1–D8, decisioni A–G, verifica finale
3. `docs/BUILD-LOG.md` — **le trappole tecniche, elencate sotto: leggile, mi sono costate ore**
4. `LORE.md` — perché la geometria è "sporca"
5. `docs/CONVENTIONS.md` — unità, datum, regole sul codice
6. `CLAUDE.md` — la regola non negoziabile

## Cosa esiste già (1900 righe di Python, tutto funzionante e verificato)

```
tools/extract_params.py      misura la mesh OBJ  ->  cad/params.json
tools/segment_features.py    segmenta la mesh in patch e le classifica (piano/cilindro)
tools/slice_mesh.py          sezioni piane -> polilinee (Douglas-Peucker)
tools/analyze_mesh.py        bbox + clustering dei piani
tools/render_views.py        render ortografici z-buffer -> PNG (numpy puro, niente OpenGL)
tools/fit_superellipsoid.py  fitting della cupola e rilievo delle asole
tools/probe_*.py             sonde mirate (fori, dettagli, cupola)
tools/compare_model_mesh.py  distanza esatta punto-superficie modello <-> mesh

cad/params.json              TUTTE le quote, misurate. Unica fonte del costruttore.
cad/build_model.py           costruisce i solidi -> STEP, STL, FCStd   (~6 s)
cad/make_drawing.py          tavola A3 in 3 fogli -> PDF, DXF, SVG
cad/draft2d.py               motore di disegno 2D: primitive + backend SVG/PDF/DXF,
                             SCRITTO A MANO, ZERO DIPENDENZE ESTERNE, NON usa FreeCAD
```

Ambiente attuale: Python 3.13 in `.venv/` (numpy, ezdxf), FreeCAD 1.1.3 installato via Homebrew
cask e usato headless. Ogni step costa 5–20 s.

Risultato raggiunto: scostamento modello ↔ mesh con mediana **0.015 mm** (scatola) e **0.013 mm**
(coperchio); ingombri identici alla tavola di riferimento.

## Scopo: deciso, non da rinegoziare

Il codice attuale è **specifico per questo pezzo**: `cad/params.json` ha uno schema modellato sul
contenitore TAISER (cupola paraboloidica, 4 colonnine di cui una diversa, asole, tasche ellittiche),
e `build_model.py` costruisce esattamente quelle feature.

**Voglio un runner web di questa pipeline.** L'utente carica un OBJ, l'app esegue analisi →
parametri → modello → tavola e restituisce gli output, con la possibilità di modificare i parametri
da form e rilanciare. Riusa tutto quello che c'è, e va bene che funzioni sui pezzi di questa
famiglia: **non** voglio ora uno strumento generico di reverse engineering con riconoscimento
automatico delle feature su una mesh qualsiasi. Quello semmai verrà dopo, su queste fondamenta.

Corollario pratico: quando una feature del pezzo non è generalizzabile, **non fermarti a chiedere se
generalizzarla** — lasciala specifica, ma isolala dietro un confine chiaro (vedi «Cosa mi aspetto»).

Restano da chiedermi solo stack e hosting. La mia preferenza di default, da confermare, è
FastAPI + coda di job + frontend React/Vite con three.js per l'anteprima 3D, tutto in un
monorepo, deploy via Docker. E chiedimi se il repo deve andare su GitHub (oggi non c'è remote).

## Vincoli tecnici veri, già verificati

- **`FreeCAD -c script.py` va invocato con `< /dev/null`.** Altrimenti esegue lo script e resta
  appeso sulla console interattiva. Il primo build sembrava impiegare 15 minuti: in realtà ogni
  passo costa 0.01 s, era solo il processo che non usciva. In un backend web questo significa
  **stdin chiuso e timeout espliciti**.
- **FreeCAD è una dipendenza nativa pesante.** Sul mio Mac è in `/Applications/FreeCAD.app/Contents/MacOS/FreeCAD`
  (il binario `FreeCADCmd` su macOS non esiste più). Per il deploy serve un'immagine Linux con
  FreeCAD (AppImage, conda-forge o pacchetto distro): va deciso e provato presto, non alla fine.
- **`Shape.BoundBox` mente sulle superfici BSpline**: restituisce l'inviluppo dei punti di
  controllo. Usare sempre `optimalBoundingBox()`. Stesso inganno vale su `Compound(edges).BoundBox`:
  per misurare edge BSpline bisogna discretizzarli.
- **L'HLR di TechDraw non genera la silhouette** delle superfici BSpline in alcune viste (dove la
  genera è accurata a 0.017 mm). Per la cupola si disegna sempre la curva analitica del paraboloide.
- **In headless TechDraw calcola i valori delle quote ma non le disegna** (la grafica sta nel lato
  GUI). Per questo esiste `cad/draft2d.py`. Nota utile per la web app: draft2d è Python puro e
  **produce SVG**, quindi l'anteprima della tavola nel browser è immediata, senza FreeCAD.
- **Simboli**: nel PDF servono font in `WinAnsiEncoding`; nel DXF i codici `%%c` (diametro) e
  `%%d` (grado).
- Gli step lunghi (build, tavola, confronto) vanno in **job asincroni con log in streaming**,
  non in una richiesta HTTP sincrona.

## La regola non negoziabile, che deve sopravvivere nella web app

**Nessuna quota inventata.** Ogni numero che entra nel modello è (a) misurato dalla mesh da uno
script in `tools/`, oppure (b) approvato esplicitamente dall'utente e registrato. Se manca un valore
e non è approvato: fermarsi e chiedere, non stimare.

Nella UI questo si traduce in un requisito concreto: ogni quota va mostrata come **«misurato» vs
«usato nel modello»**, con la provenienza, e le divergenze vanno rese evidenti. Il progetto attuale
ha 8 discrepanze catalogate (D1–D8) e 7 ambiguità (A–G) che l'utente ha risolto una per una: quel
passaggio di decisione **è il cuore del prodotto**, non un dettaglio da nascondere dietro dei
default. Va progettato come uno step esplicito del flusso.

Attenzione a un tranello del dominio, spiegato in `docs/lost+found_design.md` §2.1: la tavola
tecnica TinkerCAD fornita come «fonte di verità» **non lo è**, perché è generata dalla mesh stessa.
La web app non deve indurre l'utente a credere che un disegno caricato sia automaticamente
autorevole.

## Flusso che immagino nella UI (da discutere, non è un ordine)

1. Upload di `model.obj` (+ `.mtl`, ed eventuale immagine/PDF della tavola di riferimento)
2. Analisi automatica → report delle feature trovate, con render ortografici e sezioni
3. Tabella **misurato → proposto** e le ambiguità da risolvere, come form
4. Build → anteprima 3D (STL) e **mappa di scostamento** modello ↔ mesh
5. Tavola → anteprima SVG nel browser, con impaginazione modificabile
6. Download di STEP / STL / PDF / DXF / SVG e del report di verifica

## Cosa mi aspetto da te

- Chiedimi stack e hosting, poi un piano. Lo scopo è già deciso: non riaprirlo.
- Non buttare via il codice esistente: `draft2d.py`, i tool di analisi e `compare_model_mesh.py`
  sono verificati e vanno riusati.
- Separa presto ciò che è **specifico del pezzo** (lo schema di `params.json`, le feature costruite
  in `build_model.py`) da ciò che è **generico** (analisi mesh, motore di disegno, confronto): è la
  scelta architetturale che decide se il progetto scala.
- Mantieni i file di progetto del mio workflow (`CLAUDE.md`, `LORE.md`, `STATE.md`,
  `docs/BUILD-LOG.md`, `docs/CONVENTIONS.md`) aggiornati man mano.
- Applica il trigger di chiusura capitolo standard quando la sessione si avvicina ai 400k token.
