# Teiser — reverse engineering CAD del contenitore TAISER

Ricostruzione di un modello CAD **parametrico** (STEP) a partire da una mesh OBJ Tinkercad, con
tavola tecnica quotata in PDF e DXF generata dal modello.

L'oggetto è un contenitore per elettronica in due pezzi: scatola 80 × 46 × 27 mm con una cupola
paraboloidica sul fianco, e coperchio 73.86 × 46 × 2.5 mm.

## Struttura

```
input/     model.obj, model.mtl      sorgenti Tinkercad (sola lettura)
tools/     analisi della mesh        misura, segmentazione, sezioni, render, confronto
cad/       costruzione               params.json (quote misurate), build_model.py,
                                     make_drawing.py, draft2d.py (motore 2D)
output/    STEP, STL, FCStd, PDF, DXF, SVG
docs/      lost+found_design.md, BUILD-LOG.md, CONVENTIONS.md
```

## Come rigenerare

```bash
.venv/bin/python tools/extract_params.py
/Applications/FreeCAD.app/Contents/MacOS/FreeCAD -c cad/build_model.py < /dev/null
/Applications/FreeCAD.app/Contents/MacOS/FreeCAD -c cad/make_drawing.py < /dev/null
/Applications/FreeCAD.app/Contents/MacOS/FreeCAD -c tools/compare_model_mesh.py < /dev/null
```

Il `< /dev/null` è necessario: senza, FreeCAD esegue lo script e resta appeso sulla console.

## Il punto da sapere

La tavola TinkerCAD fornita come «fonte di verità per tutte le misure» **non lo è**: le sue 6 quote
coincidono al millesimo col bounding box della mesh perché è stata generata dalla mesh stessa, e
tace su tutto il resto — cavità, spessori, cupola, fori, colonnine. L'unica fonte reale di quote è
la mesh. Vedi [docs/lost+found_design.md](docs/lost+found_design.md) §2.1 e [LORE.md](LORE.md).

## Stato

Fasi 1–5 completate. Scostamento modello ↔ mesh: mediana 0.015 mm (scatola), 0.013 mm (coperchio).
Dettagli e punti aperti in [STATE.md](STATE.md).
