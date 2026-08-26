"""Il run raccontato in italiano comune, dai file che il run ha prodotto.

La pipeline produce numeri esatti e li nomina con precisione: `c1_cupola1_
semiasse_x`, «feature non ricostruibili», «scostamento p90». Sono i nomi giusti
per chi il pezzo lo deve fabbricare, e restano dove sono. Ma sono anche il motivo
per cui chi apre l'app per la prima volta non capisce se le cose sono andate bene.

Questo modulo non calcola niente di nuovo: rilegge `analysis.json`,
`recipe.json` e `deviation.json` e ne ricava tre frasi e qualche riga d'elenco.
Se un file non c'è, la frase corrispondente non c'è — non si inventa uno stato.

Sta in `parts/auto/` e non in `core/` perché legge la *ricetta*, che è il formato
del ricostruttore automatico; e in Python perché le parole con cui si descrive il
lavoro sono parte del lavoro, non della presentazione.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from parts.auto import drawing

#: Sotto questo scostamento mediano il modello ricalca la mesh: è la tolleranza
#: di progetto sulle feature piane (docs/CONVENTIONS.md).
BENE_MM = 0.10

#: Sopra questo scostamento mediano il modello è un'approssimazione grossolana e
#: va detto senza giri di parole: mezzo millimetro è la soglia con cui il progetto
#: giudica una superficie curva ricostruita male.
MALE_MM = 0.50

#: Sotto questa frazione di dettagli ricostruiti il modello resta «parziale» anche
#: con uno scostamento minimo. Le due cose misurano cose diverse: lo scostamento
#: pesa i *punti* della mesh, quindi una cupola fitta di triangoli lo tiene basso
#: anche se dieci smussi sono rimasti fuori. Dirlo «fedele» sarebbe vero e
#: fuorviante insieme.
COPERTURA_PIENA = 0.80

#: Come si chiama, in italiano comune, ogni feature del repertorio.
NOMI = {
    "prisma": ("corpo", "corpi"),
    "cavita": ("cavità", "cavità"),
    "cupola": ("cupola", "cupole"),
    "foro": ("foro", "fori"),
    "asola": ("asola", "asole"),
    "libera": ("forma libera", "forme libere"),
    "sfera": ("calotta sferica", "calotte sferiche"),
    "cilindro": ("superficie cilindrica", "superfici cilindriche"),
    "arco": ("smusso", "smussi"),
}


def _nome(kind: str, quanti: int) -> str:
    singolare, plurale = NOMI.get(kind, (kind, kind))
    return singolare if quanti == 1 else plurale


def _leggi(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def _nel_modello(feature: dict, recipe: dict | None) -> bool:
    """Stessa domanda che si fa la tavola: il solido porta questa feature?

    Duplicarne la risposta sarebbe il modo più sicuro di farle divergere — il
    riepilogo direbbe «ricostruita» e il disegno «mancante» —, quindi la si chiede
    a chi la sa dare. Qui si gestisce solo il caso in cui la ricetta non c'è
    ancora: prima della build nessuna feature è nel modello, ma `buildable` dice
    già quali ci finirebbero.
    """
    if recipe is None:
        return bool(feature.get("buildable"))
    return drawing._nel_modello(feature, recipe)


def riassumi(run_dir: Path) -> dict[str, Any]:
    """Tre frasi e due elenchi: cosa c'è nel file, cosa è stato ricostruito, quanto somiglia."""
    analysis = _leggi(run_dir / "analysis.json")
    recipe = _leggi(run_dir / "recipe.json")
    deviation = _leggi(run_dir / "deviation.json")
    if analysis is None:
        return {"stato": "da_analizzare", "frasi": [], "trovato": [], "mancante": []}

    corpi = len(analysis.get("bodies", []))
    features = [f for f in analysis.get("features", []) if f.get("kind") != "prisma"]
    dentro = [f for f in features if _nel_modello(f, recipe)]
    fuori = [f for f in features if not _nel_modello(f, recipe)]

    frasi = [
        f"Il file contiene {corpi} {'pezzo' if corpi == 1 else 'pezzi'} "
        f"e {len(features)} {'dettaglio' if len(features) == 1 else 'dettagli'} "
        f"(fori, cavità, curve).",
    ]
    if recipe is not None:
        frasi.append(
            "Li ho ricostruiti tutti." if not fuori else
            f"Ne ho ricostruiti {len(dentro)} su {len(features)}; "
            f"{_elenco(_conta(fuori))} {'resta' if len(fuori) == 1 else 'restano'} "
            f"fuori dal modello, segnati sul disegno."
        )
    if deviation is not None:
        frasi.append(_frase_scostamento(deviation))

    copertura = len(dentro) / len(features) if features else 1.0
    return {
        "stato": _stato(_mediana(deviation), copertura,
                        recipe is not None, deviation is not None),
        "frasi": frasi,
        "trovato": _conta(dentro),
        "mancante": _conta(fuori),
        "scostamento_mm": _mediana(deviation),
    }


def _elenco(conteggio: list[dict[str, Any]], massimo: int = 3) -> str:
    """«12 smussi, 4 forme libere e altri 2 tipi»: un elenco che sta in una riga."""
    voci = [f"{c['quanti']} {c['nome']}" for c in conteggio[:massimo]]
    resto = len(conteggio) - massimo
    if resto > 0:
        voci.append(f"altri {resto} tipi")
    if len(voci) == 1:
        return voci[0]
    return ", ".join(voci[:-1]) + " e " + voci[-1]


def _stato(mediana: float | None, copertura: float, ha_ricetta: bool,
           ha_confronto: bool) -> str:
    if not ha_ricetta:
        return "analizzato"
    if not ha_confronto or mediana is None:
        return "costruito"
    if mediana > MALE_MM:
        return "grossolano"
    if mediana <= BENE_MM and copertura >= COPERTURA_PIENA:
        return "fedele"
    return "parziale"


def _mediana(deviation: dict | None) -> float | None:
    if not deviation:
        return None
    stats = deviation.get("stats") or {}
    valore = stats.get("mediana_mm")
    return float(valore) if valore is not None else None


def _frase_scostamento(deviation: dict) -> str:
    """Lo scostamento detto in millimetri e in giudizio, non solo in cifre.

    «mediana 0.027 mm» è il numero giusto e non dice niente a chi non sa rispetto
    a cosa. Il giudizio non sostituisce la cifra: la accompagna.
    """
    mediana = _mediana(deviation)
    if mediana is None:
        return "Il confronto con il file di partenza non ha prodotto una misura."
    quanto = f"{mediana:.3f} mm".replace(".", ",")
    if mediana <= BENE_MM:
        return (f"Il modello ricalca il file di partenza: si discosta di {quanto} "
                f"nella metà dei punti misurati.")
    if mediana <= MALE_MM:
        return (f"Il modello è una semplificazione: si discosta di {quanto} nella "
                f"metà dei punti misurati.")
    return (f"Il modello è una semplificazione grossolana: si discosta di {quanto} "
            f"nella metà dei punti misurati.")


def _conta(features: list[dict]) -> list[dict[str, Any]]:
    """Quante feature per tipo, con il nome in italiano comune."""
    conteggio: dict[str, int] = {}
    for f in features:
        conteggio[f.get("kind", "?")] = conteggio.get(f.get("kind", "?"), 0) + 1
    return [{"kind": kind, "quanti": n, "nome": _nome(kind, n)}
            for kind, n in sorted(conteggio.items(), key=lambda kv: -kv[1])]
