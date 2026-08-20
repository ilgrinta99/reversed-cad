"""Contenitore TAISER: collega `tools/` e `cad/` alla pipeline web.

Non riscrive nulla della pipeline esistente. Ogni step lancia lo script che già
esiste e che è già verificato, puntandolo sulla cartella del run tramite le
variabili d'ambiente `TAISER_MESH`, `TAISER_PARAMS`, `TAISER_OUT`, `TAISER_REPORT`
(vedi docs/CONVENTIONS.md). Da riga di comando gli script si comportano come prima.

Il registro delle quote (`core/provenance`) sta *sopra* params.json, non al suo
posto: `measure()` lo riempie leggendo il file che `extract_params.py` ha appena
scritto, e `build()` riscrive nel file i valori approvati prima di chiamare
`build_model.py`. Le quote non elencate in `schema.py` restano quelle misurate
dagli script: la regola vale anche per loro, semplicemente non hanno una riga in
tabella perché su di esse misura e uso non possono divergere.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from core.compare import deviation
from core.freecad.runner import run_script
from core.plugin import RunContext, StepResult, registry
from core.provenance import DecisionSet, Dimension, Registry
from parts.teiser import decisions as teiser_decisions
from parts.teiser import schema

ROOT = Path(__file__).resolve().parents[2]
EXTRACT = ROOT / "tools" / "extract_params.py"
RENDER = ROOT / "tools" / "render_views.py"
BUILD = ROOT / "cad" / "build_model.py"
DRAW = ROOT / "cad" / "make_drawing.py"
COMPARE = ROOT / "tools" / "compare_model_mesh.py"
PREVIEW = Path(__file__).parent / "preview_script.py"

MEASURED_BY = "tools/extract_params.py"


class TeiserPart:
    id = "teiser"
    name = "Contenitore TAISER"
    description = (
        "Scatola e coperchio con cupola paraboloidica, 4 colonnine (una diversa), "
        "asole e tasche ellittiche. Misure da tools/extract_params.py, solidi da "
        "cad/build_model.py, tavola da cad/make_drawing.py su cad/draft2d.py."
    )
    wired = True

    # -- dichiarazioni -----------------------------------------------------

    def declare_dimensions(self) -> Registry:
        reg = Registry()
        for spec in schema.SPECS:
            reg.add(Dimension(id=spec.id, label=spec.label, unit=spec.unit,
                              note=spec.note))
        return reg

    def declare_decisions(self) -> DecisionSet:
        return teiser_decisions.build()

    # -- step --------------------------------------------------------------

    def measure(self, ctx: RunContext, registry_: Registry) -> StepResult:
        params_path = ctx.artifact("params.json")
        ctx.log(f"misura di {ctx.mesh_path.name} con {EXTRACT.relative_to(ROOT)}")
        _run_python(EXTRACT, ctx, {"TAISER_MESH": str(ctx.mesh_path),
                                   "TAISER_PARAMS": str(params_path)})

        params = json.loads(params_path.read_text())
        divergenti, mancanti = [], []
        for spec in schema.SPECS:
            dim = registry_.get(spec.id)
            misura = schema.measured_value(params, spec)
            proposto = schema.proposed_value(params, spec)

            if misura is None:
                # Nessuna misura scalare: la quota esiste solo se approvata.
                mancanti.append(spec.id)
                registry_.update(dim)
                continue

            dim = dim.with_measurement(misura, MEASURED_BY)
            if proposto is not None and abs(proposto - misura) <= dim.tolerance:
                # Misura e valore del costruttore coincidono: non c'è nulla da
                # decidere, il numero *è* la misura.
                dim = dim.accept_measurement()
            else:
                # Divergenza: il valore non entra finché qualcuno non lo approva.
                divergenti.append(spec.id)
                dim = _with_proposal(dim, proposto)
            registry_.update(dim)

        ctx.log(f"{len(schema.SPECS)} quote in tabella: "
                f"{len(schema.SPECS) - len(divergenti) - len(mancanti)} coincidono con la "
                f"misura, {len(divergenti)} divergono, {len(mancanti)} non hanno una misura "
                f"scalare")

        # Le decisioni già registrate (A–G, S1) approvano le divergenti che
        # governano: le riapplica il job di analisi, che ha in mano il run.
        renders = _render_views(ctx)
        artifacts = {"params": params_path, **renders}

        rimaste = [d.id for d in registry_.blocking()]
        if rimaste:
            ctx.log("da decidere: " + ", ".join(rimaste))
        return StepResult(
            artifacts=artifacts,
            metrics={"quote": len(schema.SPECS), "divergenti": len(divergenti),
                     "senza_misura_scalare": len(mancanti)},
            notes=[
                "Le quote che coincidono con la misura sono accettate d'ufficio: sono "
                "la misura. Le divergenti restano da approvare.",
                "Le viste sono render della mesh, non del modello: servono a riconoscere "
                "il pezzo, non a quotarlo.",
            ],
        )

    def build(self, ctx: RunContext, registry_: Registry) -> StepResult:
        params_path = _params_for_build(ctx, registry_)
        ctx.log(f"costruzione con {BUILD.relative_to(ROOT)}")
        run_script(BUILD, cwd=ROOT, timeout_s=ctx.timeout_s, on_line=ctx.log,
                   env={"TAISER_PARAMS": str(params_path), "TAISER_OUT": str(ctx.run_dir)})

        # Gli STL di consegna sono a tassellazione fine (23 MB): per la pagina web
        # ne serve uno grossolano, che non sostituisce i primi.
        run_script(PREVIEW, [str(ctx.run_dir)], cwd=ROOT, timeout_s=ctx.timeout_s,
                   on_line=ctx.log)

        return StepResult(
            artifacts={
                "params": params_path,
                "preview": ctx.run_dir / "preview.stl",
                "step": ctx.run_dir / "model.step",
                "step_scatola": ctx.run_dir / "scatola.step",
                "step_coperchio": ctx.run_dir / "coperchio.step",
                "stl": ctx.run_dir / "model.stl",
                "fcstd": ctx.run_dir / "taiser.FCStd",
            },
            metrics={"quote_usate": len(registry_)},
        )

    def draw(self, ctx: RunContext, registry_: Registry) -> StepResult:
        params_path = _params_for_build(ctx, registry_)
        if not (ctx.run_dir / "taiser.FCStd").is_file():
            raise FileNotFoundError(
                "la tavola si genera dal modello: eseguire prima la build"
            )
        ctx.log(f"tavola con {DRAW.relative_to(ROOT)} su core/drafting/")
        run_script(DRAW, cwd=ROOT, timeout_s=ctx.timeout_s, on_line=ctx.log,
                   env={"TAISER_PARAMS": str(params_path), "TAISER_OUT": str(ctx.run_dir)})
        # Quattro fogli: viste, sezioni, coperchio, assonometria. L'elenco si
        # ricava dai file scritti, così aggiungere un foglio alla tavola non
        # richiede di ricordarsi di aggiornare anche questo.
        svg = sorted(ctx.run_dir.glob("drawing_p*.svg"),
                     key=lambda p: int(p.stem.rsplit("p", 1)[-1]))
        artefatti = {"pdf": ctx.run_dir / "drawing.pdf", "dxf": ctx.run_dir / "drawing.dxf"}
        for i, path in enumerate(svg, start=1):
            # L'anteprima nel browser è l'SVG: il motore di disegno è Python puro,
            # nessun FreeCAD nel percorso di visualizzazione.
            artefatti["svg" if i == 1 else f"svg_p{i}"] = path
        return StepResult(artifacts=artefatti, metrics={"fogli": len(svg)})

    def compare(self, ctx: RunContext, model_path: Path) -> StepResult:
        params_path = ctx.run_dir / "params.json"
        raw_path = ctx.run_dir / "compare_raw.json"
        ctx.log(f"confronto con {COMPARE.relative_to(ROOT)}")
        run_script(COMPARE, cwd=ROOT, timeout_s=ctx.timeout_s, on_line=ctx.log,
                   env={"TAISER_PARAMS": str(params_path), "TAISER_OUT": str(ctx.run_dir),
                        "TAISER_MESH": str(ctx.mesh_path), "TAISER_REPORT": str(raw_path),
                        "TAISER_N": os.environ.get("TAISER_N", "900")})

        raw = json.loads(raw_path.read_text())
        punti, parti = [], {}
        for nome, blocco in raw.items():
            if nome.startswith("_"):
                continue
            punti.extend(blocco["punti"])
            parti[nome] = {"stats": blocco["stats"], "worst": blocco["peggiori"],
                           "campionati": blocco["campionati"], "totali": blocco["totali"]}
        out = ctx.artifact("deviation.json")
        stats = deviation.write(out, punti, parti)
        return StepResult(
            artifacts={"deviation": out, "deviation_raw": raw_path},
            metrics={k: round(v, 4) for k, v in stats.items()},
            notes=["Ogni residuo oltre 0.5 mm è il raccordo di base: è la deviazione "
                   "voluta della decisione A."],
        )


# ---------------------------------------------------------------- utilità


def _with_proposal(dim: Dimension, proposto: float | None) -> Dimension:
    """Annota nella quota il valore che il costruttore proporrebbe.

    Annotare non è approvare: `used` resta vuoto e la quota continua a bloccare la
    build finché qualcuno non decide.
    """
    if proposto is None:
        return dim
    nota = f"proposto da {MEASURED_BY}: {proposto:g} {dim.unit}"
    return Dimension(**{**dim.__dict__,
                        "note": f"{dim.note} · {nota}" if dim.note else nota})


def _params_for_build(ctx: RunContext, registry_: Registry) -> Path:
    """Riscrive nel params.json del run i valori approvati, e lo restituisce.

    `registry_.values()` applica il cancello: se una quota non è né misurata né
    approvata, qui si solleva e la build non parte.
    """
    valori = registry_.values()
    params_path = ctx.run_dir / "params.json"
    if not params_path.is_file():
        raise FileNotFoundError(
            "params.json del run assente: eseguire prima l'analisi della mesh"
        )
    params = json.loads(params_path.read_text())
    cambiate = 0
    for dim_id, valore in valori.items():
        spec = schema.BY_ID[dim_id]
        if schema.read(params, spec.path) != valore:
            cambiate += 1
        schema.write(params, spec.path, valore)
    params_path.write_text(json.dumps(params, indent=2, ensure_ascii=False))
    if cambiate:
        ctx.log(f"{cambiate} quote riscritte in params.json dai valori approvati")
    return params_path


def _render_views(ctx: RunContext) -> dict[str, Path]:
    """Render ortografici della mesh, per riconoscere il pezzo a colpo d'occhio."""
    out_dir = ctx.run_dir / "views"
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        _run_python(RENDER, ctx, {}, args=[str(ctx.mesh_path), str(out_dir)])
    except subprocess.CalledProcessError as exc:
        # I render sono un di più: se falliscono, l'analisi resta valida.
        ctx.log(f"render non riusciti ({exc}): l'analisi prosegue")
        return {}
    return {f"view_{p.stem}": p for p in sorted(out_dir.glob("*.png"))}


def _run_python(script: Path, ctx: RunContext, env: dict[str, str],
                args: list[str] | None = None) -> None:
    """Esegue uno script `tools/` con l'interprete del backend (niente FreeCAD).

    cwd = radice del repo: gli script leggono i propri moduli da `tools/`.
    """
    proc = subprocess.Popen(
        [sys.executable, str(script), *(args or [])],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        cwd=str(ROOT), env={**os.environ, **env}, text=True, bufsize=1,
    )
    assert proc.stdout is not None
    coda: list[str] = []
    for riga in proc.stdout:
        riga = riga.rstrip("\n")
        coda.append(riga)
        ctx.log(riga)
    proc.wait(timeout=ctx.timeout_s)
    if proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, script.name,
                                            "\n".join(coda[-20:]))


plugin = registry.register(TeiserPart())
