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
