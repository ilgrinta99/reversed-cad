"""Esecuzione headless di script FreeCAD, con i vincoli del BUILD-LOG incorporati.

Non chiamare FreeCAD direttamente da altrove: le trappole verificate sul campo sono
qui e solo qui.

1. stdin CHIUSO. `FreeCAD -c script.py` senza `< /dev/null` esegue lo script e poi
   resta appeso sulla console interattiva. Il primo build sembrava impiegare 15
   minuti: ogni passo costava 0.01 s, era il processo che non usciva.
2. TIMEOUT esplicito, con kill dell'intero gruppo di processi. Un job che non esce
   non deve poter bloccare il worker.
3. GLI ARGOMENTI NON PASSANO DA argv. `FreeCAD -c script.py a b` lascia sì `a` e `b`
   in `sys.argv`, ma insieme al binario e a `-c` (quindi `sys.argv[1]` è `-c`), e
   soprattutto FreeCAD prova ad APRIRE `a` e `b` come documenti: un params.json
   finisce nell'importatore di mesh FEM e produce un traceback. Gli argomenti si
   passano nell'ambiente, in `TEISER_ARGS` (JSON), e lo script li legge da lì.
4. FreeCAD AZZERA PYTHONPATH. Dentro lo script `os.environ["PYTHONPATH"]` è vuota e
   la radice del repo non è su `sys.path`: `import core...` fallisce. Il runner passa
   la radice in `TEISER_REPO_ROOT`, e ogni script inizia con il prologo di tre righe
   documentato in `core/freecad/script.py`.
5. IL CODICE DI USCITA MENTE. Un'eccezione non catturata nello script fa uscire
   FreeCAD con rc=0: il job risulterebbe riuscito senza aver prodotto nulla.
   (`sys.exit(n)` invece propaga correttamente.) Per questo ogni script deve
   stampare `TEISER_OK` come ultima riga, e il runner pretende di vederla.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Sequence

#: Percorsi provati, in ordine, quando FREECAD_BIN non è impostata.
#: Su macOS il binario `FreeCADCmd` non esiste più: si usa `FreeCAD -c`.
CANDIDATE_BINARIES: tuple[str, ...] = (
    "/Applications/FreeCAD.app/Contents/MacOS/FreeCAD",  # macOS, Homebrew cask
    "freecad",  # conda-forge / distro
    "FreeCAD",
    "freecadcmd",
    "FreeCADCmd",
)

DEFAULT_TIMEOUT_S = 300.0

#: Riga che uno script deve stampare per dichiararsi riuscito. Vedi trappola 4.
SUCCESS_SENTINEL = "TEISER_OK"

#: Variabile d'ambiente con gli argomenti dello script, in JSON. Vedi trappola 3.
ARGS_ENV = "TEISER_ARGS"

#: Radice del repo, da cui gli script rimettono `core.*` su sys.path. Vedi trappola 4.
ROOT_ENV = "TEISER_REPO_ROOT"


class FreeCADNotFound(RuntimeError):
    pass


class FreeCADTimeout(RuntimeError):
    def __init__(self, timeout_s: float, tail: str) -> None:
        super().__init__(f"FreeCAD non è uscito entro {timeout_s:g}s. Ultime righe:\n{tail}")
        self.timeout_s = timeout_s
        self.tail = tail


class FreeCADFailed(RuntimeError):
    def __init__(self, returncode: int, tail: str, reason: str = "") -> None:
        detail = reason or f"FreeCAD è uscito con codice {returncode}"
        super().__init__(f"{detail}. Ultime righe:\n{tail}")
        self.returncode = returncode
        self.tail = tail


@dataclass(frozen=True)
class FreeCADResult:
    returncode: int
    output: str
    duration_s: float


def find_freecad(explicit: str | None = None) -> str:
    """Risolve il binario FreeCAD, o solleva FreeCADNotFound con un messaggio utile."""
    for candidate in (explicit, os.environ.get("FREECAD_BIN"), *CANDIDATE_BINARIES):
        if not candidate:
            continue
        if os.path.isabs(candidate):
            if os.access(candidate, os.X_OK):
                return candidate
            continue
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    raise FreeCADNotFound(
        "Nessun binario FreeCAD trovato. Imposta FREECAD_BIN, oppure installa "
        "FreeCAD (conda-forge nel container, cask Homebrew su macOS). "
        f"Provati: {', '.join(c for c in CANDIDATE_BINARIES)}"
    )


def run_script(
    script: str | Path,
    args: Sequence[str] = (),
    *,
    cwd: str | Path | None = None,
    env: dict[str, str] | None = None,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    on_line: Callable[[str], None] | None = None,
    binary: str | None = None,
    expect_sentinel: str | None = SUCCESS_SENTINEL,
) -> FreeCADResult:
    """Esegue uno script sotto FreeCAD headless e ne restituisce l'output.

    `args` NON finisce in `sys.argv`: viaggia in `TEISER_ARGS` come JSON, perché
    FreeCAD tratterebbe gli argomenti posizionali come file da aprire (trappola 3).
    Lo script li rilegge con `core.freecad.script.args()`, dopo il prologo che
    rimette la radice del repo su `sys.path` (trappola 4).

    `expect_sentinel` è la riga che lo script deve stampare per essere considerato
    riuscito: senza, un'eccezione non catturata passerebbe per successo (trappola 5).
    Passare `None` solo per script che non si possono modificare.

    `on_line` riceve ogni riga appena prodotta: è il gancio per lo streaming dei
    log verso il job runner. stdout e stderr sono uniti, così l'ordine è quello
    reale.
    """
    script = Path(script)
    if not script.is_file():
        raise FileNotFoundError(f"Script FreeCAD inesistente: {script}")

    binary = find_freecad(binary)
    cmd = [binary, "-c", str(script)]  # nessun argomento posizionale: vedi trappola 3

    full_env = {**os.environ, **(env or {}), ARGS_ENV: json.dumps(list(args))}
    # FreeCAD azzera PYTHONPATH (trappola 4): la radice del repo viaggia su una
    # variabile propria, e lo script se la rimette su sys.path da sé.
    full_env[ROOT_ENV] = str(Path(__file__).resolve().parents[2])
    # FreeCAD in container non ha display: senza questo alcuni build Qt provano
    # comunque a contattare un X server e falliscono tardi e male.
    full_env.setdefault("QT_QPA_PLATFORM", "offscreen")

    started = time.monotonic()
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,  # vincolo 1: MAI ereditare uno stdin interattivo
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=str(cwd) if cwd else None,
        env=full_env,
        text=True,
        bufsize=1,
        start_new_session=True,  # gruppo proprio, così il kill del timeout è completo
    )

    # Il timeout non può essere controllato dentro il ciclo di lettura: `readline`
    # blocca, e uno script appeso che smette di stampare non farebbe mai un giro.
    # Serve un watchdog indipendente — è proprio il caso della console interattiva.
    timed_out = threading.Event()

    def _watchdog() -> None:
        timed_out.set()
        _kill_group(proc)

    watchdog = threading.Timer(timeout_s, _watchdog)
    watchdog.daemon = True
    watchdog.start()

    lines: list[str] = []
    try:
        assert proc.stdout is not None
        for raw in proc.stdout:
            line = raw.rstrip("\n")
            lines.append(line)
            if on_line is not None:
                on_line(line)
        proc.wait()
    except BaseException:
        _kill_group(proc)
        raise
    finally:
        watchdog.cancel()
        if proc.stdout is not None:
            proc.stdout.close()

    duration = time.monotonic() - started
    if timed_out.is_set():
        raise FreeCADTimeout(timeout_s, _tail(lines))
    if proc.returncode != 0:
        raise FreeCADFailed(proc.returncode, _tail(lines))
    if expect_sentinel is not None and not any(l.strip() == expect_sentinel for l in lines):
        raise FreeCADFailed(
            proc.returncode,
            _tail(lines),
            reason=(
                f"lo script non ha stampato {expect_sentinel!r}: è fallito a metà. "
                "FreeCAD esce con codice 0 anche dopo un'eccezione, quindi il codice "
                "di uscita non basta"
            ),
        )
    return FreeCADResult(proc.returncode, "\n".join(lines), duration)


def _kill_group(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        try:
            proc.wait(timeout=5)
            return
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        proc.kill()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass


def _tail(lines: Iterable[str], n: int = 30) -> str:
    kept = list(lines)[-n:]
    return "\n".join(kept) if kept else "(nessun output)"
