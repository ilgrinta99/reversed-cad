import { useState } from 'react'
import { api } from '../api.js'

// Si carica una mesh, e basta. Non c'è un pezzo da scegliere: quale pezzo sia,
// e quali quote abbia, lo dice l'analisi della mesh — non un menu compilato prima
// di guardarla.
//
// I formati accettati arrivano da /api/health: è il server a saperli leggere, e
// un secondo elenco scritto qui divergerebbe alla prima aggiunta.
const FORMATI_DI_RISERVA = ['.obj', '.stl', '.ply', '.wrl']

export default function UploadPanel({ onCreated, formats }) {
  const accettati = (formats?.length ? formats : FORMATI_DI_RISERVA).join(',')
  const [mesh, setMesh] = useState(null)
  const [references, setReferences] = useState([])
  const [title, setTitle] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  async function submit(event) {
    event.preventDefault()
    setError(null)
    setBusy(true)
    try {
      onCreated(await api.createRun(mesh, references, title))
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="panel" onSubmit={submit}>
      <h2>1 · Caricamento</h2>
      <p className="hint">
        La mesh caricata è l'unica fonte di quote, e l'analisi parte da questo
        file: ingombri, pareti, raccordi, fori e ambiguità vengono misurati qui,
        non letti da un modello di riferimento. Il .mtl e gli altri allegati
        restano materiale di consultazione — una tavola TinkerCAD è generata dalla
        mesh stessa, quindi non è una fonte indipendente e non autorizza alcun
        numero. Le misure si assumono in millimetri: nessuno di questi formati
        porta un'unità, e indovinarla non si può.
      </p>

      <div className="row">
        <label>
          Mesh ({accettati.replaceAll(',', ' ')}){' '}
          <input type="file" accept={accettati} required
                 onChange={(e) => setMesh(e.target.files[0])} />
        </label>
        <label>
          Allegati (.mtl, immagini, PDF){' '}
          <input type="file" multiple onChange={(e) => setReferences([...e.target.files])} />
        </label>
        <label>
          Titolo{' '}
          <input value={title} onChange={(e) => setTitle(e.target.value)}
                 placeholder="facoltativo" />
        </label>
      </div>

      <div className="row" style={{ marginTop: 14 }}>
        <button className="primary" type="submit" disabled={busy || !mesh}>
          {busy ? 'Caricamento…' : 'Carica e apri il run'}
        </button>
      </div>
      {error && <p className="error">{error}</p>}
    </form>
  )
}
