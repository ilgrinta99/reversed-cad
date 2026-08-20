"""Analisi ad hoc di una mesh: che cosa c'è dentro, misurato mesh per mesh.

Questo modulo non sa che pezzo sta guardando, e non deve saperlo. Prende un
triangolato qualsiasi, lo divide in corpi e patch (`core.mesh.patches`) e ne
ricava le quote che quelle patch *dimostrano*:

* ingombro, volume e chiusura di ogni corpo;
* facce esterne, cioè i piani che stanno sul contorno dell'ingombro;
* spessore delle pareti, come distanza fra una faccia esterna e la prima faccia
  che le sta di fronte — non come «lo spessore tipico di una scatola»;
* profondità della cavità, quando esiste un fondo interno;
* arrotondamento degli spigoli, letto da dove le facce piane si fermano;
* fori e asole, dai cilindri riconosciuti;
* superfici libere, che nessuna primitiva elementare spiega;
* simmetria rispetto ai piani mediani e posizione del datum.

Ogni numero che esce da qui porta con sé come è stato ottenuto. Quello che non è
misurabile non viene stimato: viene dichiarato mancante, e diventa una domanda
all'utente (`core.mesh.ambiguity`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from core.mesh.loader import load_mesh
from core.mesh.mesh import Mesh
from core.mesh.patches import Body, Patch, segment

SOURCE = "core/mesh/analysis.py"

#: Una faccia piana è «esterna» se sta sul contorno dell'ingombro entro questo scarto.
OUTER_TOL = 1e-3

#: Area minima perché una patch conti come faccia e non come artefatto di
#: tassellazione. In mm²: sotto, il triangolo è più piccolo del rumore del file.
MIN_FACE_AREA = 1.0

#: Una faccia esterna deve coprire almeno questa frazione della sezione del corpo
#: su quell'asse. Senza il criterio, il labbro di 1.8 mm² sul fondo di una scatola
#: passerebbe per «la faccia sinistra» e tutte le quote che ne discendono —
#: spessore di parete, raccordi — sarebbero misurate rispetto a un dettaglio.
MIN_FACE_FRACTION = 0.05

#: Un cilindro è un foro passante solo se il suo ingombro trasversale arriva a
#: circa un diametro in entrambe le direzioni. Un raccordo di spigolo è anch'esso
#: un pezzo di cilindro, ma copre un quarto di giro: largo un raggio, non due.
BORE_WIDTH_RATIO = 1.6

#: Un arretramento più grande di così rispetto all'ingombro non è un raccordo:
#: è un'altra feature, e chiamarla raccordo sarebbe un'invenzione.
MAX_ROUNDING_FRACTION = 0.25

#: La faccia interna di una parete deve stare davanti a quella esterna per almeno
#: questa frazione della sua estensione. Il fianco di un'asola sta «di fronte»
#: alla parete esterna quanto basta a superare un controllo di sovrapposizione
#: generico, ma non è la faccia interna di quella parete.
MIN_WALL_COVERAGE = 0.5

#: Due testate d'asola non distano più di così, in raggi. Oltre, sono due archi
#: che si somigliano e stanno agli antipodi del pezzo: appaiarli inventerebbe
#: un'asola lunga quanto il pezzo.
MAX_SLOT_GAP_RADII = 4.0

#: Griglia su cui si verifica la simmetria speculare.
SYMMETRY_TOL = 0.01

#: Due quote più vicine di così sono lo stesso numero (mezzo micron, come il registro).
SAME = 5e-4

AXES = ("X", "Y", "Z")


@dataclass(frozen=True)
class Measurement:
    """Una quota misurata, con la prova di dove viene."""

    id: str
    label: str
    value: float
    source: str = SOURCE
    unit: str = "mm"
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "label": self.label, "value": self.value,
                "unit": self.unit, "source": self.source, "note": self.note}


@dataclass(frozen=True)
class Feature:
    """Una feature riconosciuta, con i parametri che la definiscono."""

    kind: str          # prisma | cavita | raccordo | foro | asola | libera
    body: str
    label: str
    params: dict[str, float] = field(default_factory=dict)
    note: str = ""
    #: Se False, il ricostruttore parametrico non sa rappresentarla.
    buildable: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "body": self.body, "label": self.label,
                "params": {k: float(v) for k, v in self.params.items()},
                "note": self.note, "buildable": self.buildable}


@dataclass
class BodyAnalysis:
    """Il risultato della lettura di un corpo."""

    key: str            # prefisso stabile delle quote: c1, c2, …
    name: str
    body: Body
    outer: dict[str, Patch] = field(default_factory=dict)   # "X-min" → patch
    walls: dict[str, float] = field(default_factory=dict)   # "X-min" → spessore
    cavity_floor: float | None = None
    cavity_top: float | None = None
    roundings: list[dict[str, Any]] = field(default_factory=list)
    holes: list[dict[str, Any]] = field(default_factory=list)
    #: Archi cilindrici parziali rimasti spaiati: né fori né testate di asola.
    arcs: list[dict[str, Any]] = field(default_factory=list)
    free_patches: list[Patch] = field(default_factory=list)
    symmetry: dict[str, float] = field(default_factory=dict)

    @property
    def extents(self) -> np.ndarray:
        return self.body.extents


@dataclass
class MeshAnalysis:
    """Tutto ciò che si è potuto misurare, e tutto ciò che non si è potuto."""

    mesh: Mesh
    bodies: list[BodyAnalysis]
    measurements: list[Measurement]
    features: list[Feature]
    notes: list[str] = field(default_factory=list)

    def measurement(self, dim_id: str) -> Measurement | None:
        for m in self.measurements:
            if m.id == dim_id:
                return m
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "vertices": int(len(self.mesh)),
            "triangles": int(len(self.mesh.faces)),
            "bodies": [
                {
                    "key": b.key,
                    "name": b.name,
                    "extents": [float(x) for x in b.extents],
                    "bbox_min": [float(x) for x in b.body.bbox_min],
                    "bbox_max": [float(x) for x in b.body.bbox_max],
                    "volume": b.body.volume,
                    "area": b.body.area,
                    "closed": b.body.closed,
                    "patches": len(b.body.patches),
                    "free_patches": len(b.free_patches),
                    "walls": dict(b.walls),
                    "symmetry": dict(b.symmetry),
                }
                for b in self.bodies
            ],
            "measurements": [m.to_dict() for m in self.measurements],
            "features": [f.to_dict() for f in self.features],
            "notes": list(self.notes),
        }


# -- ingresso ---------------------------------------------------------------


def analyze(path_or_mesh, *, max_bodies: int = 8, log=lambda msg: None) -> MeshAnalysis:
    """Misura una mesh qualsiasi. Nessun parametro dipende dal pezzo."""
    mesh = path_or_mesh if isinstance(path_or_mesh, Mesh) else load_mesh(path_or_mesh)
    log(f"mesh {mesh.format.upper() or '?'}: {len(mesh)} vertici, "
        f"{len(mesh.faces)} triangoli")

    bodies = segment(mesh, min_area=0.05)
    log(f"{len(bodies)} corpi connessi, "
        f"{sum(len(b.patches) for b in bodies)} patch di superficie")
    if len(bodies) > max_bodies:
        log(f"i {len(bodies) - max_bodies} corpi più piccoli restano fuori dalla "
            f"tabella delle quote: compaiono comunque fra le feature")

    analyses: list[BodyAnalysis] = []
    measurements: list[Measurement] = []
    features: list[Feature] = []
    notes: list[str] = []

    for index, body in enumerate(bodies[:max_bodies], start=1):
        analysis = BodyAnalysis(key=f"c{index}", name=_unique_name(body, index, bodies),
                                body=body)
        _read_outer_faces(analysis)
        _read_walls(analysis)
        _read_cavity(analysis)
        _read_roundings(analysis)
        _read_holes(analysis, mesh)
        _read_free_patches(analysis)
        _read_symmetry(analysis, mesh)
        analyses.append(analysis)

        measurements.extend(_measurements_of(analysis))
        features.extend(_features_of(analysis))
        log(f"{analysis.name}: ingombro "
            f"{analysis.extents[0]:.3f} × {analysis.extents[1]:.3f} × "
            f"{analysis.extents[2]:.3f} mm, {len(body.patches)} patch, "
            f"{len(analysis.holes)} fori, {len(analysis.free_patches)} superfici libere")

    if len(bodies) > max_bodies:
        notes.append(
            f"{len(bodies)} corpi nella mesh: i primi {max_bodies} per area sono in "
            f"tabella, gli altri no."
        )
    free_total = sum(len(a.free_patches) for a in analyses)
    if free_total:
        notes.append(
            f"{free_total} superfici non riconducibili a piano, cilindro o sfera. "
            f"Non vengono approssimate di nascosto: sono una decisione."
        )
    return MeshAnalysis(mesh=mesh, bodies=analyses, measurements=measurements,
                        features=features, notes=notes)


def _unique_name(body: Body, index: int, bodies: list[Body]) -> str:
    """Il nome del gruppo OBJ, disambiguato quando più corpi lo condividono."""
    same = [b for b in bodies if b.name == body.name]
    if len(same) <= 1:
        return body.name
    # Confronto per identità: i corpi portano array numpy, e `==` fra dataclass
    # li confronterebbe elemento per elemento.
    position = next(i for i, b in enumerate(same) if b is body)
    return f"{body.name}#{position + 1}"


# -- letture ----------------------------------------------------------------


def _read_outer_faces(a: BodyAnalysis) -> None:
    """I piani che stanno sul contorno dell'ingombro e ne coprono una parte vera.

    «Sul contorno» da solo non basta: un labbro di pochi mm² tocca l'estremo
    dell'ingombro esattamente come la parete che gli sta accanto. Se la faccia
    esterna di un lato non esiste — perché la superficie è curva, o perché la
    tassellazione l'ha fusa con il raccordo — questo metodo non ne inventa una:
    quel lato resta senza faccia, e senza le quote che ne dipendono.
    """
    extents = a.body.extents
    for k, axis in enumerate(AXES):
        section = float(extents[(k + 1) % 3] * extents[(k + 2) % 3])
        floor_area = max(MIN_FACE_AREA, MIN_FACE_FRACTION * section)
        for side, limit in (("min", a.body.bbox_min[k]), ("max", a.body.bbox_max[k])):
            outward = -1.0 if side == "min" else 1.0
            best: Patch | None = None
            for patch in a.body.planes_normal_to(axis):
                if patch.area < floor_area:
                    continue
                if np.sign(patch.normal[k]) != outward:
                    continue
                position = float(patch.bbox_min[k])
                if abs(position - limit) > OUTER_TOL:
                    continue
                if best is None or patch.area > best.area:
                    best = patch
            if best is not None:
                a.outer[f"{axis}-{side}"] = best


def _read_walls(a: BodyAnalysis) -> None:
    """Spessore di parete: dalla faccia esterna alla prima faccia che le sta di fronte.

    «Di fronte» ha un significato preciso: normale opposta, e sovrapposizione
    sugli altri due assi. Senza quel controllo la parete di un lato verrebbe
    misurata contro la faccia interna del lato opposto.
    """
    faces = set(id(p) for p in a.outer.values())
    for key, outer in a.outer.items():
        axis, side = key.split("-")
        k = AXES.index(axis)
        outer_pos = float(outer.bbox_min[k])
        inward = 1.0 if side == "min" else -1.0
        best: tuple[float, Patch] | None = None
        for patch in a.body.planes_normal_to(axis):
            # Un'altra faccia esterna non è la faccia interna di questa parete:
            # su un corpo pieno darebbe «spessore = tutto il pezzo».
            if id(patch) in faces or patch.area < MIN_FACE_AREA:
                continue
            if np.sign(patch.normal[k]) != inward:
                continue
            thickness = (float(patch.bbox_min[k]) - outer_pos) * inward
            if thickness <= SAME:
                continue
            if not _covers(outer, patch, skip=k):
                continue
            if best is None or thickness < best[0]:
                best = (thickness, patch)
        if best is not None:
            a.walls[key] = best[0]


def _covers(outer: Patch, inner: Patch, *, skip: int) -> bool:
    """`inner` sta davanti a `outer` per una parte significativa della sua estensione?

    Non basta che si tocchino: serve che la faccia interna copra davvero quella
    esterna, altrimenti il fianco di una feature qualsiasi passa per parete.
    """
    for k in range(3):
        if k == skip:
            continue
        low = max(float(outer.bbox_min[k]), float(inner.bbox_min[k]))
        high = min(float(outer.bbox_max[k]), float(inner.bbox_max[k]))
        span = float(outer.bbox_max[k] - outer.bbox_min[k])
        if span <= SAME:
            continue
        if (high - low) < MIN_WALL_COVERAGE * span:
            return False
    return True


def _read_cavity(a: BodyAnalysis) -> None:
    """Cavità: un piano orizzontale interno rivolto verso l'alto, sotto il bordo."""
    top = a.outer.get("Z-max")
    z_top = float(top.bbox_min[2]) if top is not None else float(a.body.bbox_max[2])
    floor: Patch | None = None
    for patch in a.body.planes_normal_to("Z"):
        if patch.area < MIN_FACE_AREA or patch.normal[2] <= 0:
            continue
        z = float(patch.bbox_min[2])
        if z <= float(a.body.bbox_min[2]) + SAME or z >= z_top - SAME:
            continue
        if floor is None or patch.area > floor.area:
            floor = patch
    if floor is None:
        return
    a.cavity_floor = float(floor.bbox_min[2])
    a.cavity_top = z_top


def _read_roundings(a: BodyAnalysis) -> None:
    """Arrotondamento di uno spigolo, letto da dove le due facce piane si fermano.

    Se la faccia superiore si ferma a 1.5 mm dal fianco e il fianco si ferma a
    1.5 mm dalla faccia superiore, quello spigolo ha un raccordo circolare R1.5.
    Se i due arretramenti sono diversi, il raccordo non è circolare — ed è
    esattamente il caso che va portato all'utente invece che arrotondato di
    nascosto. Il metodo regge anche su tassellazioni grossolane, perché guarda
    dove finiscono le facce piane, non come è discretizzata la curva.
    """
    keys = list(a.outer)
    for i, first_key in enumerate(keys):
        for second_key in keys[i + 1:]:
            axis_a, side_a = first_key.split("-")
            axis_b, side_b = second_key.split("-")
            if axis_a == axis_b:
                continue
            ka, kb = AXES.index(axis_a), AXES.index(axis_b)
            face_a, face_b = a.outer[first_key], a.outer[second_key]
            # Arretramento della faccia A lungo l'asse di B, e viceversa.
            edge_b = float(face_b.bbox_min[kb])
            edge_a = float(face_a.bbox_min[ka])
            setback_a = _setback(face_a, kb, edge_b, side_b)
            setback_b = _setback(face_b, ka, edge_a, side_a)
            if setback_a is None or setback_b is None:
                continue
            if setback_a <= SAME and setback_b <= SAME:
                continue  # spigolo vivo: nessun raccordo da decidere
            extents = a.body.extents
            if (setback_a > MAX_ROUNDING_FRACTION * float(extents[kb])
                    or setback_b > MAX_ROUNDING_FRACTION * float(extents[ka])):
                continue  # troppo grande per essere un raccordo: non lo si battezza tale
            a.roundings.append({
                "kind": "spigolo",
                "edge": f"{first_key}/{second_key}",
                f"semiasse_{axis_b.lower()}": setback_a,
                f"semiasse_{axis_a.lower()}": setback_b,
                "along": axis_b,
                "across": axis_a,
                "value_along": setback_a,
                "value_across": setback_b,
                "circular": abs(setback_a - setback_b) <= max(
                    0.02 * max(setback_a, setback_b), SAME),
            })


def _setback(face: Patch, axis_index: int, edge: float, side: str) -> float | None:
    """Di quanto la faccia si ferma prima dello spigolo teorico."""
    reach = float(face.bbox_min[axis_index] if side == "min" else face.bbox_max[axis_index])
    setback = (reach - edge) if side == "min" else (edge - reach)
    return setback if setback >= -SAME else None


def _read_holes(a: BodyAnalysis, mesh: Mesh) -> None:
    """Fori e asole, dai cilindri riconosciuti.

    Un cilindro completo — largo un diametro in tutte e due le direzioni
    trasversali — è un foro, e il suo diametro è una quota. Un cilindro parziale è
    un arco: può essere il raccordo di uno spigolo, oppure la testata di un'asola.
    Distinguerli non è un dettaglio: due archi coassiali dello stesso raggio, con
    la stessa estensione lungo l'asse, sono le due testate di un'asola, e da lì
    escono larghezza e interasse. Un arco solo resta un arco, e viene dichiarato
    tale invece che promosso a foro.
    """
    arcs: list[dict[str, Any]] = []
    for patch in a.body.of_kind("cylinder"):
        name = patch.axis_name
        if name is None or patch.radius is None:
            continue  # asse obliquo: resta fra le feature, non fra i fori quotati
        k = AXES.index(name)
        span = float(patch.bbox_max[k] - patch.bbox_min[k])
        widths = [float(patch.bbox_max[j] - patch.bbox_min[j]) for j in range(3) if j != k]
        record = {
            "axis": name,
            "diameter": 2.0 * patch.radius,
            "radius": float(patch.radius),
            "depth": span,
            "center": [float(x) for x in patch.center] if patch.center is not None else None,
            "rms": patch.rms,
            "slot": False,
            "width": min(widths),
            "length": max(widths),
            "area": patch.area,
        }
        if min(widths) >= BORE_WIDTH_RATIO * patch.radius:
            a.holes.append(record)
        else:
            arcs.append(record)

    a.holes.extend(_slots_from_arcs(arcs))
    a.arcs = [arc for arc in arcs if not arc.get("paired")]
    a.holes.sort(key=lambda h: -h["area"])


def _slots_from_arcs(arcs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Coppie di archi coassiali e di pari raggio: le due testate di un'asola."""
    out: list[dict[str, Any]] = []
    for i, first in enumerate(arcs):
        if first.get("paired") or first["center"] is None:
            continue
        for second in arcs[i + 1:]:
            if second.get("paired") or second["center"] is None:
                continue
            if second["axis"] != first["axis"]:
                continue
            if abs(second["radius"] - first["radius"]) > 0.02 * first["radius"]:
                continue
            if abs(second["depth"] - first["depth"]) > max(0.05 * first["depth"], SAME):
                continue
            gap = float(np.linalg.norm(np.asarray(first["center"])
                                       - np.asarray(second["center"])))
            if gap <= SAME or gap > MAX_SLOT_GAP_RADII * first["radius"]:
                continue
            first["paired"] = second["paired"] = True
            out.append({
                "axis": first["axis"],
                "diameter": 2.0 * first["radius"],
                "radius": first["radius"],
                "depth": first["depth"],
                "center": [(x + y) / 2.0 for x, y in zip(first["center"], second["center"])],
                "rms": max(first["rms"], second["rms"]),
                "slot": True,
                "width": 2.0 * first["radius"],
                "length": 2.0 * first["radius"] + gap,
                "interasse": gap,
                "area": first["area"] + second["area"],
            })
            break
    return out


def _read_free_patches(a: BodyAnalysis) -> None:
    a.free_patches = [p for p in a.body.of_kind("free") if p.area >= MIN_FACE_AREA]


def _read_symmetry(a: BodyAnalysis, mesh: Mesh) -> None:
    """Quanto il corpo è speculare rispetto ai propri piani mediani.

    Misura semplice e verificabile: la frazione di vertici che ha un
    corrispondente speculare entro la tolleranza. Non è un giudizio, è un numero:
    se vale 1.0 il pezzo è simmetrico, se vale 0.6 non lo è, e nel mezzo si decide.
    """
    points = mesh.vertices[np.unique(mesh.faces[a.body.faces])]
    if len(points) == 0:
        return
    grid = np.round(points / SYMMETRY_TOL).astype(np.int64)
    present = set(map(tuple, grid))
    center = (a.body.bbox_min + a.body.bbox_max) / 2.0
    for k, axis in enumerate(AXES):
        mirrored = points.copy()
        mirrored[:, k] = 2.0 * center[k] - mirrored[:, k]
        keys = np.round(mirrored / SYMMETRY_TOL).astype(np.int64)
        hits = sum(1 for key in map(tuple, keys) if key in present)
        a.symmetry[axis] = hits / len(points)


# -- da letture a quote e feature -------------------------------------------


def _measurements_of(a: BodyAnalysis) -> list[Measurement]:
    out: list[Measurement] = []

    def add(suffix: str, label: str, value: float, note: str = "") -> None:
        out.append(Measurement(id=f"{a.key}_{suffix}", label=f"{a.name} · {label}",
                               value=float(value), note=note))

    for k, axis in enumerate(AXES):
        add(f"ingombro_{axis.lower()}", f"ingombro {axis}", a.extents[k],
            note="differenza fra gli estremi del corpo")

    for key, thickness in sorted(a.walls.items()):
        axis, side = key.split("-")
        add(f"parete_{axis.lower()}_{side}", f"parete {axis} {side}", thickness,
            note="faccia esterna → prima faccia opposta")

    if a.cavity_floor is not None and a.cavity_top is not None:
        add("cavita_profondita", "profondità della cavità",
            a.cavity_top - a.cavity_floor, note="bordo → fondo interno")
        add("fondo_spessore", "spessore del fondo",
            a.cavity_floor - float(a.body.bbox_min[2]),
            note="base del corpo → fondo interno")

    for rounding in a.roundings:
        if rounding["kind"] != "spigolo":
            continue
        edge = rounding["edge"].replace("/", "_").replace("-", "").lower()
        if rounding["circular"]:
            add(f"raccordo_{edge}_r", f"raccordo spigolo {rounding['edge']}",
                (rounding["value_along"] + rounding["value_across"]) / 2.0,
                note="i due arretramenti coincidono: raccordo circolare")
        else:
            add(f"raccordo_{edge}_{rounding['along'].lower()}",
                f"raccordo {rounding['edge']} · semiasse {rounding['along']}",
                rounding["value_along"], note="arretramento della faccia")
            add(f"raccordo_{edge}_{rounding['across'].lower()}",
                f"raccordo {rounding['edge']} · semiasse {rounding['across']}",
                rounding["value_across"], note="arretramento della faccia")

    for index, hole in enumerate(a.holes, start=1):
        if hole["slot"]:
            add(f"asola{index}_larghezza", f"asola {index} · larghezza", hole["width"],
                note=f"due testate di raggio {hole['radius']:.4f} sull'asse {hole['axis']}")
            add(f"asola{index}_lunghezza", f"asola {index} · lunghezza", hole["length"],
                note=f"interasse delle testate {hole.get('interasse', 0.0):.4f}")
        else:
            add(f"foro{index}_diametro", f"foro {index} · diametro", hole["diameter"],
                note=f"cilindro asse {hole['axis']}, rms {hole['rms']:.4f}")
        add(f"{'asola' if hole['slot'] else 'foro'}{index}_profondita",
            f"{'asola' if hole['slot'] else 'foro'} {index} · profondità", hole["depth"])
    return out


def _features_of(a: BodyAnalysis) -> list[Feature]:
    out = [Feature(
        kind="prisma", body=a.name, label=f"{a.name}: ingombro esterno",
        params={"lunghezza_x": float(a.extents[0]), "larghezza_y": float(a.extents[1]),
                "altezza_z": float(a.extents[2]),
                "origine_x": float(a.body.bbox_min[0]),
                "origine_y": float(a.body.bbox_min[1]),
                "origine_z": float(a.body.bbox_min[2])},
        note="chiuso" if a.body.closed else "mesh aperta: il volume non è affidabile",
    )]
    if a.cavity_floor is not None and a.cavity_top is not None:
        out.append(Feature(
            kind="cavita", body=a.name, label=f"{a.name}: cavità",
            params={"fondo_z": a.cavity_floor, "bordo_z": a.cavity_top,
                    **{f"parete_{k.lower().replace('-', '_')}": v
                       for k, v in a.walls.items()}},
        ))
    for index, hole in enumerate(a.holes, start=1):
        centre = hole["center"] or [0.0, 0.0, 0.0]
        out.append(Feature(
            kind="asola" if hole["slot"] else "foro", body=a.name,
            label=f"{a.name}: {'asola' if hole['slot'] else 'foro'} {index}",
            params={"diametro": hole["diameter"], "profondita": hole["depth"],
                    "larghezza": hole["width"], "lunghezza": hole["length"],
                    "centro_x": centre[0], "centro_y": centre[1], "centro_z": centre[2]},
            note=f"asse {hole['axis']}",
            buildable=not hole["slot"],
        ))
    for patch in a.free_patches:
        out.append(Feature(
            kind="libera", body=a.name, label=f"{a.name}: superficie libera",
            params={"area": patch.area, "spread_deg": patch.spread_deg,
                    "dx": float(patch.extents[0]), "dy": float(patch.extents[1]),
                    "dz": float(patch.extents[2])},
            note="né piano né cilindro né sfera",
            buildable=False,
        ))
    return out
