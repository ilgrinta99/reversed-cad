import { useState } from 'react'
import { api } from '../api.js'

// Le domande che *questo* file solleva, una scheda per ciascuna.
//
// Compaiono dopo la misura, perché prima non esistono: non sono un catalogo
// scritto in anticipo, sono il risultato della lettura. Se il file non solleva
// domande, il pannello lo dice e il flusso prosegue senza chiedere niente.
//
// Ogni scheda si legge in due tempi: la domanda in italiano comune (`plain`,
// dal backend) e — per chi la vuole — la formulazione tecnica con le misure che
// l'hanno fatta nascere. Una domanda che non si capisce non è una domanda.
export default function DecisionCards({ runId, decisions, analysed, tecnico, bloccanti,
                                        onChanged }) {
  // Sette schede aperte fra il riepilogo e i risultati sono un muro: chi arriva
  // qui per vedere com'è andata deve scorrerle tutte. Restano chiuse finché non
  // bloccano niente — allora una riga basta a dire che ci sono — e si aprono da
  // sole quando senza una risposta il modello non si costruisce.
  const [aperto, setAperto] = useState(Boolean(bloccanti))
  if (!analysed) return null

  const items = decisions?.decisions ?? []
  const aperte = items.filter((d) => !d.resolved)
  const mostrate = tecnico ? items : aperte
  const visibili = aperto || tecnico || bloccanti

  return (
    <div className="panel">
      <h2>Cosa devo decidere</h2>
      {items.length === 0 ? (
        <>
          <p className="hint">
            Niente: ogni misura viene dal file e nessuna lettura è in conflitto con
            un’altra. Il modello si costruisce con le misure così come sono.
          </p>
          <span className="badge ok">nessuna domanda</span>
        </>
      ) : (
        <>
          <p className="hint">
            {aperte.length === 0
              ? 'Hai risposto a tutte. Puoi cambiare una risposta e rilanciare.'
              : bloccanti
                ? `Senza una risposta il modello non si costruisce: ${aperte.length}
                   ${aperte.length === 1 ? 'domanda' : 'domande'} in attesa.`
                : `Ci sono ${aperte.length} ${aperte.length === 1 ? 'punto' : 'punti'} in cui il
                   file non è conclusivo. Puoi rispondere adesso oppure lasciare che il
                   modello si costruisca con le misure così come sono: la scelta resta
                   registrata e si può cambiare in ogni momento.`}
          </p>
          {!visibili && (
            <div className="row">
              <button onClick={() => setAperto(true)}>
                Apri le {aperte.length === 1 ? 'domanda' : `${aperte.length} domande`}
              </button>
            </div>
          )}
          {visibili && mostrate.map((d) => (
            <DecisionCard key={d.id} runId={runId} decision={d} tecnico={tecnico}
                          onChanged={onChanged} />
          ))}
          {visibili && !tecnico && (
            <div className="row">
              <button onClick={() => setAperto(false)}>Chiudi le domande</button>
            </div>
          )}
        </>
      )}
    </div>
  )
}

function DecisionCard({ runId, decision, tecnico, onChanged }) {
  const [option, setOption] = useState(decision.chosen ?? '')
  const [rationale, setRationale] = useState(decision.rationale ?? '')
  const [dettagli, setDettagli] = useState(false)
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
        <h3 style={{ margin: 0 }}>{decision.plain || decision.question}</h3>
        <div className="spacer" />
        <span className={`badge ${decision.resolved ? 'ok' : 'warn'}`}>
          {decision.resolved ? 'risposto' : 'in attesa'}
        </span>
      </div>

      {decision.options.map((o) => (
        <label className="option" key={o.id}>
          <input type="radio" name={`d-${decision.id}`} value={o.id}
                 checked={option === o.id} onChange={() => setOption(o.id)} />
          <span>
            <strong>{o.label}</strong>
            {o.consequence && <div className="consequence">{o.consequence}</div>}
            {(o.accept_measured ?? []).length > 0 && (
              <div className="consequence">
                usa la misura del file per {o.accept_measured.length}{' '}
                {o.accept_measured.length === 1 ? 'quota' : 'quote'}
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

      <button type="button" className="link" onClick={() => setDettagli(!dettagli)}>
        {dettagli ? 'Nascondi il dettaglio tecnico' : 'Perché te lo sto chiedendo'}
      </button>
      {(dettagli || tecnico) && (
        <div className="dettaglio">
          <p className="evidence">{decision.title} · {decision.id}</p>
          <p style={{ margin: '6px 0' }}>{decision.question}</p>
          {decision.evidence && <p className="evidence">{decision.evidence}</p>}
          {Object.keys(decision.options.find((o) => o.id === option)?.sets ?? {}).length > 0 && (
            <p className="evidence">
              imposta {summarise(decision.options.find((o) => o.id === option).sets)}
            </p>
          )}
          {decision.reference && <p className="provenance">Riferimento: {decision.reference}</p>}
        </div>
      )}

      {decision.resolved && (
        <p className="provenance" style={{ marginTop: 8 }}>
          Risposto da {decision.resolved_by} il{' '}
          {new Date(decision.resolved_at).toLocaleString('it-IT')}
        </p>
      )}
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
