# STATE

**Fase corrente:** FASI 1–5 completate. FASE 6 (web app) in piedi e verificata end-to-end.
**Aggiornato:** 2026-08-19

## Fatto
- [x] FASE 1 — briefing: quote della tavola, misura della mesh, discrepanze D1–D8, ambiguità A–G
- [x] FASE 2 — ambiente: FreeCAD 1.1.3 headless, venv Python 3.13 (numpy, ezdxf)
- [x] Decisioni A–G ricevute dal committente e applicate
- [x] FASE 3 — modello parametrico: `cad/params.json` (misurato) + `cad/build_model.py`
- [x] FASE 5 — verifica contro la mesh, 3 giri di correzione (vedi BUILD-LOG)
- [x] FASE 4 — tavola tecnica quotata, 3 fogli A3, PDF + DXF + SVG
- [x] FASE 6 — web app: FastAPI + coda job su SQLite + React/three.js, pipeline
      completa dal browser (analisi 10 s, build 6 s, tavola 2 s, confronto 10 s)

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

## Web app (FASE 6)

Runner web della stessa pipeline. Gli script non sono stati riscritti: sono
puntabili su una cartella di run con `TAISER_MESH` / `TAISER_PARAMS` /
`TAISER_OUT` / `TAISER_REPORT` (docs/CONVENTIONS.md). Da riga di comando tutto
funziona come prima.

| Dove | Cosa |
|---|---|
| `core/` | runner FreeCAD, registro quote, formato confronto — generico |
| `parts/teiser/` | schema di params.json, decisioni A–G e D1–D8, cablaggio degli script |
| `webapp/backend` | FastAPI, coda job in-process, SQLite, log in streaming SSE |
| `webapp/frontend` | React + Vite + three.js |
| `docker/` | immagine Linux con FreeCAD 1.1.3 da conda-forge |

Il registro delle quote sta **sopra** params.json, non al suo posto: 46 quote in
tabella, 8 divergenze fra misurato e usato, 2 senza misura scalare (i raccordi
ellittici). Tutte e 10 sono coperte dalle decisioni registrate in §6 di
lost+found_design.md, che l'app riapplica dopo ogni analisi. Senza quelle
approvazioni la build non parte.

**Verifica cross-piattaforma:** su Linux con FreeCAD conda-forge 1.1.3 il confronto
modello ↔ mesh dà le stesse identiche cifre del Mac (§8 di lost+found_design.md).

### Aperto sulla web app
1. **Immagine Docker mai costruita davvero.** FreeCAD conda-forge è stato verificato
   installandolo direttamente (è quel che fa il Dockerfile), ma nel container di
   sviluppo non c'era un demone Docker: `docker build` va eseguito una volta.
2. **Peso dei run: 47 MB**, di cui 44 MB di STL a tassellazione fine. L'anteprima usa
   `preview.stl` (1.6 MB), ma la cartella del run non viene mai ripulita.
3. **Un solo pezzo cablato.** `parts/demo_box/` esiste come implementazione di
   riferimento; un secondo pezzo vero non è mai stato provato.

## Aperto — decisione del committente
1. **Raccordo di base ellittico.** È l'unico scostamento oltre 0.5 mm. Azzerarlo richiede uno sweep
   dedicato (`makeFillet` non fa raccordi ellittici). Vale la pena?
2. **Tolleranze.** Il modello è nominale: nessuna tolleranza, nessun datum, nessun accoppiamento
   quotato fra coperchio e colonnine. La tavola TinkerCAD non ne conteneva.

## Come rigenerare tutto (riga di comando)
```bash
.venv/bin/python tools/extract_params.py
/Applications/FreeCAD.app/Contents/MacOS/FreeCAD -c cad/build_model.py < /dev/null
/Applications/FreeCAD.app/Contents/MacOS/FreeCAD -c cad/make_drawing.py < /dev/null
/Applications/FreeCAD.app/Contents/MacOS/FreeCAD -c tools/compare_model_mesh.py < /dev/null
```
