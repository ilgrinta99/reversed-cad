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

## Tolleranze di confronto
- Confronto modello ↔ mesh: scostamento accettabile **≤ 0.10 mm** su feature piane,
  **≤ 0.50 mm** su superfici curve ricostruite in modo approssimato (cupola).
- Ogni scostamento oltre soglia va registrato in `docs/BUILD-LOG.md`.
