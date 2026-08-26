import { useState } from 'react'
import { api } from '../api.js'

const BADGE = {
  measured_ok: ['ok', 'misurato'],
  approved_override: ['warn', 'approvato'],
  derived_ok: ['ok', 'derivato'],
  unapproved_divergence: ['bad', 'divergenza non approvata'],
  missing: ['bad', 'da risolvere'],
}

const fmt = (v, unit) => (v === null || v === undefined ? '—' : `${v.toFixed(3)} ${unit}`)

// Misurato contro usato, con la provenienza sempre in vista: nessun valore entra
// nel modello senza passare di qui.
//
// Su una mesh vera sono cinquanta righe con nomi come `c1_cupola1_semiasse_x`, e
// quasi tutte dicono la stessa cosa — misurato = usato, delta zero. Aprire su
// tutte vuol dire nascondere le tre che contano dentro le cinquanta che non
// contano, quindi si aprono quelle: bloccanti e divergenti. Le altre restano a
// un clic, che è dove devono stare, non altrove.
export default function DimensionTable({ runId, provenance, onChanged }) {
  const [tutte, setTutte] = useState(false)
  const [editing, setEditing] = useState(null)
  const [value, setValue] = useState('')
  const [rationale, setRationale] = useState('')
  const [error, setError] = useState(null)

  const dims = provenance?.dimensions ?? []
  const blocking = dims.filter((d) => d.blocks_build).length
  const diverging = dims.filter((d) => d.diverges).length
  const attenzione = dims.filter((d) => d.blocks_build || d.diverges)
  const mostrate = tutte || attenzione.length === 0 ? dims : attenzione

  async function accept(dim) {
    setError(null)
    try {
      await api.acceptMeasured(runId, dim.id)
      onChanged()
    } catch (e) {
      setError(e.message)
    }
  }

  async function approve(event) {
    event.preventDefault()
    setError(null)
    try {
      await api.approve(runId, editing.id, Number(value), rationale)
      setEditing(null)
      setRationale('')
      onChanged()
    } catch (e) {
      setError(e.message)
    }
  }

  function beginApprove(dim) {
    setEditing(dim)
    setValue(String(dim.used ?? dim.measured ?? ''))
    setRationale('')
    setError(null)
  }

  return (
    <div className="panel">
      <h2>Le misure, una per una</h2>
      <p className="hint">
        Ogni numero che entra nel modello è misurato dal file oppure approvato da te,
        con la motivazione registrata. {blocking > 0
          ? `${blocking} misure bloccano la costruzione.`
          : 'Nessuna misura bloccante.'}{' '}
        {diverging > 0
          ? `${diverging} si discostano dal file e restano segnalate.`
          : 'Nessuna si discosta dal file.'}
      </p>
      <div className="row" style={{ marginBottom: 10 }}>
        <span className="note">
          {mostrate.length === dims.length
            ? `${dims.length} misure`
            : `${mostrate.length} di ${dims.length} misure: quelle che richiedono attenzione`}
        </span>
        <div className="spacer" />
        {attenzione.length > 0 && (
          <button onClick={() => setTutte(!tutte)}>
            {tutte ? 'Mostra solo quelle da guardare' : `Mostra tutte e ${dims.length}`}
          </button>
        )}
      </div>

      <table className="dims">
        <thead>
          <tr>
            <th>Quota</th>
            <th className="num">Misurato</th>
            <th className="num">Usato</th>
            <th className="num">Δ</th>
            <th>Stato</th>
            <th>Provenienza</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {mostrate.map((d) => {
            const [tone, text] = BADGE[d.status] ?? ['warn', d.status]
            return (
              <tr key={d.id} className={d.blocks_build ? 'blocking' : d.diverges ? 'diverging' : ''}>
                <td>
                  {d.label}
                  <div className="provenance">{d.id}</div>
                </td>
                <td className="num">{fmt(d.measured, d.unit)}</td>
                <td className="num">{fmt(d.used, d.unit)}</td>
                <td className="num">
                  {d.divergence === null || d.divergence === undefined
                    ? '—'
                    : `${d.divergence > 0 ? '+' : ''}${d.divergence.toFixed(3)}`}
                </td>
                <td><span className={`badge ${tone}`}>{text}</span></td>
                <td className="provenance">{d.explanation}</td>
                <td>
                  <div className="row">
                    <button onClick={() => accept(d)} disabled={d.measured === null}>
                      Usa misura
                    </button>
                    <button onClick={() => beginApprove(d)}>Approva…</button>
                  </div>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>

      {editing && (
        <form className="decision" onSubmit={approve} style={{ marginTop: 14 }}>
          <h3>Approva «{editing.label}»</h3>
          <p className="hint">
            Stai facendo entrare nel modello un valore diverso da quello letto nel
            file. La motivazione viene registrata insieme al numero, e resta sul
            disegno.
          </p>
          <div className="row">
            <label>
              Valore ({editing.unit}){' '}
              <input type="number" step="any" required value={value}
                     onChange={(e) => setValue(e.target.value)} />
            </label>
            <label style={{ flex: 1 }}>
              Motivazione{' '}
              <input required style={{ width: '100%' }} value={rationale}
                     placeholder="es. D4: spessore nominale di stampa"
                     onChange={(e) => setRationale(e.target.value)} />
            </label>
          </div>
          <div className="row" style={{ marginTop: 10 }}>
            <button className="primary" type="submit">Registra approvazione</button>
            <button type="button" onClick={() => setEditing(null)}>Annulla</button>
          </div>
        </form>
      )}
      {error && <p className="error">{error}</p>}
    </div>
  )
}
