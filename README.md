# Teiser — reverse engineering CAD del contenitore TAISER

Ricostruzione di un modello CAD **parametrico esatto** (STEP) a partire da una mesh OBJ Tinkercad,
con generazione di una tavola tecnica quotata (PDF + DXF) tramite FreeCAD TechDraw.

## Struttura

```
input/     model.obj, model.mtl      sorgenti Tinkercad (sola lettura)
tools/     script di analisi mesh    misura, segmentazione, sezioni, render
cad/       script di costruzione     modello parametrico FreeCAD
output/    model.step, model.stl, drawing.pdf, drawing.dxf
docs/      design.md, BUILD-LOG.md, CONVENTIONS.md
```

## Uso

```bash
.venv/bin/python tools/segment_features.py input/model.obj   # features e quote dalla mesh
.venv/bin/python tools/slice_mesh.py                          # profili di sezione
.venv/bin/python tools/render_views.py input/model.obj /tmp   # viste ortografiche PNG
```

## Stato

FASE 1 (briefing) completa — vedi [docs/design.md](docs/design.md). In attesa di conferma
sulle ambiguità A–G prima di procedere alla costruzione parametrica.
