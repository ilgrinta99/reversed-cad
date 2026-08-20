"""Pezzo demo: un parallelepipedo misurato dalla mesh.

Non è il contenitore TAISER e non pretende di esserlo. Esiste per due motivi:

1. rende la pipeline eseguibile end-to-end (upload → analisi → decisioni → build →
   tavola → confronto) senza inventare un solo numero del pezzo vero;
2. è l'implementazione di riferimento di `PartPlugin`: chi scriverà
   `parts/teiser/` copia questa struttura, non deve indovinarla.

Ogni quota che esce da `measure()` porta il nome dello script che l'ha prodotta.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from core.compare import deviation
from core.freecad.runner import run_script
from core.mesh.loader import load_mesh
from core.plugin import RunContext, StepResult, registry
from core.provenance import Decision, DecisionKind, DecisionSet, Dimension, Option, Registry

_HERE = Path(__file__).parent
_MEASURED_BY = "parts/demo_box/plugin.py:measure"


class DemoBoxPart:
    id = "demo_box"
    name = "Parallelepipedo demo"
    description = (
        "Pezzo di riferimento per verificare la pipeline: misura l'ingombro della "
        "mesh e costruisce il solido corrispondente. Non è il contenitore TAISER."
    )

    # -- dichiarazioni -----------------------------------------------------

    def declare_dimensions(self) -> Registry:
        reg = Registry()
        reg.extend([
            Dimension(id="length", label="Lunghezza (X)"),
            Dimension(id="width", label="Larghezza (Y)"),
            Dimension(id="height", label="Altezza (Z)"),
        ])
        return reg

    def declare_decisions(self) -> DecisionSet:
        ds = DecisionSet()
        ds.add(Decision(
            id="A1",
            kind=DecisionKind.AMBIGUITY,
            title="Arrotondamento degli ingombri",
            question="Usare gli ingombri misurati così come sono, o arrotondarli al mm?",
            evidence=(
                "La mesh viene da un export triangolato: le facce non sono "
                "perfettamente planari, e l'ingombro misurato porta qualche decimo "
                "di rumore. Nessuna delle due letture è più 'vera' a priori."
            ),
            options=(
                Option(id="misurato", label="Tieni la misura",
                       consequence="Il modello resta fedele alla mesh, decimali inclusi."),
                # Nessun `sets` in queste opzioni: i valori dipendono dalla misura,
                # che a decisione dichiarata non è ancora stata fatta. L'utente li
                # conferma poi dalla tabella delle quote, dove misurato e usato sono
                # entrambi visibili. Un'opzione non porta numeri inventati a priori.
                Option(id="arrotondato", label="Arrotonda al mm",
                       consequence="Ingombri tondi, scostamento fino a 0.5 mm per lato."),
            ),
            reference="parts/demo_box/plugin.py",
        ))
        return ds

    # -- step --------------------------------------------------------------

    def measure(self, ctx: RunContext, registry_: Registry) -> StepResult:
        mesh = load_mesh(ctx.mesh_path)
        ctx.log(f"mesh caricata: {len(mesh)} vertici, {len(mesh.faces)} triangoli")

        lo, hi = mesh.bbox
        extents = hi - lo
        for dim_id, value, axis in zip(("length", "width", "height"), extents, "XYZ"):
            ctx.log(f"ingombro {axis}: {value:.4f} mm")
            registry_.update(
                registry_.get(dim_id).with_measurement(float(value), _MEASURED_BY)
                # Il valore misurato non entra da solo nel modello: resta da
                # accettare o da sostituire con un'approvazione. È lo step di
                # decisione, e non ha default silenziosi.
            )

        report = ctx.artifact("analysis.json")
        report.write_text(json.dumps({
            "vertices": int(len(mesh)),
            "triangles": int(len(mesh.faces)),
            "bbox_min": lo.tolist(),
            "bbox_max": hi.tolist(),
            "extents": extents.tolist(),
        }, indent=2))
        return StepResult(
            artifacts={"analysis": report},
            metrics={"vertices": int(len(mesh)), "triangles": int(len(mesh.faces))},
            notes=["Le quote sono misurate ma non ancora accettate: vanno confermate."],
        )

    def build(self, ctx: RunContext, registry_: Registry) -> StepResult:
        values = registry_.values()  # solleva se una quota non è misurata né approvata
        params = ctx.artifact("params.json")
        params.write_text(json.dumps(values, indent=2))

        run_script(
            _HERE / "build_script.py",
            [str(params), str(ctx.run_dir)],
            timeout_s=ctx.timeout_s,
            on_line=ctx.log,
        )
        return StepResult(
            artifacts={
                "params": params,
                "step": ctx.run_dir / "model.step",
                "stl": ctx.run_dir / "model.stl",
            },
            metrics={k: float(v) for k, v in values.items()},
        )

    def draw(self, ctx: RunContext, registry_: Registry) -> StepResult:
        """Tavola minimale in SVG, senza FreeCAD.

        Il motore di disegno vero è `cad/draft2d.py` (Python puro, backend
        SVG/PDF/DXF): quando entrerà in `core/drafting/`, questo metodo diventerà
        una chiamata a quello. La proprietà che conta è già qui: l'anteprima della
        tavola nel browser non passa da FreeCAD.
        """
        v = registry_.values()
        svg = _three_view_svg(v["length"], v["width"], v["height"])
        out = ctx.artifact("drawing.svg")
        out.write_text(svg)
        ctx.log("tavola SVG scritta (3 viste, quote in mm)")
        return StepResult(artifacts={"svg": out})

    def compare(self, ctx: RunContext, model_path: Path) -> StepResult:
        """Distanza della superficie della mesh da quella del solido.

        Per il parallelepipedo la distanza punto-superficie è analitica. Per il
        pezzo vero questo metodo delegherà a `compare_model_mesh.py`, che è già
        verificato: la firma è pensata per accoglierlo senza cambiamenti.
        """
        mesh = load_mesh(ctx.mesh_path)
        params = json.loads((ctx.run_dir / "params.json").read_text())
        # Il solido si confronta com'è stato costruito, con i valori *usati*: se una
        # quota è stata approvata diversa dalla misura, lo scostamento deve vedersi.
        lo, _ = mesh.bbox
        hi = lo + np.array([params["length"], params["width"], params["height"]])
        ctx.log(f"modello {hi - lo} mm dall'origine {lo} mm")
        # Solo i vertici non bastano: un vertice di spigolo giace su più facce del
        # solido e misura zero anche dove la superficie si discosta. Si campionano
        # anche i baricentri dei triangoli, che stanno in mezzo alle facce.
        samples = _surface_samples(mesh)
        d = _distance_to_box_surface(samples, lo, hi)

        out = ctx.artifact("deviation.json")
        punti = [[float(p[0]), float(p[1]), float(p[2]), float(dist)]
                 for p, dist in zip(samples, d)]
        stats = deviation.write(out, punti, {"BOX": {
            "stats": deviation.stats_from(d),
            "campionati": len(punti), "totali": len(punti), "worst": [],
        }})
        for key, value in stats.items():
            ctx.log(f"{key}: {value:.4f}")
        return StepResult(artifacts={"deviation": out},
                          metrics={k: round(v, 4) for k, v in stats.items()})


def _surface_samples(mesh) -> np.ndarray:
    """Vertici più baricentri dei triangoli: copre anche l'interno delle facce."""
    if len(mesh.faces) == 0:
        return mesh.vertices
    centroids = mesh.vertices[mesh.faces].mean(axis=1)
    return np.vstack([mesh.vertices, centroids])


def _distance_to_box_surface(points: np.ndarray, lo: np.ndarray,
                             hi: np.ndarray) -> np.ndarray:
    """Distanza esatta punto → superficie di una scatola allineata agli assi."""
    center = (lo + hi) / 2.0
    half = (hi - lo) / 2.0
    q = np.abs(points - center) - half
    outside = np.linalg.norm(np.maximum(q, 0.0), axis=1)
    inside = np.minimum(np.max(q, axis=1), 0.0)
    return np.abs(outside + inside)


def _three_view_svg(length: float, width: float, height: float) -> str:
    """Tre viste ortografiche quotate. Nessuna dipendenza, nessun FreeCAD."""
    m, gap = 30.0, 25.0
    w = m * 2 + length + gap + width
    h = m * 2 + height + gap + width
    views = [
        (m, m, length, height, "Fronte"),
        (m + length + gap, m, width, height, "Lato"),
        (m, m + height + gap, length, width, "Pianta"),
    ]
    body = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.1f}mm" height="{h:.1f}mm" '
        f'viewBox="0 0 {w:.1f} {h:.1f}">',
        '<style>text{font:3.5px sans-serif;fill:#111}'
        '.o{fill:none;stroke:#111;stroke-width:0.35}'
        '.d{stroke:#111;stroke-width:0.18}</style>',
        f'<rect x="0" y="0" width="{w:.1f}" height="{h:.1f}" fill="#fff"/>',
    ]
    for x, y, vw, vh, label in views:
        body.append(f'<rect class="o" x="{x:.2f}" y="{y:.2f}" '
                    f'width="{vw:.2f}" height="{vh:.2f}"/>')
        body.append(f'<text x="{x:.2f}" y="{y - 3:.2f}">{label}</text>')
        # Quota orizzontale sotto la vista.
        yq = y + vh + 8
        body.append(f'<line class="d" x1="{x:.2f}" y1="{yq:.2f}" '
                    f'x2="{x + vw:.2f}" y2="{yq:.2f}"/>')
        body.append(f'<text x="{x + vw / 2:.2f}" y="{yq - 1:.2f}" '
                    f'text-anchor="middle">{vw:.2f}</text>')
    body.append("</svg>")
    return "\n".join(body)


plugin = registry.register(DemoBoxPart())
