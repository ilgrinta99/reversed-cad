import { useEffect, useState } from 'react'
import { api } from '../api.js'

// La tavola si vede nel browser senza passare da FreeCAD: il motore di disegno
// (core/drafting/) è Python puro e produce SVG. Gli stessi fogli escono in PDF e
// DXF dallo stesso codice — FreeCAD serve solo prima, per proiettare le viste.
// I fogli possono essere parecchi (uno per corpo, più sezioni e registro): la
// pulsantiera va a capo invece di allargare il pannello.
export default function DrawingPreview({ runId, sheets }) {
  const [index, setIndex] = useState(0)
  const [svg, setSvg] = useState(null)
  const [error, setError] = useState(null)

  const current = sheets[index]

  useEffect(() => {
    if (!current) return
    setSvg(null)
    setError(null)
    api.artifactText(runId, current).then(setSvg, (e) => setError(e.message))
  }, [runId, current])

  useEffect(() => {
    if (index >= sheets.length) setIndex(0)
  }, [sheets.length, index])

  return (
    <div className="panel">
      <h2>5 · Tavola</h2>
      {sheets.length === 0 && <p className="hint">Disponibile dopo lo step «Tavola».</p>}
      {sheets.length > 1 && (
        <div className="row" style={{ marginBottom: 10 }}>
          {sheets.map((name, i) => (
            <button key={name} className={i === index ? 'primary' : ''}
                    onClick={() => setIndex(i)}>
              Foglio {i + 1}
            </button>
          ))}
          <span className="provenance">{current}</span>
        </div>
      )}
      {error && <p className="error">{error}</p>}
      {svg && <div className="drawing" dangerouslySetInnerHTML={{ __html: svg }} />}
    </div>
  )
}
