# LORE

## Che oggetto è
Un contenitore in due pezzi — scatola e coperchio — che ha tutte le caratteristiche di un
**box per elettronica**: cavità rettangolare, 4 colonnine d'angolo forate per viti, coperchio
con 4 asole corrispondenti, un'asola passante su una parete (connettore), un foro Ø3 su un'altra
(LED o pressacavo), e una vistosa **cupola cava** sul fianco destro con due aperture — plausibilmente
alloggiamento di un sensore, di un altoparlante o di un'antenna.

## Da dove viene
Modellato in **Tinkercad** e esportato in OBJ. Questo spiega quasi tutte le stranezze geometriche
del pezzo, ed è la chiave per leggerlo:

- Tinkercad compone forme a partire da primitive **scalate in modo non uniforme**. Da qui gli
  spessori di parete asimmetrici (1.293 contro 2.188) e i raccordi **ellittici** invece che circolari:
  non sono scelte di progetto, sono l'effetto collaterale di uno scaling.
- I valori non sono mai "tondi" (1.634, 2.188, 1.293, 26.999) perché nessuno li ha mai digitati:
  sono il risultato di trascinamenti col mouse.

## Il trabocchetto della tavola
La tavola TinkerCAD è stata presentata come «fonte di verità per tutte le misure esatte».
**Non lo è.** Le sue 6 quote coincidono al millesimo col bounding box della mesh, e la nota in calce
lo ammette: sono quote «misurabili direttamente dal modello OBJ». La tavola è un *derivato* della
mesh, non un documento di progetto indipendente. Documenta le tre dimensioni d'ingombro per pezzo e
tace su tutto il resto — incluse feature grosse e visibili dall'esterno come la cupola.

Conseguenza operativa: **non esiste, in questo progetto, una fonte di quote nominali.** Ogni valore
"da progetto" va deciso, non trovato. Per questo `docs/lost+found_design.md` distingue sempre
*misurato* da *proposto*, e per questo le ambiguità A–G vanno chiuse dal committente prima di
scrivere una riga di codice di modellazione.
