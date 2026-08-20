# -*- coding: utf-8 -*-
"""Compositore di tavole: da una specifica dichiarativa ai file PDF, DXF e SVG.

Il contratto e' netto. Qui si sa **come** si disegna un foglio — dove va la
cornice, come si scala una vista, che aspetto ha una quota — e non si sa **cosa**
c'e' dentro: viste, quote e note arrivano da chi compone la tavola, cioe' da un
plugin di `parts/`. E' lo stesso confine di `core/plugin.py`, applicato al disegno.

La geometria proiettata arriva dal JSON di `project_script.py`, che gira sotto
FreeCAD. Questo modulo non importa FreeCAD: si puo' eseguire e provare ovunque.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from core.drafting import layout
from core.drafting.sheet import Foglio, scrivi_dxf, scrivi_pdf, scrivi_svg

A3 = (420.0, 297.0)


# ---------------------------------------------------------------- specifica


@dataclass(frozen=True)
class Vista:
    """Una vista proiettata, con il posto che occupa sul foglio.

    `id` e' la chiave della vista nel JSON delle proiezioni; `centro_modello` e'
    il punto della vista (coordinate del modello proiettate) che finisce nel
    centro assegnato sul foglio. Se e' None si usa il centro dell'ingombro.
    """

    id: str
    etichetta: str
    centro: tuple[float, float]
    scala: float
    centro_modello: tuple[float, float] | None = None
    etichetta_sotto: float = 0.0        # distanza dell'etichetta dal bordo basso
    campitura_passo: float = 1.6


@dataclass(frozen=True)
class Quota:
    """Una quota lineare, in coordinate di vista. Il testo lo decide il chiamante.

    Il testo e' obbligatorio e non viene calcolato dalla geometria: sulla tavola
    deve comparire il valore del registro delle quote, non la misura del disegno.
    """

    vista: str
    p1: tuple[float, float]
    p2: tuple[float, float]
    offset: float
    testo: str
    orizzontale: bool = True
    fuori: bool | None = None


@dataclass(frozen=True)
class Richiamo:
    """Linea di richiamo con testo: fori, asole, tasche, note locali."""

    vista: str
    punto: tuple[float, float]
    scostamento: tuple[float, float]     # mm sul foglio, dal punto al testo
    righe: tuple[str, ...]


@dataclass(frozen=True)
class Traccia:
    """Traccia di un piano di sezione su una vista, con la sua lettera."""

    vista: str
    p1: tuple[float, float]
    p2: tuple[float, float]
    lettera: str
    verso: int = 1


@dataclass(frozen=True)
class Sagoma:
    """Un profilo di confronto sovrapposto a una vista, in coordinate di vista.

    Non è geometria del modello: serve a far vedere, sulla tavola stessa, di
    quanto il solido ricostruito si scosta dal pezzo reale. Ha uno stile e un
    layer suoi perché non si confonda con gli spigoli.
    """

    vista: str
    punti: tuple[tuple[float, float], ...]
    chiusa: bool = True


@dataclass(frozen=True)
class Tabella:
    x: float
    y: float
    w: float
    titolo: str
    intestazioni: tuple[tuple[str, float, str], ...]
    righe: tuple[tuple[tuple[str, str], ...], ...]
    h_riga: float = 5.0


@dataclass(frozen=True)
class Riquadro:
    x: float
    y: float
    w: float
    h: float
    titolo: str
    righe: tuple[str, ...]


@dataclass
class FoglioSpec:
    cartiglio: layout.Cartiglio
    viste: list[Vista] = field(default_factory=list)
    quote: list[Quota] = field(default_factory=list)
    richiami: list[Richiamo] = field(default_factory=list)
    tracce: list[Traccia] = field(default_factory=list)
    sagome: list[Sagoma] = field(default_factory=list)
    tabelle: list[Tabella] = field(default_factory=list)
    riquadri: list[Riquadro] = field(default_factory=list)
    larghezza: float = A3[0]
    altezza: float = A3[1]


# ---------------------------------------------------------------- disegno


def _trasforma(vista: Vista, proiezione: dict):
    """Coordinate di vista (mm di modello) -> coordinate carta (mm)."""
    if vista.centro_modello is not None:
        cx, cy = vista.centro_modello
    else:
        x0, y0, x1, y1 = proiezione.get("bbox", [0.0, 0.0, 0.0, 0.0])
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    px, py = vista.centro
    s = vista.scala

    def T(p):
        x = p[0] if not hasattr(p, "x") else p.x
        y = p[1] if not hasattr(p, "x") else p.y
        return (px + (x - cx) * s, py + (y - cy) * s)

    return T


def disegna_edges(f: Foglio, edges: list[dict], T, scala: float, stile: str) -> None:
    """Riversa le primitive 2D del JSON nel foglio, applicando la trasformazione."""
    for e in edges:
        tipo = e["t"]
        if tipo == "l":
            a, b = T(e["a"]), T(e["b"])
            f.linea(a[0], a[1], b[0], b[1], stile)
        elif tipo == "c":
            c = T(e["c"])
            f.cerchio(c[0], c[1], e["r"] * scala, stile)
        elif tipo == "a":
            c = T(e["c"])
            f.arco(c[0], c[1], e["r"] * scala, e["a1"], e["a2"], stile)
        else:
            f.polilinea([T(p) for p in e["pts"]], stile)


def disegna_vista(f: Foglio, vista: Vista, proiezione: dict) -> None:
    """Campitura di sezione, spigoli nascosti, spigoli in vista, etichetta."""
    T = _trasforma(vista, proiezione)
    poligoni = [[T(p) for p in poly] for poly in proiezione.get("sezione", [])]
    if poligoni:
        f.tratteggio(poligoni, passo=vista.campitura_passo, ang=45.0)
    disegna_edges(f, proiezione.get("nascosti", []), T, vista.scala, 'nascosto')
    disegna_edges(f, proiezione.get("visibili", []), T, vista.scala, 'contorno')
    if vista.etichetta:
        x0, y0, x1, y1 = proiezione.get("bbox", [0.0, 0.0, 0.0, 0.0])
        basso = T((x0, y0))[1]
        layout.etichetta(f, vista.centro[0], basso - vista.etichetta_sotto, vista.etichetta)


def componi_foglio(spec: FoglioSpec, proiezioni: dict, n: int, tot: int) -> Foglio:
    """Un `FoglioSpec` diventa un `Foglio` di primitive, pronto per i backend."""
    f = Foglio(spec.larghezza, spec.altezza, spec.cartiglio.titolo)
    layout.cornice_e_cartiglio(f, spec.cartiglio, n, tot)

    per_id = {v.id: v for v in spec.viste}
    for vista in spec.viste:
        disegna_vista(f, vista, proiezioni.get(vista.id, {}))

    def T_di(vista_id: str):
        vista = per_id[vista_id]
        return _trasforma(vista, proiezioni.get(vista_id, {})), vista.scala

    for q in spec.quote:
        if q.vista not in per_id:
            continue
        T, _ = T_di(q.vista)
        f.quota_lineare(T(q.p1), T(q.p2), q.offset, q.testo,
                        orizzontale=q.orizzontale, fuori=q.fuori)
    for s in spec.sagome:
        if s.vista not in per_id:
            continue
        T, _ = T_di(s.vista)
        f.polilinea([T(p) for p in s.punti], 'riferimento', chiusa=s.chiusa)
    for r in spec.richiami:
        if r.vista not in per_id:
            continue
        T, _ = T_di(r.vista)
        p = T(r.punto)
        f.richiamo(p, (p[0] + r.scostamento[0], p[1] + r.scostamento[1]), list(r.righe))
    for t in spec.tracce:
        if t.vista not in per_id:
            continue
        T, _ = T_di(t.vista)
        a, b = T(t.p1), T(t.p2)
        layout.linea_di_sezione(f, a[0], a[1], b[0], b[1], t.lettera, t.verso)
    for tab in spec.tabelle:
        f.tabella(tab.x, tab.y, tab.w, tab.titolo, list(tab.intestazioni),
                  [list(r) for r in tab.righe], h_riga=tab.h_riga)
    for riq in spec.riquadri:
        f.riquadro(riq.x, riq.y, riq.w, riq.h, riq.titolo)
        for i, riga in enumerate(riq.righe):
            f.testo(riq.x + 4.0, riq.y + riq.h - 13.0 - 4.6 * i, riga, 2.5, st='contorno')
    return f


def componi(fogli: list[FoglioSpec], proiezioni: dict, out_dir: Path,
            nome: str = "drawing", titolo_pdf: str = "Tavola") -> dict[str, Path]:
    """Scrive PDF multipagina, DXF con i fogli affiancati e un SVG per foglio."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    disegnati = [componi_foglio(s, proiezioni, i, len(fogli))
                 for i, s in enumerate(fogli, start=1)]

    artefatti: dict[str, Path] = {}
    pdf = out_dir / f"{nome}.pdf"
    scrivi_pdf(disegnati, str(pdf), titolo_pdf)
    artefatti["pdf"] = pdf

    dxf = out_dir / f"{nome}.dxf"
    scrivi_dxf(disegnati, str(dxf))
    artefatti["dxf"] = dxf

    for i, f in enumerate(disegnati, start=1):
        svg = out_dir / f"{nome}_p{i}.svg"
        scrivi_svg([f], str(svg))
        artefatti[f"svg_p{i}" if i > 1 else "svg"] = svg
    return artefatti


# ---------------------------------------------------------------- utilita'


def bbox_2d(proiezione: dict) -> tuple[float, float, float, float]:
    """(x0, y0, x1, y1) della vista, con un valore neutro se la vista e' vuota."""
    box = proiezione.get("bbox") or [0.0, 0.0, 0.0, 0.0]
    return tuple(float(v) for v in box)


def dimensioni_2d(proiezione: dict) -> tuple[float, float]:
    x0, y0, x1, y1 = bbox_2d(proiezione)
    return (x1 - x0, y1 - y0)


def ancora_iso(proiezione: dict, area: tuple[float, float, float, float],
               margine: float = 6.0,
               massimo: float | None = None) -> tuple[float, tuple[float, float]]:
    """Scala e centro per infilare l'assonometria in un rettangolo libero.

    `massimo` limita la scala verso l'alto: serve a non disegnare il pittorico
    più grande delle viste quotate che accompagna.
    """
    x0, y0, x1, y1 = area
    w, h = dimensioni_2d(proiezione)
    scala = layout.scala_normalizzata(w, h, (x1 - x0) - 2 * margine, (y1 - y0) - 2 * margine)
    if massimo is not None:
        scala = min(scala, massimo)
    return scala, ((x0 + x1) / 2.0, (y0 + y1) / 2.0 - 2.0)
