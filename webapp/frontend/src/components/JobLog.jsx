import { useEffect, useRef, useState } from 'react'
import { api, streamJob } from '../api.js'

// Avvia uno step e ne mostra i log mentre arrivano. Gli step lunghi non stanno
// in una richiesta sincrona: qui si vede cosa sta facendo, riga per riga.
export default function JobLog({ runId, kind, label, hint, onFinished, disabled, disabledReason }) {
  const [lines, setLines] = useState([])
  const [job, setJob] = useState(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState(null)
  const box = useRef(null)
  const stop = useRef(null)

  useEffect(() => () => stop.current?.(), [])
  useEffect(() => {
    if (box.current) box.current.scrollTop = box.current.scrollHeight
  }, [lines])

  async function start() {
    setLines([])
    setError(null)
    setJob(null)
    setRunning(true)
    try {
      const started = await api.startJob(runId, kind)
      stop.current = streamJob(
        started.id,
        (line) => setLines((prev) => [...prev, line]),
        (finished) => {
          setJob(finished)
          setRunning(false)
          if (finished.state === 'failed') setError(finished.error)
          onFinished?.(finished)
        },
      )
    } catch (e) {
      setError(e.message)
      setRunning(false)
    }
  }

  return (
    <div className="panel">
      <h2>{label}</h2>
      {hint && <p className="hint">{hint}</p>}
      <div className="row">
        <button className="primary" onClick={start} disabled={running || disabled}>
          {running ? 'In corso…' : 'Esegui'}
        </button>
        {job && (
          <span className={`badge ${job.state === 'succeeded' ? 'ok' : 'bad'}`}>
            {job.state === 'succeeded' ? 'completato' : 'fallito'}
          </span>
        )}
        {disabled && disabledReason && <span className="note">{disabledReason}</span>}
      </div>
      {lines.length > 0 && (
        <div className="log" ref={box} style={{ marginTop: 12 }}>
          {lines.join('\n')}
        </div>
      )}
      {error && <p className="error">{error}</p>}
    </div>
  )
}
