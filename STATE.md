# STATE

**Fase corrente:** FASI 1–5 completate. FASE 6 (web app) in piedi. FASE 7: l'analisi
non è più cablata sul TAISER — si carica una mesh e la si misura. FASE 8: la tavola
è una tavola anche lì, con viste proiettate, sezioni, quote e assonometria.
FASE 9: la mesh può essere OBJ, STL, PLY o WRL. FASE 10: quello che il modello
non porta si vede sulla tavola, con posizione e ingombro. FASE 11: la cupola non
era una superficie libera — è un paraboloide, e adesso si costruisce. FASE 12: la
pagina si legge senza essere del mestiere. FASE 13: sulla tavola c'è ogni
elemento del modello — pareti, fori, asole, aperture — e ciò che il modello non
porta ha il suo contorno vero, non un rettangolo.
**Aggiornato:** 2026-09-24

## Fatto
- [x] FASE 1 — briefing: quote della tavola, misura della mesh, discrepanze D1–D8, ambiguità A–G
- [x] FASE 2 — ambiente: FreeCAD 1.1.3 headless, venv Python 3.13 (numpy, ezdxf)
- [x] Decisioni A–G ricevute dal committente e applicate
- [x] FASE 3 — modello parametrico: `cad/params.json` (misurato) + `cad/build_model.py`
- [x] FASE 5 — verifica contro la mesh, 3 giri di correzione (vedi BUILD-LOG)
- [x] FASE 4 — tavola tecnica quotata, 4 fogli A3, PDF + DXF + SVG
- [x] FASE 6 — web app: FastAPI + coda job su SQLite + React/three.js, pipeline
      completa dal browser (analisi 10 s, build 6 s, tavola 2 s, confronto 10 s)
- [x] FASE 7 — analisi ad hoc: niente pezzo da scegliere al caricamento, quote e
      ambiguità misurate sulla mesh caricata (`core/mesh/`, `parts/auto/`)
- [x] FASE 8 — tavola vera anche per il percorso automatico: motore di disegno in
      `core/drafting/`, viste proiettate da TechDraw, assonometria isometrica
- [x] FASE 9 — quattro formati di ingresso: OBJ, STL, PLY, WRL
- [x] FASE 10 — niente sparisce in silenzio: ogni superficie fuori dal repertorio
      è dichiarata con posizione e ingombro, e ha la sua impronta sulle viste
- [x] FASE 11 — cupole (paraboloidi ellittici) e fori inclinati nel repertorio:
      scostamento mediano da 2.347 a 0.027 mm sulla mesh di prova
- [x] FASE 12 — UX: un pulsante, un riepilogo in italiano comune, e il gergo
      dietro l'interruttore «Modalità tecnica»
- [x] FASE 13 — ogni elemento del modello in tavola: pareti misurate anche quando
      il raccordo di base le fonde, asole e vani rettangolari costruiti, contorno
      vero delle superfici non ricostruite

## Uscite
| file | contenuto |
|---|---|
| `output/model.step` | assieme scatola + coperchio |
| `output/scatola.step`, `output/coperchio.step` | pezzi singoli |
| `output/model.stl`, `scatola.stl`, `coperchio.stl` | mesh per stampa |
| `output/taiser.FCStd` | documento FreeCAD |
| `output/drawing.pdf` | tavola, 4 fogli A3 (viste, sezioni, coperchio, assonometria) |
| `output/drawing.dxf` | stessa tavola, 4 fogli affiancati, 9 layer |
| `output/drawing_p1..4.svg` | fogli singoli |

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
| `core/mesh/patches.py` | di quanti corpi è fatta la mesh, e di quali superfici (piano, cilindro, sfera, paraboloide, libera) |
| `core/mesh/analysis.py` | quali quote quelle superfici dimostrano: ingombri, pareti, cavità, raccordi, fori, asole, simmetria, datum |
| `core/mesh/ambiguity.py` | dove la misura non è conclusiva, con le opzioni numeriche già calcolate |
| `core/mesh/sections.py` | sezioni piane, aree dei contorni, fit di cerchi |
| `parts/auto/` | ricostruzione parametrica con repertorio dichiarato: prisma, raccordo verticale, cavità, cupola, fori (anche inclinati) |

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

### Tavola quotata anche fuori dal pezzo cablato (FASE 8)

Fino a qui la tavola vera era solo quella del TAISER: il percorso automatico
produceva un SVG con tre rettangoli d'ingombro e una quota per rettangolo. Ora i
due percorsi producono la stessa classe di documento, perché il motore di disegno
è diventato generico.

| Modulo | Cosa fa |
|---|---|
| `core/drafting/sheet.py` | primitive 2D e i tre backend (SVG, PDF, DXF). Era `cad/draft2d.py` |
| `core/drafting/layout.py` | cornice, cartiglio ISO 7200, scale normalizzate ISO 5455, disposizione in primo diedro |
| `core/drafting/hlr.py` | proiezione con rimozione delle linee nascoste (TechDraw), sezioni, assonometria |
| `core/drafting/project_script.py` | gira **dentro** FreeCAD e riversa gli spigoli 2D in JSON |
| `core/drafting/tavola.py` | compositore: una specifica dichiarativa diventa fogli |
| `parts/auto/drawing.py` | *cosa* disegnare per una ricetta: viste, piani di sezione, quote |

Il confine è il JSON degli spigoli: FreeCAD proietta, tutto il resto —
impaginazione, quotatura, tre formati di uscita — è Python puro e si prova senza
FreeCAD.

Sulla mesh del TAISER il percorso automatico produce **11 fogli A3**: un foglio
d'assieme con l'assonometria, un foglio di viste ortogonali quotate per ciascuno
dei 6 corpi, due fogli di sezioni (i corpi con cavità) e il registro delle quote
con la provenienza di ogni numero. Sulle viste ortogonali di ogni corpo è
ricalcato in rosso il profilo della mesh sezionata a metà: si vede a occhio quanto
il prisma ricostruito si scosta dal pezzo, prima ancora del confronto numerico.

La tavola del TAISER guadagna un quarto foglio, l'assonometria isometrica di
assieme, scatola e coperchio; la silhouette della cupola in assonometria è
analitica come nelle viste ortogonali, perché anche lì l'HLR non la genera.

**Correzione di un difetto vecchio:** `TechDraw.project` restituisce quattro
gruppi di spigoli e il quarto — le tangenti *nascoste* — finiva fra i visibili.
Sulla pianta del TAISER erano due lunghe diagonali piene attraverso la cupola.
Ora sono tratteggiate, come devono essere.

### Quotatura consapevole dei pattern di fori

`core/drafting/patterns.py` (pura geometria, nessun pezzo) riconosce quando fori
uguali su una vista formano un **cerchio di fori** (equidistanti su un PCD) o una
**fila a passo costante**, e `parts/auto/drawing.py` li quota una volta —
«N× Ø d equidistanti su Ø(pcd) PCD», «N× Ø d passo p» — invece di ripetere N
richiami identici. Fuori dal pattern ogni foro torna al suo richiamo: una tavola
senza pattern non cambia di una virgola (i test lo bloccano).

Spunto preso da `neka-nat/cad-3dto2d` (`annotations/planner.py`), riscritto nel
nostro idiom e adattato al nostro modello mesh→ricetta. Il resto di quel repo —
proiezione, sezioni, assonometria, tre formati d'uscita — lo copriamo già, spesso
con più cose (assonometria, PDF multipagina, sovrapposizione del profilo mesh).
L'altro repo indicato, `mlightcad/awesome-cad`, è solo un indice di progetti: non
c'era codice da integrare.

**Provenance:** il diametro resta quello del registro (misurato o approvato). PCD
e passo sono conseguenze geometriche dei centri *già misurati*, ricavati solo per
la nota e dichiarati come tali sul foglio — la stessa scelta già fatta per gli
ingombri d'assieme misurati sul solido. Nessun numero nuovo entra nel modello.

### Quattro formati di mesh in ingresso (FASE 9)

`core/mesh/loader.py` è l'unico ingresso: sceglie il lettore dal suffisso e non
annusa il contenuto — un file rinominato per sbaglio deve fallire subito, non tre
passi più in là sotto forma di quote assurde. L'elenco dei formati sta lì e da lì
lo prendono sia l'API (rifiuto in caricamento) sia la UI (`/api/health` →
attributo `accept` del campo file): nessun secondo elenco che invecchia.

| formato | topologia | nomi dei corpi | precisione |
|---|---|---|---|
| `.obj` | dichiarata | gruppi `o` / `g` | testo, doppia |
| `.stl` | **assente** | solo ASCII, `solid` | singola |
| `.ply` | dichiarata | nessuno | singola se binario |
| `.wrl` | dichiarata | `DEF` | testo, doppia |

Le tre cose che rendono i formati diversi, e che il codice affronta invece di
ignorare:

1. **Lo STL non ha topologia.** Ogni triangolo porta i suoi tre vertici: caricato
   così, la segmentazione troverebbe un corpo per triangolo. I vertici si saldano
   al caricamento su una griglia da 1e-4 mm — la stessa con cui `patches.py`
   ricostruisce l'adiacenza — *senza spostarli*: di ogni gruppo si tiene la
   coordinata del file, non quella arrotondata.
2. **Il VRML è una scena, non una mesh.** La geometria sta sotto `Transform` che
   traslano, ruotano e scalano: ignorarli darebbe i pezzi tutti nell'origine, e a
   vedersi sembrerebbe giusto. Si applicano. Le primitive parametriche (`Box`,
   `Sphere`, `Cylinder`) non si convertono in triangoli: il file viene rifiutato
   con un messaggio che le nomina, invece di produrre una mesh vuota.
3. **Lo STL binario non si riconosce dalla parola `solid`**, che moltissimi
   esportatori scrivono anche lì: si guarda la dimensione del file, che in un STL
   binario vale esattamente 84 + 50 × triangoli.

**Verifica:** la mesh del progetto convertita nei quattro formati dà 6 corpi, gli
stessi ingombri e le stesse 41 quote. STL e PLY divergono di 2·10⁻⁵ mm al massimo
— è la precisione singola dei due formati, due ordini di grandezza sotto la
tolleranza con cui il registro distingue due numeri. Da un STL la pipeline gira
intera e produce gli stessi 11 fogli.

### Quello che il modello non porta si vede sulla tavola (FASE 10)

Prova su una mesh nuova — una scatola con cupola forata, boccole e tasche sul
coperchio — e il difetto è saltato fuori subito: sulla tavola quegli elementi non
c'erano *e niente diceva che ci fossero stati*. Il solido era corretto rispetto al
repertorio del ricostruttore; la tavola era muta rispetto al pezzo.

Tre cause distinte, tutte e tre chiuse:

1. **Superfici riconosciute e mai lette.** `patches.py` riconosce da sempre le
   sfere; nessuno le leggeva. `_read_holes` scartava i cilindri ad asse obliquo
   con un commento che prometteva «resta fra le feature» — e non ci restava. Gli
   archi parziali spaiati finivano in `a.arcs` e da lì in niente. Ora ogni
   superficie fuori dal repertorio è una feature dichiarata: `sfera`, `cilindro`,
   `arco`, accanto a `libera`. Sul TAISER le dichiarate passano da 11 a 27, sulla
   mesh di prova da 9 a 27. Un arco che *è* il raccordo che la build costruisce
   davvero non viene dichiarato omesso: sarebbe la bugia opposta.
2. **Dichiarate senza un dove.** Le feature non costruibili portavano area e
   ingombro, non la posizione: la tavola poteva scrivere «c'è una superficie
   libera» e basta. Ora portano `origine_*` e `centro_*`, e le viste ortogonali di
   ogni corpo ne disegnano l'**impronta** — il rettangolo d'ingombro, in viola, su
   layer `OMESSO` — con un richiamo per le prime cinque per area, incolonnato
   fuori dalla vista. Il rettangolo e non il contorno vero: ricalcare il contorno
   di una superficie libera equivarrebbe a dire che il modello la contiene.
3. **L'elenco del registro mentiva al contrario.** Era costruito su `buildable`,
   che dice se il repertorio *saprebbe* costruire una feature, non se l'ha
   costruita: con la decisione «asole = fori» le quattro asole del coperchio
   erano nel solido *e* nell'elenco delle non ricostruite. Ora l'elenco guarda la
   ricetta, e censisce per corpo e per tipo invece di troncare a otto voci.

Restano fuori dal repertorio del *costruttore*: la cupola non si costruisce, e non
la si approssima. La differenza è che adesso la tavola dice dove sta, quanto è
grande e che il modello non ce l'ha — invece di lasciare il foglio bianco lì.

### La cupola non era una superficie libera: era un paraboloide (FASE 11)

Dalla FASE 1 la cupola del TAISER era catalogata come «né piano né cilindro né
sfera» e la decisione A la faceva ignorare. Non era vero: è un **paraboloide
ellittico**, e basta provare a interpolarla per vederlo — come sfera dà rms
**1.443 mm**, come paraboloide **0.016 mm**, novanta volte meglio. Lo stesso vale
per la cupola della mesh di prova: 1.44 contro 0.018 mm.

`patches.py` prova ora il paraboloide dopo piano, cilindro e sfera, con gli stessi
criteri di accettazione (2 % del semiasse maggiore **e** 0.10 mm). Il fit è ad assi
coordinati per scelta: un paraboloide obliquo non si quota su una vista ortogonale
e il costruttore non saprebbe dove metterlo. Il criterio è selettivo — su entrambe
le mesh riconosce **solo** le due cupole vere e rifiuta ogni altra superficie
libera.

Le quote che entrano nel modello sono misure dirette dell'ingombro della patch —
semiassi del bordo, altezza, centro — non i coefficienti del fit: il fit decide
*che cosa* è quella superficie, non *quanto* misura.

**Fori a testa storta.** I due fori della cupola di prova escono a 21.8° dalla
parete. `_read_holes` scartava ogni cilindro ad asse non coordinato: non finivano
né fra i fori né altrove. Ora un cilindro *intero* è un foro anche obliquo — girargli
intorno per tutto il diametro è la prova che è un foro — e porta la sua direzione
misurata fino allo STEP. Un *arco* obliquo resta dichiarato: di quella testata non
si sa nemmeno di che feature è. Sul TAISER i due cilindri obliqui sono archi da
90° e infatti restano dichiarati: niente cambia lì.

**Costruzione.** `build_script.py` rivoluziona una parabola vera (Y² = 4·F·X con
F = ¼) e scala i tre assi sulle quote misurate. Il repertorio dichiarato diventa:
prisma, raccordo verticale, cavità, **cupola**, fori cilindrici **anche inclinati**.

**Effetto misurato**, mesh di prova, pipeline intera sotto FreeCAD 1.1.3:

| | prima | dopo |
|---|---|---|
| scostamento mediano | 2.347 mm | **0.027 mm** |
| scostamento medio | 2.538 mm | 0.995 mm |
| p90 | 5.616 mm | 3.850 mm |
| feature costruite | 12 | 15 |

Sul TAISER la mediana passa da 2.017 a **0.017 mm**, la media da 2.193 a 0.647.
Il p90 resta sopra il millimetro su entrambe: è il resto del repertorio — le
colonnine sono prismi e non hanno i loro raccordi — e la tavola continua a dirlo.

Nello stesso giro il confronto ha smesso di mentire sulle cavità: misurava la
distanza dal solo prisma esterno, quindi un punto sul fondo interno risultava
lontano quanto è spesso il fondo. Ora `_distance_to_body` conta prisma, cavità e
cupole.

### La pagina si legge senza essere del mestiere (FASE 12)

Prova su una persona che non ha mai visto il progetto: sette pannelli numerati,
sette pulsanti «Esegui» in un ordine da conoscere, e un vocabolario — provenance,
registro delle quote, ambiguità, feature non ricostruibili, scostamento p90,
`c1_cupola1_semiasse_x` — che è quello giusto per chi il pezzo lo fabbrica e muto
per tutti gli altri. Il risultato era che *non si capiva se le cose fossero andate
bene*, che è l'unica cosa che si vuole sapere aprendo l'app.

La pagina ha ora due letture, e nessuna delle due nasconde niente all'altra.

**Normale.** Un pulsante — `Avvia` — che esegue i quattro passaggi in fila (sono
sempre negli stessi quattro, in quest'ordine: non è una scelta da chiedere, è una
sequenza da eseguire), e sotto un riquadro **«Com'è andata»** in italiano comune:

> Il file contiene 6 pezzi e 33 dettagli (fori, cavità, curve).
> Ne ho ricostruiti 9 su 33; 12 smussi, 4 forme libere, 4 asole e altri 2 tipi
> restano fuori dal modello, segnati sul disegno.
> Il modello ricalca il file di partenza: si discosta di 0,027 mm nella metà dei
> punti misurati.

Poi due colonne — *nel modello* / *fuori dal modello* — il 3D, la tavola, e
quattro file con il loro nome («Il disegno tecnico», «Il modello 3D») invece di
venti path allo stesso livello.

**Tecnica.** L'interruttore in alto riapre tutto: i quattro passaggi singoli con i
log, la tabella completa delle quote, il registro di ogni file, le varianti.

Tre scelte che valgono più delle altre:

1. **Le frasi le scrive il backend** (`parts/auto/summary.py`), non il frontend:
   le parole con cui si descrive il lavoro sono parte del lavoro. E rileggono i
   file del run — non sono una seconda verità accanto ai numeri. Un test verifica
   che riepilogo e tavola contino le stesse feature: se divergessero, uno dei due
   mentirebbe e non si saprebbe quale.
2. **Ogni domanda ha una formulazione in chiaro** (`Decision.plain`), che è la
   prima riga che si legge; «Perché te lo sto chiedendo» apre quella tecnica con
   le misure che l'hanno fatta nascere. Una domanda che non si capisce non è una
   domanda.
3. **Lo scostamento è detto anche a parole.** «mediana 0.027 mm» è la cifra giusta
   e non dice niente a chi non sa rispetto a cosa. Il giudizio («ricalca», «è una
   semplificazione», «è una semplificazione grossolana») la accompagna, non la
   sostituisce — e non basta uno scostamento minimo per dire «fedele»: se metà
   dei dettagli è rimasta fuori, il riepilogo dice «ricostruito in parte», perché
   lo scostamento pesa i *punti* della mesh e una cupola fitta di triangoli lo
   tiene basso da sola.

### Ogni elemento del modello in tavola (FASE 13)

Confronto fra il modello e la sua tavola sulla mesh del progetto: il disegno
mancava di parti che il pezzo ha. Quattro cause, tutte chiuse; ognuna con il suo
test in `tests/`.

1. **Le pareti fuse col raccordo di base non si misuravano.** La tassellazione
   salda la faccia esterna al raccordo: la patch non è più un piano e l'analisi la
   scartava. Senza pareti la cavità veniva tagliata a *tutto spessore* — 80.000
   invece di 71.274 × 41.624 — e il foro Ø3.005 che attraversa la parete destra
   non trovava materiale da asportare: sulla tavola non c'era nessun foro.
   `_read_outer_faces` legge ora anche la patch non piana il cui ingombro tocca il
   contorno (`soft_outer`), e — per la faccia che una sporgenza nasconde, come la
   parete destra dietro la cupola — il piano più esterno che copre la sezione e
   sta **fuori dalla cavità** (`_read_outer_faces_dietro`). Spessori misurati:
   X-min 1.293, X-max 1.293, Y 2.188, fondo 1.634 — gli stessi di
   `docs/lost+found_design.md` §5-B, ritrovati da un codice che del TAISER non sa
   niente. La cavità porta ora la sua **scatola in coordinate assolute**
   (`cavity_box`), che il costruttore usa al posto delle pareti ricavate
   dall'ingombro: è l'unico modo perché una sporgenza che gonfia l'ingombro non
   sposti la tasca.

2. **Le asole sparivano.** Scegliendo «asole» la decisione, non si costruivano —
   si dichiaravano soltanto; scegliendo «fori» diventavano cerchi. Ora la
   ricetta porta l'asola com'è: larghezza, lunghezza, **direzione lunga** (il
   vettore fra le due testate, misurato), profondità. `build_script.py` taglia lo
   stadio vero — due cilindri e il corpo che li unisce. Le 4 asole del coperchio
   (7.206 × 4.592 e 7.561 × 4.764) sono nel modello e sulle viste.

3. **I vani rettangolari non esistevano per l'analisi.** Un'apertura o una tasca
   rettangolare non ha cilindri che la dimostrino: il vano del connettore sulla
   parete frontale (6.467 × 4.005 × 2.188), la tasca laterale sinistra
   (19.79 × 11.005, 0.603 di profondità dal lato cavità) e la tasca grande del
   coperchio (12.03 × 12.865 × 0.502) non erano né fori né asole né *dichiarati* —
   sparivano fra la misura e la tavola. `_read_windows` li riconosce da quattro
   piani che formano un canale, ne misura le tre quote, e il costruttore li taglia
   come scatole misurate. In `SEZIONE B-B` il vano del connettore attraversa
   finalmente la parete.

4. **Le superfici dichiarate avevano solo il rettangolo d'ingombro.** Ora ne
   portano il **contorno vero**: il bordo della patch, proiettato sulle tre viste
   (`_contorni_omessi` in `parts/auto/plugin.py`). Sulla scatola si riconoscono così
   il raccordo di base, le due nervature, le aperture della cupola, il rilievo
   dentro la tasca; sul coperchio le tasche ellittiche e le calotte. Il layer resta
   `OMESSO` (viola): la lettura non cambia — *questo il modello non ce l'ha* — ma
   la forma sì.

In più, una trappola d'ambiente che impediva alla pipeline di girare sul Mac:
l'interprete embedded di FreeCAD apre la console in ascii e non guarda
`PYTHONIOENCODING`; uno script che stampa «cavità» moriva a metà e il sentinella
non arrivava. `core/freecad/script.py` riapre stdout in UTF-8 nel prologo che ogni
script importa.

**Verifica** (mesh `input/model.obj`, FreeCAD 1.1.3, 11 fogli A3): 44 quote,
scostamento mediana 0.0117 / media 0.4137 / p90 1.9503 mm. Il foro Ø3.005 si vede
in `VISTA LATERALE DESTRA` e in `SEZIONE C-C`; il vano del connettore in
`SEZIONE B-B`; le 4 asole del coperchio in pianta e in `SEZIONE C-C`; la tasca del
coperchio in pianta. Sulla tavola restano in viola — col loro contorno — solo le
superfici che il repertorio non costruisce: raccordo di base, nervature, aperture
della cupola, archetti spaiati delle colonnine.

**Resta aperto:** le asole di serraggio nelle colonnine. Le loro testate sono
ellittiche (Tinkercad scala in modo non uniforme) e il fit circolare le legge
R1.99 invece di R0.81: costruirle da quel raggio inventerebbe un foro largo il
doppio. Restano dichiarate, col contorno vero; per costruirle serve un fit
ellittico delle testate — lo stesso lavoro che la decisione A aveva escluso per
il raccordo di base.

### Aperto sulla web app
1. **Immagine Docker mai costruita davvero.** FreeCAD conda-forge è stato verificato
   installandolo direttamente (è quel che fa il Dockerfile), ma nel container di
   sviluppo non c'era un demone Docker: `docker build` va eseguito una volta.
2. **Peso dei run: 47 MB**, di cui 44 MB di STL a tassellazione fine. L'anteprima usa
   `preview.stl` (1.6 MB), ma la cartella del run non viene mai ripulita.
3. ~~**Build automatica mai girata sotto FreeCAD.**~~ Fatto in FASE 8: con FreeCAD
   1.1.3 da conda-forge la pipeline `auto` gira intera su `input/model.obj` —
   analisi 0.2 s, build 0.3 s (6 corpi, STEP + STL), tavola 1.0 s (11 fogli A3,
   34 viste proiettate), confronto 0.1 s.
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
