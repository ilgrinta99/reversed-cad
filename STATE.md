# STATE

**Fase corrente:** FASI 1–5 completate. FASE 6 (web app) in piedi. FASE 7: l'analisi
non è più cablata sul TAISER — si carica una mesh e la si misura.
**Aggiornato:** 2026-08-20

## Fatto
- [x] FASE 1 — briefing: quote della tavola, misura della mesh, discrepanze D1–D8, ambiguità A–G
- [x] FASE 2 — ambiente: FreeCAD 1.1.3 headless, venv Python 3.13 (numpy, ezdxf)
- [x] Decisioni A–G ricevute dal committente e applicate
- [x] FASE 3 — modello parametrico: `cad/params.json` (misurato) + `cad/build_model.py`
- [x] FASE 5 — verifica contro la mesh, 3 giri di correzione (vedi BUILD-LOG)
- [x] FASE 4 — tavola tecnica quotata, 3 fogli A3, PDF + DXF + SVG
- [x] FASE 6 — web app: FastAPI + coda job su SQLite + React/three.js, pipeline
      completa dal browser (analisi 10 s, build 6 s, tavola 2 s, confronto 10 s)
- [x] FASE 7 — analisi ad hoc: niente pezzo da scegliere al caricamento, quote e
      ambiguità misurate sulla mesh caricata (`core/mesh/`, `parts/auto/`)

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

### Analisi ad hoc (FASE 7)

Il caricamento chiede un OBJ e nient'altro: il menu con cui si sceglieva il pezzo
*prima* di guardare il file non c'è più. Da quella scelta discendevano l'elenco
delle quote e il catalogo delle ambiguità, che su una mesh diversa dal TAISER
erano semplicemente le ambiguità di un altro pezzo.

| Modulo | Cosa risponde |
|---|---|
| `core/mesh/patches.py` | di quanti corpi è fatta la mesh, e di quali superfici (piano, cilindro, sfera, libera) |
| `core/mesh/analysis.py` | quali quote quelle superfici dimostrano: ingombri, pareti, cavità, raccordi, fori, asole, simmetria, datum |
| `core/mesh/ambiguity.py` | dove la misura non è conclusiva, con le opzioni numeriche già calcolate |
| `core/mesh/sections.py` | sezioni piane, aree dei contorni, fit di cerchi |
| `parts/auto/` | ricostruzione parametrica con repertorio dichiarato: prisma, raccordo verticale, cavità, fori |

Le schede di decisione compaiono **dopo** l'analisi, perché prima non esistono. Se
la mesh non solleva ambiguità, il pannello lo dice e il modello si costruisce con
le misure così come sono — una quota misurata è già un'origine legittima. Quando
invece una quota *non esiste come misura scalare* (il caso del raccordo non
circolare: due arretramenti diversi, quindi nessun raggio unico), resta vuota e
blocca la build finché una decisione non la approva.

**Verifica su `input/model.obj`:** senza una riga che sappia cos'è un TAISER,
l'analisi ritrova 80 × 46 × 26.999 e 74 × 46 × 2.5, gli spessori 1.293 / 2.188
(§5-B del briefing), il fondo 1.634 (§3.1), le 4 colonnine come corpi separati di
cui una diversa, e solleva 6 ambiguità — fra cui la cupola come superficie non
ricostruibile con una primitiva. 41 quote in tabella, nessuna bloccante.

### Aperto sulla web app
1. **Immagine Docker mai costruita davvero.** FreeCAD conda-forge è stato verificato
   installandolo direttamente (è quel che fa il Dockerfile), ma nel container di
   sviluppo non c'era un demone Docker: `docker build` va eseguito una volta.
2. **Peso dei run: 47 MB**, di cui 44 MB di STL a tassellazione fine. L'anteprima usa
   `preview.stl` (1.6 MB), ma la cartella del run non viene mai ripulita.
3. **Build automatica mai girata sotto FreeCAD.** `parts/auto/build_script.py` è
   scritto ma il container di sviluppo non ha FreeCAD: analisi, ambiguità, tavola
   SVG e confronto sono verificati girando davvero, la generazione di STEP/STL del
   percorso `auto` no. È il primo controllo da fare dove FreeCAD c'è.
4. **Il ricostruttore automatico è elementare.** Su una mesh con superfici libere
   il solido è una semplificazione dichiarata, non il modello finito: il confronto
   ne misura il costo.

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
