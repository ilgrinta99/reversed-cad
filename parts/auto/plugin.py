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
from core.drafting import tavola
from core.freecad.runner import run_script
from core.mesh.ambiguity import read as read_ambiguities
from core.mesh.analysis import analyze
from core.mesh.obj import load_obj
from core.mesh.sections import cross_section, polygon_area
from core.plugin import RunContext, StepResult, registry
from core.provenance import DecisionSet, Registry
from parts.auto import drawing

_HERE = Path(__file__).parent
_CORE_DRAFTING = Path(__file__).resolve().parents[2] / "core" / "drafting"
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
        """Tavola quotata completa: viste ortogonali, sezioni, assonometria, registro.

        La geometria delle viste è proiettata da FreeCAD (`TechDraw.project`, HLR
        esatto sui B-rep) e attraversa il confine come JSON di spigoli 2D;
        l'impaginazione, la quotatura e i tre formati di uscita sono Python puro in
        `core/drafting/`. È il motivo per cui la tavola si può ricomporre senza
        rifare la proiezione, e per cui il compositore è provabile senza FreeCAD.

        Sulle viste ortogonali di ogni corpo viene ricalcato il profilo vero della
        mesh, sezionata a metà: è quello che permette di vedere a colpo d'occhio
        quanto il prisma ricostruito somiglia al pezzo.
        """
        recipe = json.loads((ctx.run_dir / RECIPE_FILE).read_text()) \
            if (ctx.run_dir / RECIPE_FILE).is_file() else self._recipe(ctx, registry_)
        analysis = json.loads((ctx.run_dir / ANALYSIS_FILE).read_text())

        proiezioni = self._proietta(ctx, recipe)
        fogli = drawing.fogli(
            recipe, analysis, registry_, proiezioni,
            sorgente=recipe.get("source", ctx.mesh_path.name),
            contorni=_contorni_mesh(ctx.mesh_path, recipe),
            decisioni=self._decisioni_prese(ctx),
            scostamento=_scostamento(ctx.run_dir),
        )
        artefatti = tavola.componi(fogli, proiezioni, ctx.run_dir, "drawing",
                                   titolo_pdf="Modello ricostruito dalla mesh")
        ctx.log(f"tavola: {len(fogli)} fogli A3, {len(proiezioni)} viste proiettate, "
                f"PDF + DXF + {sum(1 for k in artefatti if k.startswith('svg'))} SVG")
        return StepResult(
            artifacts=artefatti,
            metrics={"fogli": len(fogli), "viste": len(proiezioni),
                     "corpi": len(recipe["bodies"])},
        )

    def _proietta(self, ctx: RunContext, recipe: dict) -> dict:
        """Chiede a FreeCAD la proiezione di ogni vista e rilegge il JSON.

        I solidi sono quelli scritti dalla build: la tavola descrive il modello
        costruito, non la ricetta che lo ha generato. Se mancano, lo step di build
        non è passato di qui, e disegnare una tavola sarebbe un falso.
        """
        shapes = {"assieme": ctx.run_dir / "model.step"}
        for body in recipe["bodies"]:
            shapes[body["key"]] = ctx.run_dir / f"{drawing.sanitize(body['name'])}.step"
        mancanti = [str(p.name) for p in shapes.values() if not p.is_file()]
        if mancanti:
            raise FileNotFoundError(
                "la tavola si disegna sul solido costruito, e questi file non ci sono: "
                f"{', '.join(mancanti)}. Eseguire prima lo step «build»."
            )

        spec = ctx.artifact("views.json")
        spec.write_text(json.dumps(
            {"shapes": {k: str(v) for k, v in shapes.items()},
             "views": drawing.viste_richieste(recipe)}, indent=2))
        fuori = ctx.run_dir / "projection.json"
        run_script(_CORE_DRAFTING / "project_script.py", [str(spec), str(fuori)],
                   timeout_s=ctx.timeout_s, on_line=ctx.log)
        return json.loads(fuori.read_text())["views"]

    def _decisioni_prese(self, ctx: RunContext) -> list[dict]:
        if ctx.decisions is None:
            return []
        return [{"id": d.id, "chosen": d.chosen} for d in ctx.decisions]

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
                # Prefisso delle quote di questo corpo nel registro: e' con questo
                # che la tavola risale al numero da scrivere accanto a una linea.
                "key": key,
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


#: Vista -> (asse tagliato, assi che restano). Gli assi residui di `cross_section`
#: escono già nell'ordine della vista: sezione su Z ⇒ (X, Y) ⇒ pianta.
_PIANI = {"pianta": (2, (0, 1)), "prospetto": (1, (0, 2)), "laterale": (0, (1, 2))}


def _contorni_mesh(mesh_path: Path, recipe: dict) -> dict[str, dict[str, list]]:
    """Profilo reale di ogni corpo nelle tre viste, sezionando la mesh a metà.

    Serve la mesh intera perché la sezione taglia i triangoli: il contorno del
    corpo è quello con l'area più grande fra quelli che il piano produce dentro il
    suo ingombro. È geometria di confronto, non del modello: sulla tavola ha uno
    stile e un layer suoi.
    """
    try:
        mesh = load_obj(mesh_path)
    except (OSError, ValueError):
        return {}
    fuori: dict[str, dict[str, list]] = {}
    for body in recipe["bodies"]:
        origin = np.asarray([float(v) for v in body["origin"]])
        size = np.asarray([float(v) for v in body["size"]])
        per_vista: dict[str, list] = {}
        for nome, (asse, residui) in _PIANI.items():
            contours = cross_section(mesh.vertices, mesh.faces, asse,
                                     origin[asse] + size[asse] / 2.0)
            lo = origin[list(residui)] - 1e-6
            hi = origin[list(residui)] + size[list(residui)] + 1e-6
            dentro = [c for c in contours
                      if (c.min(axis=0) >= lo).all() and (c.max(axis=0) <= hi).all()]
            if dentro:
                per_vista[nome] = [[float(a), float(b)]
                                   for a, b in max(dentro, key=polygon_area)]
        if per_vista:
            fuori[body["key"]] = per_vista
    return fuori


def _scostamento(run_dir: Path) -> dict | None:
    """Statistica del confronto, se il run l'ha già prodotta. Non si ricalcola qui."""
    path = run_dir / "deviation.json"
    if not path.is_file():
        return None
    try:
        stats = json.loads(path.read_text()).get("stats")
    except (OSError, ValueError):
        return None
    return {k: float(v) for k, v in stats.items()} if isinstance(stats, dict) else None


plugin = registry.register(AutoPart())
