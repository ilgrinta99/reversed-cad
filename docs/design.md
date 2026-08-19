# FASE 1 — Briefing di reverse engineering

**Progetto:** contenitore TAISER (scatola + coperchio)
**Data:** 2026-08-19
**Fonti:** `input/model.obj` (mesh Tinkercad), `input/model.mtl`, tavola tecnica TinkerCAD (immagine allegata in sessione)
**Strumenti di analisi:** `tools/analyze_mesh.py`, `tools/segment_features.py`, `tools/slice_mesh.py`, `tools/render_views.py`

---

## 1. Struttura del file OBJ

| Oggetto | Ruolo | Materiale | Triangoli | Bounding box (mm) |
|---|---|---|---|---|
| `obj_0` | **Scatola** | `color_4634441` (verde) | 9 652 | X −43.700…36.300, Y −50.900…−4.900, Z 0…26.999 |
| `obj_1` | **Coperchio** | `color_15277357` (rosso) | 1 532 | X −46.000…28.000, Y 33.833…79.833, Z 0…2.500 |

I due corpi sono **affiancati nel file**, non assemblati: il coperchio va traslato di circa
`(+2.456, −84.500, +26.999)` per andare in appoggio sulla scatola (offset ricavato allineando i 4 fori
del coperchio con le 4 colonnine interne della scatola — **da confermare**, vedi §5).

---

## 2. Quote estratte dalla tavola TinkerCAD

La tavola riporta **6 quote in totale**, tutte di ingombro esterno:

| # | Vista | Quota | Valore |
|---|---|---|---|
| T1 | Scatola, dall'alto | Lunghezza | 80.00 mm |
| T2 | Scatola, dall'alto / laterale | Larghezza | 46.00 mm |
| T3 | Scatola, frontale / laterale | Altezza | 27.00 mm |
| T4 | Coperchio, dall'alto / frontale | Lunghezza | 74.00 mm |
| T5 | Coperchio, dall'alto / laterale | Larghezza | 46.00 mm |
| T6 | Coperchio, frontale / laterale | Spessore | 2.50 mm |

Nessuna tolleranza, nessuna quota di dettaglio, nessun riferimento di datum, nessuna scala numerica.
Il cartiglio dichiara: unità mm, formato A3, fonte «OBJ Tinkercad».

### 2.1 Verifica tavola ↔ mesh

| Quota | Tavola | Mesh misurata | Δ |
|---|---|---|---|
| Scatola L | 80.00 | 80.000 | 0.000 |
| Scatola W | 46.00 | 46.000 | 0.000 |
| Scatola H | 27.00 | 26.999 | −0.001 |
| Coperchio L | 74.00 | 74.000 | 0.000 |
| Coperchio W | 46.00 | 46.000 | 0.000 |
| Coperchio S | 2.50 | 2.500 | 0.000 |

> **Conclusione critica.** La coincidenza è esatta al millesimo su tutte e sei le quote, e la nota in
> calce alla tavola dichiara «quote geometriche misurabili direttamente dal modello OBJ». La tavola
> **non è una fonte indipendente**: è stata generata *dalla stessa mesh*. Non aggiunge quindi nessuna
> informazione dimensionale che la mesh non contenga già, e non può essere usata come arbitro in caso
> di conflitto. In pratica **la mesh è l'unica fonte reale di quote di questo progetto.**

---

## 3. Quote MANCANTI sulla tavola (misurate dalla mesh)

Tutto ciò che segue è **assente dalla tavola** ed è stato ricavato dalla mesh. La colonna «proposto»
contiene il valore arrotondato che intendo usare nel modello parametrico, da approvare.

### 3.1 Scatola — guscio

| Feature | Misurato (mm) | Proposto | Note |
|---|---|---|---|
| Spessore pareti Y (fronte/retro) | 2.188 | **2.2** | −50.900→−48.712 e −7.088→−4.900, simmetrico |
| Spessore pareti X (sinistra/destra) | 1.293 | **1.3** | −43.700→−42.407 e 28.867→30.160 |
| Spessore fondo | 1.634 | **1.6** | piano cavità a Z = 1.634 |
| Cavità interna | 71.274 × 41.624 × 25.365 | derivata | X −42.407…28.867, Y −48.712…−7.088, Z 1.634…26.999 |
| Corpo rettangolare (senza cupola) | 73.860 × 46.000 × 26.999 | **73.86 × 46 × 27** | X −43.700…30.160 |
| Raccordo perimetrale inferiore | ellittico ≈ 1.5 (X) × 1.4 (Z) | **R 1.5** | non circolare nella mesh, vedi §5-A |

> ⚠️ **Asimmetria anomala**: le pareti X (1.293) e Y (2.188) hanno spessori diversi, e nessuno dei due
> è un valore "da progetto". Rapporto 2.188/1.293 = 1.692. Vedi §5-B.

### 3.2 Scatola — cupola ellittica sul lato destro

Feature **completamente assente dalla tavola** (vedi §4).

| Parametro | Misurato (mm) | Proposto |
|---|---|---|
| Sporgenza oltre la parete (X) | 36.300 − 30.160 = **6.140** | 6.14 |
| Estensione Y | −45.280…−10.555 → 34.725 | ≈ 34.9 |
| Estensione Z | 2.548…18.907 → 16.359 | ≈ 16.44 |
| Centro | Y = −27.918, Z = 10.728 | — |
| Guscio | cava, apre nella cavità della scatola | — |

Il test di ellissoide (semiassi 6.14 / 17.36 / 8.18) dà scarto medio 12.5 % e massimo 25.7 %:
**la cupola NON è un ellissoide**. Vedi §5-C.

### 3.3 Scatola — fori e tasche

| Feature | Posizione | Dimensione misurata |
|---|---|---|
| Foro Ø3 parete destra | asse X, Y = −46.000, Z = 4.250 | **Ø 3.005**, L 1.293 (passante), fit rms 0.0003 → cilindro perfetto |
| 2 aperture nella cupola | Z ≈ 11.20, Y ≈ −20.16 e −35.92 | ≈ 3.46 (Z) — sezione non circolare, vedi §5-D |
| Asola parete frontale | Y −50.900…−48.712 (passante) | 6.467 (X) × 4.005 (Z), centro X −4.924, Z 23.750 |
| Tasca faccia sinistra | X −43.700…−43.010 (prof. 0.690) | 19.790 (Y) × 11.005 (Z), Y −48.677…−28.887, Z 12.997…24.002 |
| 2 archi R1.49 nella tasca | (Y,Z) = (−34.308, 22.277) e (−40.790, 22.176) | Ø ≈ 2.98, profondità 0.690 |

### 3.4 Scatola — features interne

| Feature | Descrizione | Quote |
|---|---|---|
| 4 colonnine d'angolo | prismi con smusso inferiore ≈45° | 5.183 (X) × 8.762 (Y), da Z 14.191 a 26.999; smusso da Z 14.191 a 23.171 |
| 4 fori nelle colonnine | passanti verso l'alto | 1.625 × 2.743, da Z 17.687 a 26.999 |
| 2 nervature con testa R2.99 | su parete Y = −48.712 | X 1.078…2.924 e −12.771…−10.925; Z 23.202…24.890; sporgenza fino a Y = −42.861 |

### 3.5 Coperchio

| Feature | Misurato (mm) | Proposto |
|---|---|---|
| Piastra | 74.000 × 46.000 × 2.500 | come tavola |
| Faccia superiore | piana a Z = 2.500 | — |
| Faccia inferiore | piana a Z = 0 | — |
| Raccordo perimetrale inferiore | ellittico ≈ 1.5 (XY) × 1.8 (Z) | **R 1.5 / 1.8** |
| Fascia laterale netta | solo da Z 1.801 a 2.500 (0.699) | 0.7 |
| Gradino lato Y− | Z = 0.078 fino a Y = 35.623 | — |
| 4 fori d'angolo (passanti) | 1.952 (X) × 3.291 (Y) — **asolati, non circolari** | vedi §5-E |
| ↳ posizione | X −43.081…−41.129 e 23.129…25.081; Y 38.759…42.050 e 71.616…74.907 | — |
| Tasca rettangolare grande | 12.030 × 12.865, prof. 0.502 (fino a Z 1.998) | X −36.290…−24.260, Y 39.766…52.631 |
| Tasca annidata | 4.630 × 4.951, prof. 1.502 (fino a Z 0.998) | X −32.590…−27.960, Y 43.723…48.674 |
| 2 tasche piccole | 2.780 × 2.973, prof. 1.502 | X 12.735…15.515 e 17.360…20.140; Y 51.637…54.610 |

---

## 4. Discrepanze tavola ↔ mesh

| # | Gravità | Descrizione |
|---|---|---|
| **D1** | 🔴 alta | La tavola disegna **solo le sagome esterne**. Nessuna linea interna, nessuna linea nascosta, nessuna sezione. Cavità, pareti, fondo, colonnine, nervature: tutto invisibile. |
| **D2** | 🔴 alta | La **vista laterale della scatola** è un rettangolo 46 × 27 pulito: la cupola ellittica (che guardando da quel lato è il dettaglio dominante, ≈ 34.9 × 16.4 mm) e le sue 2 aperture **non compaiono affatto**. La sagoma esterna è formalmente corretta (la cupola sta dentro l'ingombro), ma la vista è di fatto priva del contenuto informativo principale. |
| **D3** | 🔴 alta | Il **foro Ø3.005 sulla parete destra** e l'**asola 6.47 × 4.01 sulla parete frontale** non compaiono in nessuna vista, pur essendo passanti e visibili dall'esterno. |
| **D4** | 🟠 media | I **4 fori del coperchio** sono disegnati (4 piccoli ovali) ma **senza nessuna quota**: né diametro/dimensione, né interasse, né distanza dai bordi. |
| **D5** | 🟠 media | Le **tasche sulla faccia superiore del coperchio** (una 12.03 × 12.87, una annidata 4.63 × 4.95, due da 2.78 × 2.97) non compaiono nella vista dall'alto del coperchio, che è disegnata come un rettangolo vuoto. |
| **D6** | 🟡 bassa | Nessuna **tolleranza**, nessun **datum**, nessuna indicazione di stato superficiale o materiale. Per un accoppiamento scatola/coperchio l'accoppiamento è indefinito. |
| **D7** | 🟡 bassa | La quota altezza scatola è **27.00** ma la mesh dà **26.999**. Scarto trascurabile (arrotondamento della tavola), ma conferma che la tavola è generata e arrotondata a 2 decimali. |
| **D8** | 🟡 bassa | La tavola non indica **come i due pezzi si accoppiano**: nel file OBJ sono affiancati, non assemblati. |

---

## 5. Ambiguità da risolvere prima di modellare

**A — Raccordi non circolari.** I raccordi perimetrali sono **ellittici**, non archi di cerchio
(coperchio: 1.484 in XY contro 1.801 in Z; scatola: ≈1.51 in X contro ≈1.42 in Z). È il comportamento
tipico della primitiva "Box arrotondato" di TinkerCAD quando viene scalata in modo non uniforme.
→ *Domanda:* li ricostruisco come **raccordi circolari** di raggio nominale (più pulito, tecnicamente
corretto, scarto ≤ 0.35 mm) oppure li replico **ellittici** per fedeltà 1:1 alla mesh?

**B — Spessore pareti asimmetrico.** 1.293 mm sulle pareti X contro 2.188 mm sulle pareti Y. Nessuno
dei due è un valore di progetto plausibile, ed è ancora una volta la firma di una primitiva scalata
in modo non uniforme.
→ *Domanda:* uniformo a un unico spessore di progetto (es. **1.5** o **2.0** mm) oppure mantengo
l'asimmetria misurata?

**C — Geometria della cupola.** Non è un ellissoide (scarto medio 12.5 %). Il profilo in sezione
Y = −27.92 è un arco molto pieno che parte da (30.160, 2.537), raggiunge X = 36.272 a Z = 10.209 e
rientra a (30.160, 18.977). Probabile primitiva "Paraboloide"/"Goccia" TinkerCAD scalata, oppure un
loft. Serve una decisione sulla ricostruzione.
→ *Domanda:* la modello come **semi-ellissoide approssimato** (semplice, parametrico, scarto ~1 mm),
oppure come **loft su sezioni estratte dalla mesh** (fedele ma poco parametrico)?

**D — Aperture nella cupola.** Le due aperture non danno un fit circolare accettabile (rms 0.89–0.95
su R≈1.9). Estensione Z 3.463 mm costante per entrambe. Vanno indagate meglio: potrebbero essere fori
cilindrici *inclinati* rispetto a X, oppure asole.
→ Serve un passaggio di analisi dedicato in FASE 3.

**E — Fori del coperchio.** 1.952 × 3.291 mm: **asole**, non fori circolari. Se sono asole, servono
raggio delle testate e interasse; se erano intese come fori Ø2 deformati dallo scaling, va deciso il
diametro nominale.
→ *Domanda:* asole fedeli alla mesh, o fori circolari Ø nominale?

**F — Accoppiamento scatola/coperchio.** L'offset (+2.456, −84.500) è stato dedotto allineando i fori
del coperchio con le colonnine della scatola, ma **non torna esattamente**: il coperchio è largo 74.00
mentre il vano tra le pareti X della scatola sarebbe 71.27 e il corpo esterno 73.86. Il coperchio
quindi né entra nella cavità né combacia col profilo esterno.
→ *Domanda:* qual è l'accoppiamento voluto? (coperchio a filo esterno / incassato / appoggiato sulle
colonnine con viti nei 4 fori)

**G — Origine e datum.** La mesh ha origine arbitraria (Z = 0 sul fondo, X/Y decentrati).
→ *Proposta:* ricentrare il modello parametrico con **origine al centro della base della scatola**,
X lungo la lunghezza, Y lungo la larghezza, Z verso l'alto. Da confermare.

---

## 6. Stato

- [x] Quote della tavola estratte (6)
- [x] Mesh importata e misurata
- [x] Discrepanze catalogate (D1–D8)
- [ ] **Risposte alle domande A–G** ← *blocca la FASE 3*
- [ ] Modello parametrico
- [ ] Tavola TechDraw

> Nessun valore di questo documento è stato inventato: ogni numero è misurato dalla mesh
> (`tools/*.py`, riproducibile) o letto dalla tavola.
