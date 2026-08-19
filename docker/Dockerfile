# Immagine Linux con FreeCAD headless per la pipeline Teiser.
#
# FreeCAD viene da conda-forge, non da AppImage: nessun FUSE, nessuna estrazione,
# e `import FreeCAD` funziona direttamente dal Python dell'ambiente.
#
# La versione è pinnata a 1.1.3, la stessa installata via Homebrew cask sul Mac di
# sviluppo. Divergenze di minor fra locale e container sono la causa più probabile
# di «funziona sul Mac, non nel container»: se si aggiorna qui, si aggiorna là.
#
# Verificato in questa sessione (container Linux x86_64, senza display):
#   freecad 1.1.3 py311h1922e53_0 · occt 7.9.3 · python 3.11 · numpy 2.4.6
#   import FreeCAD/Part/TechDraw ok, export STEP+STL ok, uno script gira in ~0.3 s.

FROM mambaorg/micromamba:2.3-debian12-slim AS base

USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl libgl1 libglx-mesa0 libegl1 libxkbcommon0 \
    && rm -rf /var/lib/apt/lists/*

ENV MAMBA_ROOT_PREFIX=/opt/conda \
    ENV_PREFIX=/opt/env \
    QT_QPA_PLATFORM=offscreen \
    LC_ALL=C.UTF-8 \
    LANG=C.UTF-8 \
    PYTHONUNBUFFERED=1

# FreeCAD e le dipendenze scientifiche in un unico solve, così le versioni sono
# coerenti fra loro e con il Python che eseguirà anche il backend.
RUN micromamba create -y -p ${ENV_PREFIX} -c conda-forge \
        python=3.11 \
        freecad=1.1.3 \
        numpy \
        ezdxf \
    && micromamba clean --all --yes

ENV PATH=${ENV_PREFIX}/bin:$PATH \
    FREECAD_BIN=${ENV_PREFIX}/bin/freecad

WORKDIR /app

# Il backend gira sullo stesso interprete dell'ambiente conda: un solo Python,
# nessun ponte fra venv e FreeCAD.
COPY webapp/backend/requirements.txt /app/webapp/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/webapp/backend/requirements.txt

COPY docker/freecad_smoke.py /app/docker/freecad_smoke.py

# Un'immagine che non sa eseguire FreeCAD headless non deve nemmeno essere
# prodotta. `< /dev/null` è obbligatorio: senza, FreeCAD esegue lo script e poi
# resta appeso sulla console interattiva, e il build non termina mai.
RUN freecad -c /app/docker/freecad_smoke.py < /dev/null

COPY core /app/core
COPY parts /app/parts
COPY webapp/backend /app/webapp/backend

ENV PYTHONPATH=/app \
    TEISER_RUNS_DIR=/data/runs \
    TEISER_DB_PATH=/data/teiser.db

RUN mkdir -p /data/runs
VOLUME ["/data"]

EXPOSE 8000
CMD ["uvicorn", "webapp.backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
