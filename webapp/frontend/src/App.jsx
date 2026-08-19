import { useCallback, useEffect, useState } from 'react'
import { api } from './api.js'
import UploadPanel from './components/UploadPanel.jsx'
import DecisionCards from './components/DecisionCards.jsx'
import DimensionTable from './components/DimensionTable.jsx'
import JobLog from './components/JobLog.jsx'
import ModelViewer from './components/ModelViewer.jsx'
import DrawingPreview from './components/DrawingPreview.jsx'
import Downloads from './components/Downloads.jsx'

export default function App() {
  const [health, setHealth] = useState(null)
  const [run, setRun] = useState(null)
  const [readiness, setReadiness] = useState(null)
  const [artifacts, setArtifacts] = useState([])
  const [error, setError] = useState(null)

  useEffect(() => {
    api.health().then(setHealth, (e) => setError(e.message))
  }, [])

  const refresh = useCallback(async () => {
    if (!run) return
    try {
      const [fresh, ready, files] = await Promise.all([
        api.getRun(run.id),
        api.readiness(run.id),
        api.artifacts(run.id),
      ])
      setRun(fresh)
      setReadiness(ready)
      setArtifacts(files)
    } catch (e) {
      setError(e.message)
    }
  }, [run?.id])

  useEffect(() => { if (run) refresh() }, [run?.id])

  const has = (name) => artifacts.some((a) => a.path === name)
  const buildable = readiness?.buildable ?? false
  const blockingCount = readiness?.blocking?.length ?? 0

  return (
    <>
      <header className="app">
        <h1>Teiser · reverse engineering CAD</h1>
        <span className="sub">
          {health
            ? health.freecad
              ? 'FreeCAD disponibile'
              : 'FreeCAD non disponibile: analisi e tavola funzionano, la build no'
            : '…'}
        </span>
        <div className="spacer" />
        {run && (
          <span className="sub">
            run {run.id} · {run.title}
            {run.parent_id && ` · variante di ${run.parent_id}`}
          </span>
        )}
      </header>

      <main>
        {error && <p className="error">{error}</p>}

        {!run && <UploadPanel onCreated={setRun} />}

        {run && (
          <>
            <JobLog
              runId={run.id}
              kind="analyze"
              label="1 · Analisi della mesh"
              hint="Misura la mesh e riempie il registro delle quote. Ogni valore porta il nome dello script che l'ha prodotto."
              onFinished={refresh}
            />

            <DecisionCards runId={run.id} decisions={run.decisions} onChanged={refresh} />

            <DimensionTable runId={run.id} provenance={run.provenance} onChanged={refresh} />

            <JobLog
              runId={run.id}
              kind="build"
              label="4 · Build del modello"
              hint="Costruisce i solidi e li esporta in STEP e STL."
              disabled={!buildable}
              disabledReason={
                blockingCount > 0
                  ? `${blockingCount} quote non sono né misurate né approvate: la build non parte.`
                  : null
              }
              onFinished={refresh}
            />

            <JobLog
              runId={run.id}
              kind="compare"
              label="4b · Confronto modello ↔ mesh"
              hint="Distanza fra la superficie costruita e la mesh di partenza."
              disabled={!has('model.stl')}
              disabledReason={!has('model.stl') ? 'Serve prima la build.' : null}
              onFinished={refresh}
            />

            <ModelViewer
              runId={run.id}
              meshName={run.mesh_name}
              hasModel={has('model.stl')}
              hasDeviation={has('deviation.json')}
            />

            <JobLog
              runId={run.id}
              kind="draw"
              label="5 · Tavola"
              hint="Genera la tavola. L'anteprima SVG non richiede FreeCAD."
              disabled={!buildable}
              onFinished={refresh}
            />

            <DrawingPreview runId={run.id} available={has('drawing.svg')} />

            <Downloads runId={run.id} artifacts={artifacts} />

            <div className="panel">
              <h2>Varianti</h2>
              <p className="hint">
                Per rilanciare con parametri diversi si crea una variante: il run
                attuale resta intatto, con la sua provenance.
              </p>
              <div className="row">
                <button onClick={() => api.forkRun(run.id).then(setRun, (e) => setError(e.message))}>
                  Crea variante
                </button>
                <button onClick={() => setRun(null)}>Nuovo run</button>
              </div>
            </div>
          </>
        )}
      </main>
    </>
  )
}
