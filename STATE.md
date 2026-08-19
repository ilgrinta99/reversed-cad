# STATE

**Fase corrente:** FASI 1–5 completate. Modello e tavola consegnati.
**Aggiornato:** 2026-08-19

## Fatto
- [x] FASE 1 — briefing: quote della tavola, misura della mesh, discrepanze D1–D8, ambiguità A–G
- [x] FASE 2 — ambiente: FreeCAD 1.1.3 headless, venv Python 3.13 (numpy, ezdxf)
- [x] Decisioni A–G ricevute dal committente e applicate
- [x] FASE 3 — modello parametrico: `cad/params.json` (misurato) + `cad/build_model.py`
- [x] FASE 5 — verifica contro la mesh, 3 giri di correzione (vedi BUILD-LOG)
- [x] FASE 4 — tavola tecnica quotata, 3 fogli A3, PDF + DXF + SVG

## Uscite
| file | contenuto |
|---|---|
| `output/model.step` | assieme scatola + coperchio |
| `output/scatola.step`, `output/coperchio.step` | pezzi singoli |
| `output/model.stl`, `scatola.stl`, `coperchio.stl` | mesh per stampa |
| `output/taiser.FCStd` | documento FreeCAD |
| `output/drawing.pdf` | tavola, 3 fogli A3 |
| `output/drawing.dxf` | stessa tavola, 3 fogli affiancati, 8 layer |
| `output/drawing_p1..3.svg` | fogli singoli |

## Verifica
- Ingombri: scatola **80.000 × 46.000 × 27.000** (= tavola T1/T2/T3), coperchio
  **73.860 × 46.000 × 2.500** (T4 scostato di −0.140 per decisione F, deliberato).
- Scostamento modello ↔ mesh: scatola mediana 0.015 / p90 0.056 mm;
  coperchio mediana 0.013 / p90 0.127 mm. Ogni residuo > 0.5 mm è il raccordo di base (decisione A).

## Aperto — decisione del committente
1. **Raccordo di base ellittico.** È l'unico scostamento oltre 0.5 mm. Azzerarlo richiede uno sweep
   dedicato (`makeFillet` non fa raccordi ellittici). Vale la pena?
2. **Tolleranze.** Il modello è nominale: nessuna tolleranza, nessun datum, nessun accoppiamento
   quotato fra coperchio e colonnine. La tavola TinkerCAD non ne conteneva.

## Come rigenerare tutto
```bash
.venv/bin/python tools/extract_params.py
/Applications/FreeCAD.app/Contents/MacOS/FreeCAD -c cad/build_model.py < /dev/null
/Applications/FreeCAD.app/Contents/MacOS/FreeCAD -c cad/make_drawing.py < /dev/null
/Applications/FreeCAD.app/Contents/MacOS/FreeCAD -c tools/compare_model_mesh.py < /dev/null
```
