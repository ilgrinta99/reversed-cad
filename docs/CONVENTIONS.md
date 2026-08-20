# Convenzioni

## Unità e sistema di riferimento
- Tutte le lunghezze in **millimetri**, angoli in gradi.
- Modello parametrico: origine al **centro della base della scatola**,
  X = lunghezza, Y = larghezza, Z = verso l'alto. *(da confermare — lost+found_design.md §5-G)*
- La mesh OBJ conserva il suo sistema originale Tinkercad; le conversioni sono esplicite nel codice.

## Fonti di verità
1. **La mesh `input/model.obj` è l'unica fonte reale di quote** (vedi lost+found_design.md §2.1: la tavola
   TinkerCAD è generata dalla mesh stessa e riporta solo 6 quote di ingombro).
2. La tavola TinkerCAD vale come conferma degli ingombri esterni.
3. Nessuna quota viene inventata: ogni valore è misurato o esplicitamente approvato dal committente
   e annotato in `docs/lost+found_design.md`.

## Codice
- Python 3.13, venv locale `.venv/`.
- `tools/` = analisi (leggono la mesh, non producono CAD).
- `cad/` = costruzione (producono solidi ed export).
- Ogni parametro dimensionale vive in un unico dict `PARAMS` in testa allo script, mai inline.
- Commenti e docstring in italiano.

## Tolleranze di lettura della mesh

Sono soglie con cui si *legge* un triangolato, non quote di un pezzo, e stanno in
cima ai moduli di `core/mesh/` con la ragione accanto. Cambiarle è una taratura, e
va fatta lì e non nel codice che le usa.

| Soglia | Valore | Dove |
|---|---|---|
| saldatura dei vertici | 1e-4 mm | `patches.WELD_TOL` |
| rottura di una patch fra normali adiacenti | 12° | `patches.BREAK_ANGLE_DEG` |
| dispersione sotto cui la patch è un piano | 1° | `patches.PLANE_SPREAD_DEG` |
| errore di fit di una primitiva | 2 % del raggio **e** 0.10 mm | `patches.FIT_RMS_RATIO`, `FIT_RMS_ABS` |
| area minima di una faccia esterna | 5 % della sezione del corpo | `analysis.MIN_FACE_FRACTION` |
| cilindro completo (foro) contro arco parziale | ingombro trasversale ≥ 1.6 R | `analysis.BORE_WIDTH_RATIO` |

## Tolleranze di confronto
- Confronto modello ↔ mesh: scostamento accettabile **≤ 0.10 mm** su feature piane,
  **≤ 0.50 mm** su superfici curve ricostruite in modo approssimato (cupola).
- Ogni scostamento oltre soglia va registrato in `docs/BUILD-LOG.md`.

## Percorsi degli script (web app e riga di comando)

Gli script di `tools/` e `cad/` leggono quattro variabili d'ambiente. Senza di esse
il comportamento è quello di sempre, relativo alla radice del repo: nessun comando
documentato cambia.

| Variabile | Cosa punta | Default |
|---|---|---|
| `TAISER_MESH` | mesh OBJ da misurare | `input/model.obj` |
| `TAISER_PARAMS` | file delle quote | `cad/params.json` |
| `TAISER_OUT` | cartella degli artefatti | `output/` |
| `TAISER_REPORT` | JSON del confronto (solo `compare_model_mesh.py`) | nessuno |

Restano le due preesistenti: `TAISER_N` (vertici campionati nel confronto) e
`TAISER_PAGES` (PDF per foglio separati).

Ogni script FreeCAD stampa `TEISER_OK` come ultima riga. Non è decorazione: FreeCAD
esce con codice 0 anche dopo un'eccezione non catturata, quindi il runner della web
app usa quella riga per distinguere un build riuscito da uno morto a metà.

## Confine fra generico e specifico del pezzo

Vale per il codice della web app, e decide dove va scritta una funzione nuova:

- **se contiene un numero, un nome di feature o un'assunzione geometrica del
  contenitore TAISER, sta in `parts/teiser/`**;
- tutto il resto è `core/`: caricamento mesh (`core/mesh/loader.py`: OBJ, STL,
  PLY, WRL — un lettore per formato, un solo ingresso), runner FreeCAD, registro delle quote,
  formato del confronto, motore di disegno (`core/drafting/`: primitive e backend,
  cornice e cartiglio, proiezione con linee nascoste, compositore di tavole).
  *Quali* viste e *quali* quote vanno in tavola è invece di chi la compone, e sta
  in `parts/` (`parts/auto/drawing.py` per il ricostruttore automatico).

Il backend web non importa mai `parts.teiser`: passa dal registry di `core.plugin`.

## La regola non negoziabile, nel codice

`core/provenance/` non è documentazione: `Registry.assert_buildable()` solleva, e
la build non parte, se anche una sola quota non è né misurata né approvata.
Un'approvazione senza motivazione viene rifiutata. Le divergenze approvate restano
elencabili: approvare non è nascondere.
