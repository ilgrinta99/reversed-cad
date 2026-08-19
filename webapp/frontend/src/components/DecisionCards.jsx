import { useState } from 'react'
import { api } from '../api.js'

// Le discrepanze (D1–D8) e le ambiguità (A–G) come schede da risolvere una per una.
// Non sono un pannello avanzato: sono il cuore del flusso.
export default function DecisionCards({ runId, decisions, onChanged }) {
  const items = decisions?.decisions ?? []
  if (items.length === 0) return null
  return (
    <div className="panel">
      <h2>2 · Discrepanze e ambiguità</h2>
      <p className="hint">
        Dove la mesh non è conclusiva, o dove modello e riferimento non concordano,
        decidi tu. Ogni scelta viene registrata nel registro delle quote con la sua
        motivazione.
      </p>
      {items.map((d) => (
        <DecisionCard key={d.id} runId={runId} decision={d} onChanged={onChanged} />
      ))}
    </div>
  )
}

function DecisionCard({ runId, decision, onChanged }) {
  const [option, setOption] = useState(decision.chosen ?? '')
  const [rationale, setRationale] = useState(decision.rationale ?? '')
  const [error, setError] = useState(null)

  async function submit(event) {
    event.preventDefault()
    setError(null)
    try {
      await api.resolveDecision(runId, decision.id, option, rationale)
      onChanged()
    } catch (e) {
      setError(e.message)
    }
  }

  return (
    <form className="decision" onSubmit={submit}>
      <div className="row">
        <span className="kind">
          {decision.kind === 'discrepancy' ? 'discrepanza' : 'ambiguità'} · {decision.id}
        </span>
        <div className="spacer" />
        <span className={`badge ${decision.resolved ? 'ok' : 'warn'}`}>
          {decision.resolved ? 'risolta' : 'da risolvere'}
        </span>
      </div>
      <h3>{decision.title}</h3>
      <p style={{ margin: '6px 0' }}>{decision.question}</p>
      {decision.evidence && <p className="evidence">{decision.evidence}</p>}

      {decision.options.map((o) => (
        <label className="option" key={o.id}>
          <input type="radio" name={`d-${decision.id}`} value={o.id}
                 checked={option === o.id} onChange={() => setOption(o.id)} />
          <span>
            <strong>{o.label}</strong>
            {o.consequence && <div className="consequence">{o.consequence}</div>}
            {Object.keys(o.sets ?? {}).length > 0 && (
              <div className="consequence">
                imposta {Object.entries(o.sets).map(([k, v]) => `${k} = ${v}`).join(', ')}
              </div>
            )}
          </span>
        </label>
      ))}

      <div className="row" style={{ marginTop: 8 }}>
        <input style={{ flex: 1 }} required value={rationale} placeholder="Perché questa scelta"
               onChange={(e) => setRationale(e.target.value)} />
        <button className="primary" type="submit" disabled={!option}>
          {decision.resolved ? 'Aggiorna' : 'Registra'}
        </button>
      </div>
      {decision.resolved && (
        <p className="provenance" style={{ marginTop: 8 }}>
          Risolta da {decision.resolved_by} il{' '}
          {new Date(decision.resolved_at).toLocaleString('it-IT')}
        </p>
      )}
      {decision.reference && <p className="provenance">Riferimento: {decision.reference}</p>}
      {error && <p className="error">{error}</p>}
    </form>
  )
}
