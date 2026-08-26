import { useCallback, useEffect, useState } from 'react'
import { api } from './api.js'
import UploadPanel from './components/UploadPanel.jsx'
import Pipeline from './components/Pipeline.jsx'
import Riepilogo from './components/Riepilogo.jsx'
import DecisionCards from './components/DecisionCards.jsx'
import DimensionTable from './components/DimensionTable.jsx'
import JobLog from './components/JobLog.jsx'
import ModelViewer from './components/ModelViewer.jsx'
import DrawingPreview from './components/DrawingPreview.jsx'
import Downloads from './components/Downloads.jsx'

// La pagina ha due letture.
//
// Quella normale risponde a tre domande e basta: che file ho caricato, cosa ne è
// uscito, cosa manca. Un pulsante, un riepilogo in italiano, il modello e la
// tavola da guardare, i file da scaricare.
//
// Quella tecnica — l'interruttore in alto — riapre tutto il resto: i passaggi uno
// per uno con i loro log, la tabella delle 55 quote con misurato/usato/delta, il
// registro completo dei file. Non è roba nascosta: è roba che serve dopo, e che
// prima impedisce di capire se le cose sono andate bene.
export default function App() {
  const [health, setHealth] = useState(null)
  const [run, setRun] = useState(null)
  const [readiness, setReadiness] = useState(null)
  const [artifacts, setArtifacts] = useState([])
  const [summary, setSummary] = useState(null)
  const [tecnico, setTecnico] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.health().then(setHealth, (e) => setError(e.message))
  }, [])

  const refresh = useCallback(async () => {
    if (!run) return
    try {
      const [fresh, ready, files, riepilogo] = await Promise.all([
        api.getRun(run.id),
        api.readiness(run.id),
        api.artifacts(run.id),
        api.summary(run.id),
      ])
      setRun(fresh)
      setReadiness(ready)
      setArtifacts(files)
      setSummary(riepilogo)
    } catch (e) {
      setError(e.message)
    }
  }, [run?.id])

  useEffect(() => { if (run) refresh() }, [run?.id])

  const has = (name) => artifacts.some((a) => a.path === name)
  // Per la vista 3D si preferisce l'STL grossolano: quello di consegna è a
  // tassellazione fine e pesa decine di MB.
  const modelPath = has('preview.stl') ? 'preview.stl' : has('model.stl') ? 'model.stl' : null
  const sheets = artifacts.map((a) => a.path).filter((p) => p.endsWith('.svg')).sort()
  const buildable = readiness?.buildable ?? false
  const blockingCount = readiness?.blocking?.length ?? 0
  // Prima dell'analisi il run non ha quote: non è un errore, è che la mesh non è
  // ancora stata misurata. Finché è così, non c'è niente da decidere né da quotare.
  const analysed = (run?.provenance?.dimensions?.length ?? 0) > 0
  const daDecidere = (run?.decisions?.decisions ?? []).filter((d) => !d.resolved).length

  return (
    <>
      <header className="app">
        <h1>Da una mesh a un modello CAD quotato</h1>
        {health && !health.freecad && (
          <span className="badge bad">
            FreeCAD non disponibile: posso misurare il file, non costruire il modello
          </span>
        )}
        <div className="spacer" />
        {run && <span className="sub">{run.title || run.mesh_name}</span>}
        <label className="interruttore">
          <input type="checkbox" checked={tecnico}
                 onChange={(e) => setTecnico(e.target.checked)} />
          Modalità tecnica
        </label>
      </header>

      <main>
        {error && <p className="error">{error}</p>}

        {!run && <UploadPanel formats={health?.mesh_formats} onCreated={setRun} />}

        {run && (
          <>
            <Pipeline
              runId={run.id}
              onFinito={refresh}
              disabled={analysed && !buildable}
              disabledReason={
                analysed && !buildable
                  ? `${blockingCount} misure non sono né misurate né approvate: rispondi prima alle domande qui sotto.`
                  : null
              }
            />

            <Riepilogo summary={summary} onApri={() => setTecnico(true)} />

            {analysed && (daDecidere > 0 || tecnico) && (
              <DecisionCards
                runId={run.id}
                decisions={run.decisions}
                analysed={analysed}
                tecnico={tecnico}
                bloccanti={analysed && !buildable}
                onChanged={refresh}
              />
            )}

            <ModelViewer
              runId={run.id}
              modelPath={modelPath}
              hasModel={!!modelPath}
              hasDeviation={has('deviation.json')}
            />

            <DrawingPreview runId={run.id} sheets={sheets} />

            <Downloads runId={run.id} artifacts={artifacts} tutti={tecnico} />

            {tecnico && (
              <>
                {analysed && (
                  <DimensionTable runId={run.id} provenance={run.provenance}
                                  onChanged={refresh} />
                )}

                <div className="panel">
                  <h2>Passaggi singoli</h2>
                  <p className="hint">
                    Gli stessi quattro passaggi della catena, uno per uno, con il
                    log completo. Servono per rifarne uno solo dopo aver cambiato
                    una quota, senza ripartire da capo.
                  </p>
                </div>
                <JobLog runId={run.id} kind="analyze" label="Misura del file"
                        hint="Corpi, ingombri, pareti, raccordi, fori, cupole. Da qui
                              escono le quote del registro e le domande da risolvere."
                        onFinished={refresh} />
                <JobLog runId={run.id} kind="build" label="Costruzione del solido"
                        hint="Costruisce i solidi dalle quote approvate ed esporta STEP e STL."
                        disabled={!analysed || !buildable} onFinished={refresh} />
                <JobLog runId={run.id} kind="compare" label="Confronto con la mesh"
                        hint="Distanza fra la superficie costruita e il file di partenza."
                        disabled={!modelPath} onFinished={refresh} />
                <JobLog runId={run.id} kind="draw" label="Tavola"
                        hint="Viste, sezioni, quote, registro della provenienza."
                        disabled={!analysed || !buildable} onFinished={refresh} />

                <div className="panel">
                  <h2>Varianti</h2>
                  <p className="hint">
                    Per rilanciare con quote diverse si crea una variante: questa
                    prova resta intatta, con la sua provenienza.
                  </p>
                  <div className="row">
                    <button onClick={() =>
                      api.forkRun(run.id).then(setRun, (e) => setError(e.message))}>
                      Crea variante
                    </button>
                  </div>
                </div>
              </>
            )}

            <div className="panel">
              <div className="row">
                <button onClick={() => { setRun(null); setSummary(null) }}>
                  Carica un altro file
                </button>
              </div>
            </div>
          </>
        )}
      </main>
    </>
  )
}
