"""Analisi automatica: il pezzo è quello che la mesh dimostra di essere.

Gli altri plugin di `parts/` sanno in anticipo che pezzo stanno guardando: hanno
un elenco di quote e un catalogo di ambiguità scritti prima di vedere il file.
Questo no. Qui l'unica specifica è la mesh caricata: `measure()` la misura
(`core.mesh.analysis`), ne ricava le quote che esistono davvero e le domande che
quella geometria solleva (`core.mesh.ambiguity`), e le restituisce al runner.
Due mesh diverse producono due tabelle diverse e due elenchi di domande diversi —
che è tutto il punto.

Il ricostruttore parametrico è volutamente elementare e dichiara i propri limiti:
prisma esterno, raccordo verticale, cavità, fori cilindrici. Quello che non sa
fare non lo approssima: lo elenca fra le feature non ricostruibili, e diventa una
domanda. Il confronto modello ↔ mesh misura poi quanto è costato ignorarlo.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from core.compare import deviation
from core.freecad.runner import run_script
from core.mesh.ambiguity import read as read_ambiguities
from core.mesh.analysis import analyze
from core.mesh.obj import load_obj
from core.mesh.sections import cross_section, polygon_area
from core.plugin import RunContext, StepResult, registry
from core.provenance import DecisionSet, Registry

_HERE = Path(__file__).parent
ANALYSIS_FILE = "analysis.json"
RECIPE_FILE = "recipe.json"


class AutoPart:
    id = "auto"
    name = "Analisi automatica della mesh"
    description = (
        "Nessun pezzo da scegliere: la mesh viene misurata così com'è. Le quote "
        "e le ambiguità nascono dall'analisi di questo file, non da un catalogo "
        "deciso prima."
    )
    wired = True

    # -- dichiarazioni -----------------------------------------------------

    def declare_dimensions(self) -> Registry:
        """Vuoto, e non è una mancanza.

        Dichiarare quote prima di aver visto la mesh significherebbe sapere già
        che pezzo è. Il registro si riempie in `measure()`, con quello che la
        mesh dimostra.
        """
        return Registry()

    def declare_decisions(self) -> DecisionSet:
        """Vuoto per lo stesso motivo: le ambiguità sono di questa mesh."""
        return DecisionSet()

    # -- step --------------------------------------------------------------

    def measure(self, ctx: RunContext, registry_: Registry) -> StepResult:
        analysis = analyze(ctx.mesh_path, log=ctx.log)
        reading = read_ambiguities(analysis)

        report = ctx.artifact(ANALYSIS_FILE)
        report.write_text(json.dumps(analysis.to_dict(), indent=2, ensure_ascii=False))

        buildable = [f for f in analysis.features if f.buildable]
        blocked = [f for f in analysis.features if not f.buildable]
        ctx.log(f"{len(reading.registry)} quote misurate, "
                f"{len(reading.decisions)} ambiguità da risolvere")
        for decision in reading.decisions:
            ctx.log(f"  ambiguità {decision.id}: {decision.title}")

        return StepResult(
            artifacts={"analysis": report},
            metrics={
                "vertices": int(len(analysis.mesh)),
                "triangles": int(len(analysis.mesh.faces)),
                "corpi": len(analysis.bodies),
                "quote": len(reading.registry),
                "ambiguita": len(reading.decisions),
                "feature_ricostruibili": len(buildable),
                "feature_non_ricostruibili": len(blocked),
            },
            notes=reading.notes,
            dimensions=reading.registry,
            decisions=reading.decisions,
        )

    def build(self, ctx: RunContext, registry_: Registry) -> StepResult:
        recipe = self._recipe(ctx, registry_)
        path = ctx.artifact(RECIPE_FILE)
        path.write_text(json.dumps(recipe, indent=2, ensure_ascii=False))
        params = ctx.artifact("params.json")
        params.write_text(json.dumps(registry_.values(), indent=2, ensure_ascii=False))

        ctx.log(f"costruzione di {len(recipe['bodies'])} corpi")
        run_script(_HERE / "build_script.py", [str(path), str(ctx.run_dir)],
                   timeout_s=ctx.timeout_s, on_line=ctx.log)
        return StepResult(
            artifacts={"recipe": path, "params": params,
                       "step": ctx.run_dir / "model.step",
                       "stl": ctx.run_dir / "model.stl"},
            metrics={"corpi": len(recipe["bodies"]),
                     "fori": sum(len(b["bores"]) for b in recipe["bodies"])},
        )

    def draw(self, ctx: RunContext, registry_: Registry) -> StepResult:
        """Tre viste quotate in SVG. Nessun FreeCAD nel percorso di anteprima.

        In pianta, sopra il rettangolo di ingombro, viene ricalcato il contorno
        vero della mesh a mezza altezza: è quello che permette di vedere a colpo
        d'occhio quanto il prisma ricostruito somiglia al pezzo, senza aspettare
        la build e il confronto.
        """
        recipe = json.loads((ctx.run_dir / RECIPE_FILE).read_text()) \
            if (ctx.run_dir / RECIPE_FILE).is_file() else self._recipe(ctx, registry_)
        out = ctx.artifact("drawing.svg")
        out.write_text(_three_view_svg(recipe, _plan_outlines(ctx.mesh_path, recipe)))
        ctx.log(f"tavola SVG scritta: {len(recipe['bodies'])} corpi, quote in mm")
        return StepResult(artifacts={"svg": out})

    def compare(self, ctx: RunContext, model_path: Path) -> StepResult:
        """Distanza fra i punti della mesh e la superficie del solido costruito.

        Il solido è un'unione di prismi: la distanza punto → superficie è
        analitica, e non serve FreeCAD per calcolarla. Dove il modello ignora una
        feature — una cupola, un'asola — lo scostamento salta fuori qui, con il
        suo valore: è il modo in cui una semplificazione dichiarata resta
        verificabile invece che nascosta.
        """
        mesh = load_obj(ctx.mesh_path)
        recipe = json.loads((ctx.run_dir / RECIPE_FILE).read_text())
        samples = _surface_samples(mesh)
        distances = _distance_to_recipe(samples, recipe)

        out = ctx.artifact("deviation.json")
        points = [[float(p[0]), float(p[1]), float(p[2]), float(d)]
                  for p, d in zip(samples, distances)]
        stats = deviation.write(out, points, {
            body["name"]: {
                "stats": deviation.stats_from(
                    _distance_to_box(samples, np.asarray(body["origin"]),
                                     np.asarray(body["origin"]) + np.asarray(body["size"]))),
                "campionati": len(points), "totali": len(points), "worst": [],
            }
            for body in recipe["bodies"]
        })
        for key, value in stats.items():
            ctx.log(f"{key}: {value:.4f}")
        return StepResult(
            artifacts={"deviation": out},
            metrics={k: round(v, 4) for k, v in stats.items()},
            notes=["Lo scostamento comprende le feature che il ricostruttore non "
                   "rappresenta: è la misura di quanto costa la semplificazione, "
                   "non un errore nascosto."],
        )

    # -- ricetta -----------------------------------------------------------

    def _recipe(self, ctx: RunContext, registry_: Registry) -> dict:
        """Traduce quote approvate e analisi in istruzioni per il costruttore.

        `registry_.values()` è il cancello: se una quota non è né misurata né
        approvata, qui si solleva e la build non parte. Le posizioni (dove sta un
        foro, dove comincia un corpo) restano quelle misurate e sono in
        `analysis.json` con il nome di chi le ha prodotte: in tabella stanno le
        quote su cui misura e uso *possono* divergere.
        """
        if ctx.chosen("superfici_libere") == "fermati":
            raise ValueError(
                "decisione «superfici_libere» = fermati: la mesh contiene superfici "
                "che il ricostruttore parametrico non rappresenta, e si è scelto di "
                "non costruire un solido che le ignori."
            )
        values = registry_.values()
        analysis = json.loads((ctx.run_dir / ANALYSIS_FILE).read_text())

        wanted = analysis["bodies"]
        if ctx.chosen("corpi") == "principale":
            wanted = wanted[:1]
            ctx.log("decisione «corpi» = principale: gli altri corpi restano fuori")
        slots_as_bores = any(ctx.chosen(f"{b['key']}_asole") == "fori"
                             for b in analysis["bodies"])

        bodies = []
        for body in wanted:
            key = body["key"]
            size = [values.get(f"{key}_ingombro_{axis}") for axis in "xyz"]
            if any(v is None for v in size):
                continue
            bodies.append({
                "name": body["name"],
                "origin": body["bbox_min"],
                "size": size,
                "fillet": _fillet(values, key),
                "cavity": _cavity(values, body, key),
                "bores": _bores(values, analysis, key, slots_as_bores),
            })
        if not bodies:
            raise ValueError("nessun corpo con ingombro approvato: niente da costruire")
        return {"bodies": bodies, "source": str(ctx.mesh_path.name)}


def _fillet(values: dict[str, float], key: str) -> float | None:
    """Raggio del raccordo verticale, se una quota lo definisce senza ambiguità."""
    radii = [v for k, v in values.items()
             if k.startswith(f"{key}_raccordo_") and k.endswith("_r")]
    return min(radii) if radii else None


def _cavity(values: dict[str, float], body: dict, key: str) -> dict | None:
    depth = values.get(f"{key}_cavita_profondita")
    floor = values.get(f"{key}_fondo_spessore")
    if depth is None or floor is None:
        return None
    walls = {side: values[f"{key}_parete_{side.split('-')[0].lower()}_{side.split('-')[1]}"]
             for side in body["walls"]
             if f"{key}_parete_{side.split('-')[0].lower()}_{side.split('-')[1]}" in values}
    if not walls:
        return None
    return {"depth": depth, "floor": floor, "walls": walls}


def _bores(values: dict[str, float], analysis: dict, key: str,
           slots_as_bores: bool) -> list[dict]:
    out = []
    body = next((b for b in analysis["bodies"] if b["key"] == key), None)
    if body is None:
        return out
    for feature in analysis["features"]:
        if feature["body"] != body["name"]:
            continue
        if feature["kind"] == "asola" and not slots_as_bores:
            continue
        if feature["kind"] not in ("foro", "asola"):
            continue
        index = feature["label"].rsplit(" ", 1)[-1]
        prefix = f"{key}_{feature['kind']}{index}"
        diameter = values.get(f"{prefix}_diametro") or values.get(f"{prefix}_larghezza")
        depth = values.get(f"{prefix}_profondita")
        params = feature["params"]
        if diameter is None or depth is None or "centro_x" not in params:
            continue
        out.append({
            "axis": feature["note"].split()[-1],
            "diameter": diameter,
            "depth": depth,
            "center": [params["centro_x"], params["centro_y"], params["centro_z"]],
        })
    return out


# -- geometria di supporto --------------------------------------------------


def _surface_samples(mesh) -> np.ndarray:
    """Vertici più baricentri: un vertice di spigolo da solo misura zero ovunque."""
    if len(mesh.faces) == 0:
        return mesh.vertices
    centroids = mesh.vertices[mesh.faces].mean(axis=1)
    return np.vstack([mesh.vertices, centroids])


def _distance_to_box(points: np.ndarray, low: np.ndarray, high: np.ndarray) -> np.ndarray:
    centre = (low + high) / 2.0
    half = (high - low) / 2.0
    q = np.abs(points - centre) - half
    outside = np.linalg.norm(np.maximum(q, 0.0), axis=1)
    inside = np.minimum(np.max(q, axis=1), 0.0)
    return np.abs(outside + inside)


def _distance_to_recipe(points: np.ndarray, recipe: dict) -> np.ndarray:
    """Distanza dalla superficie più vicina fra quelle dei corpi costruiti."""
    best = None
    for body in recipe["bodies"]:
        low = np.asarray(body["origin"], dtype=float)
        high = low + np.asarray(body["size"], dtype=float)
        d = _distance_to_box(points, low, high)
        best = d if best is None else np.minimum(best, d)
    return best if best is not None else np.zeros(len(points))


def _plan_outlines(mesh_path: Path, recipe: dict) -> dict[str, list]:
    """Contorno reale in pianta di ogni corpo, a mezza altezza.

    Serve la mesh intera perché la sezione taglia i triangoli: il contorno esterno
    è quello con l'ingombro più grande fra quelli che il piano produce.
    """
    try:
        mesh = load_obj(mesh_path)
    except (OSError, ValueError):
        return {}
    outlines: dict[str, list] = {}
    for body in recipe["bodies"]:
        origin = [float(v) for v in body["origin"]]
        size = [float(v) for v in body["size"]]
        contours = cross_section(mesh.vertices, mesh.faces, 2, origin[2] + size[2] / 2.0)
        inside = [c for c in contours
                  if (c.min(axis=0) >= np.array(origin[:2]) - 1e-6).all()
                  and (c.max(axis=0) <= np.array(origin[:2]) + np.array(size[:2]) + 1e-6).all()]
        if not inside:
            continue
        outer = max(inside, key=polygon_area)
        outlines[body["name"]] = [[float(x), float(y)] for x, y in outer]
    return outlines


def _three_view_svg(recipe: dict, outlines: dict[str, list] | None = None) -> str:
    """Fronte, lato e pianta dell'ingombro di ogni corpo, quotati."""
    margin, gap = 30.0, 25.0
    outlines = outlines or {}
    rows, width, height = [], 0.0, margin
    for body in recipe["bodies"]:
        length, depth, tall = (float(v) for v in body["size"])
        rows.append((body["name"], length, depth, tall, height, body["origin"]))
        width = max(width, margin * 2 + length + gap + depth)
        height += tall + gap + depth + gap * 2
    height += margin

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.1f}mm" '
        f'height="{height:.1f}mm" viewBox="0 0 {width:.1f} {height:.1f}">',
        '<style>text{font:3.5px sans-serif;fill:#111}'
        '.o{fill:none;stroke:#111;stroke-width:0.35}'
        '.d{stroke:#111;stroke-width:0.18}'
        '.mesh{fill:none;stroke:#c33;stroke-width:0.25;stroke-dasharray:1.2 0.8}</style>',
        f'<rect x="0" y="0" width="{width:.1f}" height="{height:.1f}" fill="#fff"/>',
    ]
    for name, length, depth, tall, top, origin in rows:
        parts.append(f'<text x="{margin:.2f}" y="{top - 4:.2f}">{name}</text>')
        outline = outlines.get(name)
        if outline:
            # La pianta sta sotto le due viste in alzato; il contorno va portato
            # nel riferimento del foglio, con Y verso il basso come in SVG.
            base_y = top + tall + gap
            points = " ".join(
                f"{margin + (x - float(origin[0])):.2f},"
                f"{base_y + depth - (y - float(origin[1])):.2f}"
                for x, y in outline
            )
            parts.append(f'<polygon class="mesh" points="{points}"/>')
        for x, y, w, h, label in (
            (margin, top, length, tall, "Fronte"),
            (margin + length + gap, top, depth, tall, "Lato"),
            (margin, top + tall + gap, length, depth, "Pianta (tratteggio: mesh)"),
        ):
            parts.append(f'<rect class="o" x="{x:.2f}" y="{y:.2f}" '
                         f'width="{w:.2f}" height="{h:.2f}"/>')
            parts.append(f'<text x="{x:.2f}" y="{y - 1:.2f}">{label}</text>')
            quota = y + h + 8
            parts.append(f'<line class="d" x1="{x:.2f}" y1="{quota:.2f}" '
                         f'x2="{x + w:.2f}" y2="{quota:.2f}"/>')
            parts.append(f'<text x="{x + w / 2:.2f}" y="{quota - 1:.2f}" '
                         f'text-anchor="middle">{w:.2f}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


plugin = registry.register(AutoPart())
