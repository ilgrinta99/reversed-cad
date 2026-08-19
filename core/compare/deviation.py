"""Formato comune del confronto modello ↔ mesh.

Un solo schema per tutti i pezzi, così il frontend ha una sola cosa da leggere:

    {
      "stats":  {"media_mm", "mediana_mm", "p90_mm", "p99_mm", "max_mm"},
      "points": [[x, y, z, scostamento_mm], ...],   # riferimento dell'assieme
      "parts":  {"<nome>": {"stats": {...}, "worst": [...], "campionati": n}},
      "soglie_mm": {"piana": 0.10, "curva": 0.50}
    }

I punti portano le coordinate con sé: nessuna dipendenza dall'ordine dei vertici
del file di partenza, che un loader 3D riordina.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Sequence

#: docs/CONVENTIONS.md
SOGLIA_PIANA = 0.10
SOGLIA_CURVA = 0.50

Point = Sequence[float]  # [x, y, z, d]


def stats_from(distances: Iterable[float]) -> dict[str, float]:
    d = sorted(distances, reverse=True)
    if not d:
        return {"media_mm": 0.0, "mediana_mm": 0.0, "p90_mm": 0.0, "p99_mm": 0.0,
                "max_mm": 0.0}
    n = len(d)
    q = lambda f: d[int((1 - f) * (n - 1))]  # noqa: E731 — stessa formula di tools/
    return {
        "media_mm": sum(d) / n,
        "mediana_mm": q(0.50),
        "p90_mm": q(0.90),
        "p99_mm": q(0.99),
        "max_mm": d[0],
    }


def write(path: Path, points: list[Point], parts: dict[str, Any] | None = None) -> dict:
    """Scrive il file nel formato comune e restituisce le statistiche aggregate."""
    report = {
        "stats": stats_from(p[3] for p in points),
        "points": [[round(float(x), 4) for x in p] for p in points],
        "parts": parts or {},
        "soglie_mm": {"piana": SOGLIA_PIANA, "curva": SOGLIA_CURVA},
    }
    path.write_text(json.dumps(report))
    return report["stats"]
