import { useState } from 'react'
import { api } from '../api.js'

// Le ambiguità che *questa* mesh solleva, una scheda per ciascuna. Compaiono dopo
// l'analisi, perché prima non esistono: non sono un catalogo scritto in anticipo,
// sono il risultato della misura. Se la mesh non ne solleva nessuna, il pannello
// lo dice e il flusso prosegue senza chiedere niente.
export default function DecisionCards({ runId, decisions, analysed, notes, onChanged }) {
  if (!analysed) return null

  const items = decisions?.decisions ?? []
  const pending = items.filter((d) => !d.resolved).length

  return (
    <div className="panel">
      <h2>3 · Ambiguità rilevate</h2>
      {items.length === 0 ? (
        <>
          <p className="hint">
            Nessuna ambiguità: ogni quota della tabella è misurata dalla mesh e
            nessuna lettura è in conflitto con un'altra. Il modello parametrico si
            costruisce con le misure così come sono.
          </p>
          <span className="badge ok">nessuna ambiguità</span>
        </>
      ) : (
        <>
          <p className="hint">
            L'analisi ha trovato {items.length}{' '}
            {items.length === 1 ? 'punto' : 'punti'} in cui la mesh non è
            conclusiva: {pending} da risolvere. Ogni scheda porta l'evidenza
            misurata e le opzioni con i numeri già calcolati. Ogni scelta viene
            registrata nel registro delle quote con la sua motivazione.
          </p>
          {items.map((d) => (
            <DecisionCard key={d.id} runId={runId} decision={d} onChanged={onChanged} />
          ))}
        </>
      )}
      {notes?.length > 0 && (
        <ul className="hint" style={{ marginTop: 12, paddingLeft: 18 }}>
          {notes.map((n) => <li key={n}>{n}</li>)}
        </ul>
      )}
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
                imposta {summarise(o.sets)}
              </div>
            )}
            {(o.accept_measured ?? []).length > 0 && (
              <div className="consequence">
                porta {o.accept_measured.length}{' '}
                {o.accept_measured.length === 1 ? 'quota' : 'quote'} al valore misurato
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

// Un'opzione di arrotondamento tocca decine di quote: elencarle tutte renderebbe
// la scheda illeggibile proprio dove serve decidere.
function summarise(sets) {
  const entries = Object.entries(sets)
  const shown = entries.slice(0, 4).map(([k, v]) => `${k} = ${v}`).join(', ')
  return entries.length > 4 ? `${shown} e altre ${entries.length - 4}` : shown
}
