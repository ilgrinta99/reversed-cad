# STATE

**Fase corrente:** FASE 1 completata → **in attesa di conferma committente**
**Aggiornato:** 2026-08-19

## Fatto
- [x] Scheletro progetto + git init + venv (numpy)
- [x] Sorgenti copiati in `input/`
- [x] Toolchain di analisi mesh (`tools/`, 4 script)
- [x] Estrazione quote tavola TinkerCAD (6 quote di ingombro)
- [x] Misura completa della mesh: gusci, cavità, cupola, fori, asole, colonnine, tasche
- [x] `docs/design.md` — quote, quote mancanti, discrepanze D1–D8, ambiguità A–G

## In corso (nulla — FASE 2 sostanzialmente chiusa)
- [x] FreeCAD 1.1.3 installato e verificato headless (Part, Import, importDXF, Mesh, TechDraw)

## Bloccato — serve risposta del committente
Le 7 domande A–G in `docs/design.md` §5. Le più impattanti:
- **B** — spessore pareti asimmetrico (1.293 X vs 2.188 Y): uniformare o mantenere?
- **C** — la cupola non è un ellissoide: approssimare o fare loft su sezioni?
- **F** — accoppiamento scatola/coperchio indefinito (il coperchio da 74.00 non combacia
  né con la cavità da 71.27 né col corpo esterno da 73.86)

## Prossimo
FASE 2 (setup FreeCAD) può partire in parallelo. FASE 3 (costruzione) è bloccata da A–G.
