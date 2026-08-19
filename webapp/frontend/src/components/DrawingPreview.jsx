import { useEffect, useState } from 'react'
import { api } from '../api.js'

// La tavola si vede nel browser senza passare da FreeCAD: il motore di disegno
// è Python puro e produce SVG.
export default function DrawingPreview({ runId, available }) {
  const [svg, setSvg] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!available) return
    api.artifactText(runId, 'drawing.svg').then(setSvg, (e) => setError(e.message))
  }, [runId, available])

  return (
    <div className="panel">
      <h2>5 · Tavola</h2>
      {!available && <p className="hint">Disponibile dopo lo step «Tavola».</p>}
      {error && <p className="error">{error}</p>}
      {svg && <div className="drawing" dangerouslySetInnerHTML={{ __html: svg }} />}
    </div>
  )
}
