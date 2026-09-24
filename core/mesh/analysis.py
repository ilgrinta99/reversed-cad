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
* superfici libere, che nessuna primitiva elementare spiega, e — con esse — tutte
  le superfici che una primitiva spiega ma che il ricostruttore non porta:
  calotte sferiche, cilindri ad asse obliquo, archi spaiati. Sono dichiarate con
  posizione e ingombro, perché una feature taciuta è peggio di una non costruita;
* simmetria rispetto ai piani mediani e posizione del datum.

Ogni numero che esce da qui porta con sé come è stato ottenuto. Quello che non è
misurabile non viene stimato: viene dichiarato mancante, e diventa una domanda
all'utente (`core.mesh.ambiguity`).
"""

from __future__ import annotations

import math
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
    #: Facce esterne che la tassellazione ha fuso con un raccordo di base. La
    #: patch non è un piano — il suo ingombro include la fascia del raccordo — ma
    #: l'esterno del corpo passa di lì, e senza questa lettura la parete non
    #: esiste: la cavità verrebbe tagliata a tutto spessore e i fori non
    #: troverebbero materiale da asportare. Servono a misurare gli spessori, non
    #: a leggere raccordi: lì l'ingombro mentirebbe e si resta su `outer`.
    soft_outer: dict[str, Patch] = field(default_factory=dict)
    walls: dict[str, float] = field(default_factory=dict)   # "X-min" → spessore
    cavity_floor: float | None = None
    cavity_top: float | None = None
    #: (x0, y0, x1, y1) dei quattro lati interni della cavità, in coordinate di
    #: mesh. La cavità non si ricava dall'ingombro del corpo: una sporgenza lo
    #: gonfia, e la tasca finirebbe dentro la sporgenza.
    cavity_box: tuple[float, float, float, float] | None = None
    roundings: list[dict[str, Any]] = field(default_factory=list)
    holes: list[dict[str, Any]] = field(default_factory=list)
    #: Archi cilindrici parziali rimasti spaiati: né fori né testate di asola.
    arcs: list[dict[str, Any]] = field(default_factory=list)
    #: Aperture e tasche rettangolari: quattro facce piane che formano un canale.
    #: Un foro o un'asola si riconoscono da un cilindro; un'apertura rettangolare
    #: non ha cilindri, e senza questa lettura spariva fra l'analisi e la tavola.
    windows: list[dict[str, Any]] = field(default_factory=list)
    free_patches: list[Patch] = field(default_factory=list)
    #: Cupole: paraboloidi ellittici ad asse coordinato. Bordo, altezza e verso.
    caps: list[dict[str, Any]] = field(default_factory=list)
    #: Superfici che esistono nella mesh e che il repertorio del ricostruttore non
    #: porta: superfici libere, calotte sferiche, cilindri ad asse obliquo, archi
    #: spaiati. Non sono quote — sono *presenze*, con dove stanno e quanto sono
    #: grandi, perché una feature taciuta è peggio di una feature non costruita.
    omitted: list[dict[str, Any]] = field(default_factory=list)
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
                    "omesse": len(b.omitted),
                    "walls": dict(b.walls),
                    "cavity_box": (None if b.cavity_box is None
                                   else [float(v) for v in b.cavity_box]),
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
        _read_cavity(analysis)
        # Dietro la cavità: una faccia è «esterna» solo se sta *fuori* dalla
        # cavità. Senza questo ordine la faccia interna della parete opposta
        # passerebbe per faccia esterna, e la parete non si misurerebbe più.
        _read_outer_faces_dietro(analysis)
        _read_walls(analysis)
        _read_roundings(analysis)
        _read_holes(analysis, mesh)
        _read_windows(analysis)
        _read_caps(analysis)
        _read_spheres(analysis)
        _read_free_patches(analysis)
        _read_symmetry(analysis, mesh)
        analysis.omitted.sort(key=lambda o: -o["area"])
        analyses.append(analysis)

        measurements.extend(_measurements_of(analysis))
        features.extend(_features_of(analysis))
        log(f"{analysis.name}: ingombro "
            f"{analysis.extents[0]:.3f} × {analysis.extents[1]:.3f} × "
            f"{analysis.extents[2]:.3f} mm, {len(body.patches)} patch, "
            f"{len(analysis.holes)} fori, {len(analysis.free_patches)} superfici libere, "
            f"{len(analysis.omitted)} superfici fuori dal repertorio")

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
    altre = sum(1 for a in analyses for o in a.omitted if o["kind"] != "libera")
    if altre:
        notes.append(
            f"{altre} superfici riconosciute ma fuori dal repertorio del "
            f"ricostruttore (calotte sferiche, cilindri obliqui, archi spaiati): "
            f"restano dichiarate con posizione e ingombro, non costruite."
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
                continue
            # Nessun piano *sul contorno*: la faccia è fusa col raccordo di base
            # e la patch è «libera». Il contorno del corpo passa comunque di lì —
            # l'ingombro lo dice — e la parete si misura da questa presenza.
            best = _soft_outer(a, k, side, limit)
            if best is not None:
                a.soft_outer[f"{axis}-{side}"] = best


def _read_outer_faces_dietro(a: BodyAnalysis) -> None:
    """La faccia esterna che una sporgenza nasconde al contorno.

    La cupola del TAISER esce di 6.14 mm oltre la parete destra: il contorno del
    corpo è il vertice della cupola, non la parete. Il piano della parete però
    c'è, copre la sezione, e sta **fuori dalla cavità**: è quello. Il vincolo
    sulla cavità è ciò che distingue la parete destra dalla faccia interna della
    parete sinistra — che guarda anch'essa verso +X, ma sta dentro la cavità.
    """
    if a.cavity_box is None:
        return
    extents = a.body.extents
    for k, axis in enumerate(AXES):
        if k == 2:
            continue        # la cavità è aperta in alto: su Z non dice dov'è il filo
        for side in ("min", "max"):
            key = f"{axis}-{side}"
            if key in a.outer:
                continue
            limite = a.cavity_box[k] if side == "min" else a.cavity_box[2 + k]
            outward = -1.0 if side == "min" else 1.0
            best: Patch | None = None
            best_pos: float | None = None
            for patch in a.body.planes_normal_to(axis):
                if patch.area < MIN_FACE_AREA:
                    continue
                if np.sign(patch.normal[k]) != outward:
                    continue
                pos = float(patch.bbox_min[k]) if side == "min" else float(patch.bbox_max[k])
                if outward * (pos - limite) <= SAME:
                    continue                    # dentro la cavità: non è la parete
                copre = True
                for j in range(3):
                    if j == k:
                        continue
                    if float(patch.bbox_max[j] - patch.bbox_min[j]) < \
                            MIN_WALL_COVERAGE * float(extents[j]):
                        copre = False
                        break
                if not copre:
                    continue
                if best is None or outward * pos > outward * best_pos:
                    best, best_pos = patch, pos
            if best is not None:
                a.outer[key] = best
                a.soft_outer.pop(key, None)


def _soft_outer(a: BodyAnalysis, k: int, side: str, limit: float) -> Patch | None:
    """La patch non piana il cui ingombro tocca il contorno su quel lato.

    Non è una faccia piana e non si finge che lo sia: se ne prende solo la
    posizione esterna, che è l'unica cosa che una parete chiede. Una patch che
    arriva al contorno ma è piccola — il labbro di una tasca, un raccordo locale —
    non copre la sezione del corpo e non viene presa.
    """
    extents = a.body.extents
    best: Patch | None = None
    for patch in a.body.patches:
        if patch.area < MIN_FACE_AREA:
            continue
        reach = float(patch.bbox_min[k]) if side == "min" else float(patch.bbox_max[k])
        if abs(reach - limit) > OUTER_TOL:
            continue
        copre = True
        for j in range(3):
            if j == k:
                continue
            span = float(patch.bbox_max[j] - patch.bbox_min[j])
            if span < MIN_FACE_FRACTION * float(extents[j]):
                copre = False
                break
        if not copre:
            continue
        if best is None or patch.area > best.area:
            best = patch
    return best


def _read_walls(a: BodyAnalysis) -> None:
    """Spessore di parete: dalla faccia esterna alla prima faccia che le sta di fronte.

    «Di fronte» ha un significato preciso: normale opposta, e sovrapposizione
    sugli altri due assi. Senza quel controllo la parete di un lato verrebbe
    misurata contro la faccia interna del lato opposto.

    Le facce esterne fuse col raccordo (`soft_outer`) contano come le altre: la
    loro posizione è il contorno, e la faccia interna che sta davanti è la parete.
    La sovrapposizione lì si chiede sulle estensioni del *corpo*, non su quelle
    della patch: l'ingombro di una patch fusa col raccordo si ferma prima della
    parete interna, e misurata su di sé la copertura non arriverebbe mai.
    """
    faces = set(id(p) for p in list(a.outer.values()) + list(a.soft_outer.values()))
    soft_ids = {id(p) for p in a.soft_outer.values()}
    for key, outer in {**a.outer, **a.soft_outer}.items():
        axis, side = key.split("-")
        k = AXES.index(axis)
        outer_pos = (float(outer.bbox_min[k]) if side == "min"
                     else float(outer.bbox_max[k]))
        inward = 1.0 if side == "min" else -1.0
        best: tuple[float, Patch] | None = None
        for patch in a.body.planes_normal_to(axis):
            # Un'altra faccia esterna non è la faccia interna di questa parete:
            # su un corpo pieno darebbe «spessore = tutto il pezzo».
            if id(patch) in faces or patch.area < MIN_FACE_AREA:
                continue
            if np.sign(patch.normal[k]) != inward:
                continue
            if side == "min":
                thickness = float(patch.bbox_min[k]) - outer_pos
            else:
                thickness = outer_pos - float(patch.bbox_max[k])
            if thickness <= SAME:
                continue
            if id(outer) in soft_ids:
                if not _covers_body(a, patch, skip=k):
                    continue
            elif not _covers(outer, patch, skip=k):
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


def _covers_body(a: BodyAnalysis, inner: Patch, *, skip: int) -> bool:
    """La faccia interna copre una parte significativa della sezione del corpo?

    È il criterio per le pareti lette su una faccia esterna non piana: la patch
    esterna non può fare da metro (il raccordo la taglia), quindi il metro è il
    corpo. Oltre metà della sezione: una tasca, un labbro, un rilievo non ci
    arrivano, e restano fuori.
    """
    extents = a.body.extents
    for k in range(3):
        if k == skip:
            continue
        if float(inner.bbox_max[k] - inner.bbox_min[k]) < MIN_WALL_COVERAGE * float(extents[k]):
            return False
    return True


def _read_cavity(a: BodyAnalysis) -> None:
    """Cavità: un piano orizzontale interno rivolto verso l'alto, sotto il bordo.

    Con il fondo si misurano anche le pareti interne che lo circondano: sono
    piani che salgono dal fondo e coprono la sezione del corpo. Da lì esce la
    *scatola* della cavità in coordinate assolute, che è ciò che serve a chi
    costruisce quando il corpo porta una sporgenza: la tasca non si ricava più
    dall'ingombro, che la sporgenza la gonfia, ma dai suoi quattro lati.
    """
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

    lati: dict[tuple[int, str], float] = {}
    for k, axis in enumerate(AXES):
        if k == 2:
            continue
        for side, inward in (("min", 1.0), ("max", -1.0)):
            best: Patch | None = None
            for patch in a.body.planes_normal_to(axis):
                if patch.area < MIN_FACE_AREA:
                    continue
                if np.sign(patch.normal[k]) != inward:
                    continue
                pos = float(patch.bbox_min[k])
                if not (float(a.body.bbox_min[k]) + SAME
                        < pos < float(a.body.bbox_max[k]) - SAME):
                    continue
                if not _covers_body(a, patch, skip=k):
                    continue
                if best is None or patch.area > best.area:
                    best = patch
            if best is not None:
                lati[(k, side)] = float(best.bbox_min[k])
    if len(lati) == 4:
        a.cavity_box = (lati[(0, "min")], lati[(1, "min")],
                        lati[(0, "max")], lati[(1, "max")])


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
    arc_patches: dict[int, Patch] = {}
    for patch in a.body.of_kind("cylinder"):
        if patch.radius is None:
            continue
        name = patch.axis_name
        if name is None:
            # Asse obliquo. Un cilindro *intero* resta un foro: girargli intorno
            # per tutto il diametro è la prova che è un foro, e l'inclinazione è
            # una misura come le altre. Un arco obliquo no: di quella testata non
            # si sa nemmeno di che feature è, e resta una presenza dichiarata.
            span, widths = _misure_nel_frame(patch, mesh)
            if min(widths) < BORE_WIDTH_RATIO * patch.radius:
                _omit(a, patch, "cilindro", "arco cilindrico ad asse obliquo")
                continue
            direction = np.asarray(patch.axis, dtype=float)
            a.holes.append({
                "axis": None,
                "direzione": [float(v) for v in direction / np.linalg.norm(direction)],
                "diameter": 2.0 * patch.radius, "radius": float(patch.radius),
                "depth": span,
                "center": ([float(x) for x in patch.center]
                           if patch.center is not None else None),
                "rms": patch.rms, "slot": False,
                "width": min(widths), "length": max(widths), "area": patch.area,
            })
            continue
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
            arc_patches[len(arcs)] = patch
            arcs.append(record)

    a.holes.extend(_slots_from_arcs(arcs))
    a.arcs = [arc for arc in arcs if not arc.get("paired")]
    a.holes.sort(key=lambda h: -h["area"])
    for index, arc in enumerate(arcs):
        if arc.get("paired") or _spiegato_da_un_raccordo(a, arc["radius"]):
            continue
        _omit(a, arc_patches[index], "arco", "arco cilindrico parziale, spaiato")


def _misure_nel_frame(patch: Patch, mesh: Mesh) -> tuple[float, list[float]]:
    """Lunghezza e larghezze di un cilindro obliquo, nel suo riferimento.

    L'ingombro in assi coordinati di un cilindro inclinato è più largo del
    cilindro: misurarci sopra il criterio «foro o arco» direbbe foro anche a un
    quarto di giro. Le due larghezze si misurano perpendicolarmente al suo asse.
    """
    axis = np.asarray(patch.axis, dtype=float)
    axis = axis / np.linalg.norm(axis)
    points = mesh.vertices[np.unique(mesh.faces[patch.faces])]
    seed = np.array([1.0, 0.0, 0.0]) if abs(axis[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    u = np.cross(axis, seed)
    u /= np.linalg.norm(u)
    v = np.cross(axis, u)
    along = points @ axis
    widths = [float((points @ e).max() - (points @ e).min()) for e in (u, v)]
    return float(along.max() - along.min()), widths


def _spiegato_da_un_raccordo(a: BodyAnalysis, radius: float) -> bool:
    """L'arco è il raccordo che la build costruisce davvero, e non va dichiarato omesso.

    Il raccordo verticale della ricetta nasce da un arrotondamento *circolare*
    misurato sulle facce piane (`_read_roundings`). Quando un arco ha quel raggio,
    la superficie che rappresenta finisce nel solido: elencarla fra le omesse
    sarebbe una bugia simmetrica a quella che questo modulo evita.
    """
    for rounding in a.roundings:
        if rounding.get("kind") != "spigolo" or not rounding.get("circular"):
            continue
        r = (rounding["value_along"] + rounding["value_across"]) / 2.0
        if abs(r - radius) <= max(0.02 * radius, SAME):
            return True
    return False


def _read_caps(a: BodyAnalysis) -> None:
    """Le cupole, dai paraboloidi riconosciuti.

    Ogni numero che entra nel modello viene dall'ingombro della patch, non dai
    coefficienti del fit: semiassi del bordo = metà delle estensioni trasversali,
    altezza = estensione lungo l'asse, centro del bordo = punto medio. Il fit
    serve a *decidere* che quella superficie è una cupola e da che parte guarda;
    le quote restano misure dirette, come per ogni altra feature.
    """
    for patch in a.body.of_kind("paraboloid"):
        if patch.area < MIN_FACE_AREA or patch.axis is None:
            continue
        k = int(np.argmax(np.abs(patch.axis)))
        verso = 1 if float(patch.axis[k]) > 0 else -1
        i, j = [q for q in range(3) if q != k]
        low, high = patch.bbox_min, patch.bbox_max
        centro = [(float(low[q]) + float(high[q])) / 2.0 for q in range(3)]
        # Il bordo sta all'estremo verso cui la cupola si apre; il vertice all'altro.
        centro[k] = float(high[k]) if verso > 0 else float(low[k])
        a.caps.append({
            "axis": AXES[k],
            "verso": verso,
            "assi_bordo": (AXES[i], AXES[j]),
            "centro": centro,
            "semi": {AXES[i]: float(high[i] - low[i]) / 2.0,
                     AXES[j]: float(high[j] - low[j]) / 2.0},
            "altezza": float(high[k] - low[k]),
            "area": float(patch.area),
            "rms": float(patch.rms),
        })
    a.caps.sort(key=lambda c: -c["area"])


def _read_spheres(a: BodyAnalysis) -> None:
    """Le calotte sferiche: misurate — centro e raggio — ma fuori dal repertorio.

    `patches.py` le riconosce da sempre e nessuno le leggeva: sparivano fra
    l'analisi e la tavola senza lasciare traccia. Il ricostruttore non le sa
    costruire; questo non è un motivo per non dire che ci sono.
    """
    for patch in a.body.of_kind("sphere"):
        _omit(a, patch, "sfera", "calotta sferica")


def _omit(a: BodyAnalysis, patch: Patch, kind: str, note: str) -> None:
    """Registra una superficie che il modello non porterà, con dove sta.

    La posizione non è un vezzo: senza di essa la tavola può solo scrivere «c'è
    una superficie libera», e chi legge non sa dove guardare. Con l'ingombro, la
    vista può dire *lì*.
    """
    if patch.area < MIN_FACE_AREA:
        return          # sotto quest'area è tassellazione, non una feature
    a.omitted.append({
        "kind": kind,
        "note": note,
        "area": float(patch.area),
        "spread_deg": float(patch.spread_deg),
        "bbox_min": [float(x) for x in patch.bbox_min],
        "bbox_max": [float(x) for x in patch.bbox_max],
        "radius": None if patch.radius is None else float(patch.radius),
        "axis": patch.axis_name,
    })


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
            scarto = np.asarray(second["center"], dtype=float) \
                - np.asarray(first["center"], dtype=float)
            gap = float(np.linalg.norm(scarto))
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
                # La direzione lunga dell'asola: le due testate la dimostrano, e
                # senza di essa il costruttore non saprebbe da che parte allungarla.
                "lungo": [float(v) / gap for v in scarto],
                "area": first["area"] + second["area"],
            })
            break
    return out


def _read_windows(a: BodyAnalysis) -> None:
    """Aperture e tasche rettangolari: quattro piani che formano un canale.

    Un foro ha un cilindro che lo dimostra; un'apertura rettangolare no — è
    quattro facce piane che si guardano, due per lato della sezione, con lo
    stesso spessore di materiale intorno. Da lì escono la sezione del vano e la
    profondità: quanto basta a tagliarlo nel modello, e a vederlo in sezione.
    """
    piani = [p for p in a.body.of_kind("plane") if p.area >= MIN_FACE_AREA]
    trovati: list[dict[str, Any]] = []
    for b in range(3):
        j, l = [q for q in range(3) if q != b]
        for pa, pb, jlo, jhi in _coppie_antiparallele(piani, j, b, l):
            llo, lhi = float(pa.bbox_min[l]), float(pa.bbox_max[l])
            if lhi - llo <= SAME:
                continue
            for pc, pd, l2lo, l2hi in _coppie_antiparallele(piani, l, b, j):
                if (abs(float(pc.bbox_min[j]) - jlo) > OUTER_TOL
                        or abs(float(pc.bbox_max[j]) - jhi) > OUTER_TOL):
                    continue
                if abs(l2lo - llo) > OUTER_TOL or abs(l2hi - lhi) > OUTER_TOL:
                    continue
                if not (float(a.body.bbox_min[j]) + SAME < jlo
                        and jhi < float(a.body.bbox_max[j]) - SAME):
                    continue
                if not (float(a.body.bbox_min[l]) + SAME < llo
                        and lhi < float(a.body.bbox_max[l]) - SAME):
                    continue
                blo, bhi = float(pa.bbox_min[b]), float(pa.bbox_max[b])
                if bhi - blo <= SAME or bhi - blo > 0.5 * float(a.body.extents[b]):
                    continue
                centro = [0.0, 0.0, 0.0]
                centro[j], centro[l], centro[b] = (jlo + jhi) / 2.0, (llo + lhi) / 2.0, (blo + bhi) / 2.0
                vano = [0.0, 0.0, 0.0]
                vano[j], vano[l], vano[b] = jhi - jlo, lhi - llo, bhi - blo
                trovati.append({
                    "axis": AXES[b],
                    "assi_sezione": (AXES[j], AXES[l]),
                    "center": centro,
                    "spans": vano,
                    "estensione": [blo, bhi],
                    "area": float(pa.area) + float(pb.area) + float(pc.area) + float(pd.area),
                })
    visti: set[tuple] = set()
    for vano in trovati:
        chiave = (vano["axis"],) + tuple(round(v, 3) for v in
                                         vano["center"] + vano["spans"])
        if chiave in visti:
            continue
        visti.add(chiave)
        a.windows.append(vano)
    a.windows.sort(key=lambda w: -w["area"])


def _coppie_antiparallele(planes: list[Patch], k: int, b: int,
                          l: int) -> list[tuple[Patch, Patch, float, float]]:
    """Coppie di piani antiparalleli che delimitano un canale sull'asse `k`.

    Stessa estensione su `b` (la profondità del canale) e su `l` (la larghezza):
    due facce che non combaciano non sono i due lati dello stesso vano. La faccia
    minore deve guardare verso l'interno del canale, o sarebbe il fianco di un
    rilievo, non il lato di un'apertura.
    """
    out = []
    for pa in planes:
        for pb in planes:
            if pa is pb or pa.normal[k] * pb.normal[k] >= 0:
                continue
            if (abs(float(pa.bbox_min[b]) - float(pb.bbox_min[b])) > OUTER_TOL
                    or abs(float(pa.bbox_max[b]) - float(pb.bbox_max[b])) > OUTER_TOL
                    or abs(float(pa.bbox_min[l]) - float(pb.bbox_min[l])) > OUTER_TOL
                    or abs(float(pa.bbox_max[l]) - float(pb.bbox_max[l])) > OUTER_TOL):
                continue
            lo, hi = sorted((float(pa.bbox_min[k]), float(pb.bbox_min[k])))
            if hi - lo <= SAME:
                continue
            minore = pa if float(pa.bbox_min[k]) < float(pb.bbox_min[k]) else pb
            if minore.normal[k] < 0:
                continue
            out.append((pa, pb, lo, hi))
    return out


def _read_free_patches(a: BodyAnalysis) -> None:
    a.free_patches = [p for p in a.body.of_kind("free") if p.area >= MIN_FACE_AREA]
    for patch in a.free_patches:
        _omit(a, patch, "libera", "né piano né cilindro né sfera")


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

    for index, cap in enumerate(a.caps, start=1):
        for axis in cap["assi_bordo"]:
            add(f"cupola{index}_semiasse_{axis.lower()}",
                f"cupola {index} · semiasse {axis} del bordo", cap["semi"][axis],
                note="metà dell'estensione della patch: misura diretta")
        add(f"cupola{index}_altezza", f"cupola {index} · altezza",
            cap["altezza"], note=f"paraboloide ellittico asse {cap['axis']}, "
                                 f"rms del fit {cap['rms']:.4f}")

    for index, vano in enumerate(a.windows, start=1):
        assi = vano["assi_sezione"]
        for axis in assi:
            k = AXES.index(axis)
            add(f"finestra{index}_{axis.lower()}",
                f"apertura {index} · {axis}", vano["spans"][k],
                note="estensione della sezione fra due facce parallele")
        add(f"finestra{index}_profondita", f"apertura {index} · profondità",
            vano["spans"][AXES.index(vano["axis"])],
            note=f"vano rettangolare attraverso l'asse {vano['axis']}")

    for index, hole in enumerate(a.holes, start=1):
        if hole["slot"]:
            add(f"asola{index}_larghezza", f"asola {index} · larghezza", hole["width"],
                note=f"due testate di raggio {hole['radius']:.4f} sull'asse {hole['axis']}")
            add(f"asola{index}_lunghezza", f"asola {index} · lunghezza", hole["length"],
                note=f"interasse delle testate {hole.get('interasse', 0.0):.4f}")
        else:
            add(f"foro{index}_diametro", f"foro {index} · diametro", hole["diameter"],
                note=f"cilindro asse {_nome_asse(hole)}, rms {hole['rms']:.4f}")
        add(f"{'asola' if hole['slot'] else 'foro'}{index}_profondita",
            f"{'asola' if hole['slot'] else 'foro'} {index} · profondità", hole["depth"])
    return out


def _nome_asse(hole: dict[str, Any]) -> str:
    """«X», «Y», «Z» oppure l'inclinazione vera, per un foro non coordinato."""
    if hole.get("axis"):
        return str(hole["axis"])
    d = hole.get("direzione") or [0.0, 0.0, 1.0]
    vicino = max(range(3), key=lambda k: abs(d[k]))
    gradi = math.degrees(math.acos(min(1.0, abs(d[vicino]))))
    return f"{AXES[vicino]} inclinato di {gradi:.1f}°"


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
    for index, cap in enumerate(a.caps, start=1):
        out.append(Feature(
            kind="cupola", body=a.name, label=f"{a.name}: cupola {index}",
            params={
                "altezza": cap["altezza"],
                **{f"semiasse_{k.lower()}": v for k, v in cap["semi"].items()},
                "centro_x": cap["centro"][0], "centro_y": cap["centro"][1],
                "centro_z": cap["centro"][2],
                "verso": float(cap["verso"]), "area": cap["area"], "rms": cap["rms"],
            },
            note=f"paraboloide ellittico, asse {cap['axis']}"
                 f"{'+' if cap['verso'] > 0 else '-'}",
        ))
    for index, hole in enumerate(a.holes, start=1):
        centre = hole["center"] or [0.0, 0.0, 0.0]
        params = {"diametro": hole["diameter"], "profondita": hole["depth"],
                  "larghezza": hole["width"], "lunghezza": hole["length"],
                  "centro_x": centre[0], "centro_y": centre[1], "centro_z": centre[2]}
        if hole.get("direzione"):
            params.update({f"direzione_{k}": v
                           for k, v in zip("xyz", hole["direzione"])})
        if hole.get("lungo"):
            params.update({f"lungo_{k}": v for k, v in zip("xyz", hole["lungo"])})
        out.append(Feature(
            kind="asola" if hole["slot"] else "foro", body=a.name,
            label=f"{a.name}: {'asola' if hole['slot'] else 'foro'} {index}",
            params=params,
            note=f"asse {_nome_asse(hole)}",
        ))
    for index, vano in enumerate(a.windows, start=1):
        centro, spans = vano["center"], vano["spans"]
        asse = str(vano["axis"])
        params = {"centro_x": centro[0], "centro_y": centro[1], "centro_z": centro[2],
                  "dx": spans[0], "dy": spans[1], "dz": spans[2],
                  "area": vano["area"]}
        for axis in vano["assi_sezione"]:
            params[f"larghezza_{axis.lower()}"] = spans[AXES.index(axis)]
        params[f"lungo_{asse.lower()}"] = 1.0
        params[f"profondita_{asse.lower()}"] = spans[AXES.index(asse)]
        out.append(Feature(
            kind="finestra", body=a.name, label=f"{a.name}: apertura {index}",
            params=params, note=f"vano rettangolare, asse {asse}",
        ))
    for omission in a.omitted:
        out.append(Feature(
            kind=omission["kind"], body=a.name,
            label=f"{a.name}: {_ETICHETTA_OMESSA[omission['kind']]}",
            params=_params_omessa(omission),
            note=omission["note"],
            buildable=False,
        ))
    return out


#: Come si chiama, sulla tavola, una superficie che il modello non porta.
_ETICHETTA_OMESSA = {
    "libera": "superficie libera",
    "sfera": "calotta sferica",
    "cilindro": "cilindro ad asse obliquo",
    "arco": "arco cilindrico spaiato",
}


def _params_omessa(omission: dict[str, Any]) -> dict[str, float]:
    """Ingombro e posizione di una superficie omessa, nel sistema della mesh.

    `dx`/`dy`/`dz` restano il nome storico dell'ingombro; `origine_*` e `centro_*`
    sono la novità che permette alla tavola di disegnarne l'impronta sulla vista
    giusta invece di limitarsi a nominarla in un riquadro.
    """
    low, high = omission["bbox_min"], omission["bbox_max"]
    params = {
        "area": omission["area"], "spread_deg": omission["spread_deg"],
        "dx": high[0] - low[0], "dy": high[1] - low[1], "dz": high[2] - low[2],
        "origine_x": low[0], "origine_y": low[1], "origine_z": low[2],
        "centro_x": (low[0] + high[0]) / 2.0,
        "centro_y": (low[1] + high[1]) / 2.0,
        "centro_z": (low[2] + high[2]) / 2.0,
    }
    if omission["radius"] is not None:
        params["raggio"] = omission["radius"]
    return params
