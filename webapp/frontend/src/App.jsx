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
  const [analysis, setAnalysis] = useState(null)
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
  // Per la vista 3D si preferisce l'STL grossolano: quello di consegna è a
  // tassellazione fine e pesa decine di MB.
  const modelPath = has('preview.stl') ? 'preview.stl' : has('model.stl') ? 'model.stl' : null
  const sheets = artifacts
    .map((a) => a.path)
    .filter((p) => p.endsWith('.svg'))
    .sort()
  const buildable = readiness?.buildable ?? false
  const blockingCount = readiness?.blocking?.length ?? 0
  // Prima dell'analisi il run non ha quote: non è un errore, è che la mesh non è
  // ancora stata misurata. Finché è così, non c'è niente da decidere né da quotare.
  const analysed = (run?.provenance?.dimensions?.length ?? 0) > 0

  return (
    <>
      <header className="app">
        <h1>Reverse engineering CAD · dalla mesh al modello parametrico</h1>
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
              label="2 · Analisi della mesh"
              hint="Misura questa mesh: corpi, ingombri, pareti, raccordi, fori. Da qui
                    escono le quote del registro e le ambiguità da risolvere — nessuna
                    delle due è decisa prima di aver letto il file."
              onFinished={(job) => {
                setAnalysis(job?.result ?? null)
                refresh()
              }}
            />

            <DecisionCards
              runId={run.id}
              decisions={run.decisions}
              analysed={analysed}
              notes={analysis?.notes}
              onChanged={refresh}
            />

            {analysed && (
              <DimensionTable runId={run.id} provenance={run.provenance} onChanged={refresh} />
            )}

            <JobLog
              runId={run.id}
              kind="build"
              label="5 · Build del modello"
              hint="Costruisce i solidi dalle quote approvate e li esporta in STEP e STL."
              disabled={!analysed || !buildable}
              disabledReason={
                !analysed
                  ? 'Serve prima l’analisi della mesh.'
                  : blockingCount > 0
                    ? `${blockingCount} quote non sono né misurate né approvate: la build non parte.`
                    : null
              }
              onFinished={refresh}
            />

            <JobLog
              runId={run.id}
              kind="compare"
              label="5b · Confronto modello ↔ mesh"
              hint="Distanza fra la superficie costruita e la mesh di partenza: è qui che
                    si vede quanto costa ogni semplificazione dichiarata."
              disabled={!modelPath}
              disabledReason={!modelPath ? 'Serve prima la build.' : null}
              onFinished={refresh}
            />

            <ModelViewer
              runId={run.id}
              modelPath={modelPath}
              hasModel={!!modelPath}
              hasDeviation={has('deviation.json')}
            />

            <JobLog
              runId={run.id}
              kind="draw"
              label="6 · Tavola"
              hint="Genera la tavola. L'anteprima SVG non richiede FreeCAD."
              disabled={!analysed || !buildable}
              disabledReason={!analysed ? 'Serve prima l’analisi della mesh.' : null}
              onFinished={refresh}
            />

            <DrawingPreview runId={run.id} sheets={sheets} />

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
                <button onClick={() => { setRun(null); setAnalysis(null) }}>Nuovo run</button>
              </div>
            </div>
          </>
        )}
      </main>
    </>
  )
}
