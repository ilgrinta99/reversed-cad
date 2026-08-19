# CLAUDE.md

Reverse engineering CAD: da mesh OBJ Tinkercad a modello parametrico STEP + tavola quotata.

## Leggi prima
1. `STATE.md` — dove siamo, cosa blocca
2. `docs/design.md` — tutte le quote, discrepanze D1–D8, ambiguità A–G
3. `LORE.md` — perché la geometria è "sporca" e perché la tavola non è affidabile
4. `docs/CONVENTIONS.md` — unità, datum, regole sul codice

## Regola non negoziabile
**Nessuna quota inventata.** Ogni numero che entra nel modello è (a) misurato dalla mesh con uno
script in `tools/`, oppure (b) approvato esplicitamente dal committente e registrato in `design.md`.
Se manca un valore e non è approvato: **fermarsi e chiedere**, non stimare.

## Attenzione
`docs/design.md` §2.1 — la tavola TinkerCAD **non è** una fonte indipendente di quote: è generata
dalla mesh e contiene solo 6 ingombri esterni. Non usarla come arbitro.

## Comandi

```bash
.venv/bin/python tools/segment_features.py input/model.obj
.venv/bin/python tools/slice_mesh.py
.venv/bin/python tools/render_views.py input/model.obj /tmp
```

FreeCAD headless (una volta installato):
```bash
/Applications/FreeCAD.app/Contents/MacOS/FreeCAD -c cad/build_model.py
```

## Ambiente
- Python 3.13 in `.venv/` (numpy). FreeCAD via Homebrew cask, usato headless con `FreeCADCmd`.
- `input/` è sola lettura. Gli output rigenerabili stanno in `output/`.
