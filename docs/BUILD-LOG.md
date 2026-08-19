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
- Catalogate 8 discrepanze (D1–D8) e 7 ambiguità bloccanti (A–G) in `docs/design.md`.
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
