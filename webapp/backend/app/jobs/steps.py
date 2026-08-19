"""Gli step della pipeline, come job.

Ogni step: carica il run, chiama il plugin del pezzo, salva quel che è cambiato.
Il cancello sulle quote (`registry.values()`) sta dentro `build` e `draw`, dove
serve — non è aggirabile passando da un altro endpoint.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable

from core.plugin import RunContext, StepResult, registry as part_registry
from core.provenance import UnapprovedDimensions
from webapp.backend.app.jobs.queue import Job, queue
from webapp.backend.app.storage.runs import Run, get_run, save_run

Logger = Callable[[str], None]


def _context(run: Run, log: Logger) -> RunContext:
    return RunContext(
        run_id=run.id,
        mesh_path=run.mesh_path,
        run_dir=run.dir,
        references=run.references,
        log=log,
        timeout_s=float(os.environ.get("TEISER_JOB_TIMEOUT_S", "600")),
    )


def _relative(result: StepResult, run: Run) -> dict[str, Any]:
    """Gli artefatti escono dall'API come percorsi relativi al run: il client non
    deve conoscere il filesystem del server."""
    out = result.to_dict()
    out["artifacts"] = {
        name: str(Path(path).resolve().relative_to(run.dir.resolve()))
        for name, path in result.artifacts.items()
    }
    return out


def submit_analyze(run_id: str) -> Job:
    def work(log: Logger) -> dict[str, Any]:
        run = get_run(run_id)
        plugin = part_registry.get(run.part_id)
        ctx = _context(run, log)
        log(f"mesh: {run.mesh_path.name}")
        result = plugin.measure(ctx, run.registry)
        save_run(run)

        blocking = run.registry.blocking()
        if blocking:
            log(f"{len(blocking)} quote restano da decidere: "
                + ", ".join(d.id for d in blocking))
        else:
            log("tutte le quote sono misurate o approvate")
        payload = _relative(result, run)
        payload["provenance"] = run.registry.to_dict()
        return payload

    return queue.submit(run_id, "analyze", work)


def submit_build(run_id: str) -> Job:
    def work(log: Logger) -> dict[str, Any]:
        run = get_run(run_id)
        plugin = part_registry.get(run.part_id)
        ctx = _context(run, log)
        try:
            run.registry.assert_buildable()
        except UnapprovedDimensions as exc:
            # Non si stima e non si va avanti: è la regola non negoziabile.
            log(str(exc))
            raise
        log(f"{len(run.registry)} quote verificate, costruzione in corso")
        result = plugin.build(ctx, run.registry)
        save_run(run)
        return _relative(result, run)

    return queue.submit(run_id, "build", work)


def submit_draw(run_id: str) -> Job:
    def work(log: Logger) -> dict[str, Any]:
        run = get_run(run_id)
        plugin = part_registry.get(run.part_id)
        run.registry.assert_buildable()
        result = plugin.draw(_context(run, log), run.registry)
        save_run(run)
        return _relative(result, run)

    return queue.submit(run_id, "draw", work)


def submit_compare(run_id: str, model_name: str = "model.stl") -> Job:
    def work(log: Logger) -> dict[str, Any]:
        run = get_run(run_id)
        plugin = part_registry.get(run.part_id)
        model_path = run.dir / model_name
        if not model_path.is_file():
            raise FileNotFoundError(
                f"nessun modello da confrontare in {model_name}: eseguire prima la build"
            )
        result = plugin.compare(_context(run, log), model_path)
        return _relative(result, run)

    return queue.submit(run_id, "compare", work)


SUBMITTERS: dict[str, Callable[[str], Job]] = {
    "analyze": submit_analyze,
    "build": submit_build,
    "draw": submit_draw,
    "compare": submit_compare,
}
