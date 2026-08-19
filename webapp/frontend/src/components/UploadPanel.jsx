import { useEffect, useState } from 'react'
import { api } from '../api.js'

export default function UploadPanel({ onCreated }) {
  const [parts, setParts] = useState([])
  const [partId, setPartId] = useState('')
  const [mesh, setMesh] = useState(null)
  const [references, setReferences] = useState([])
  const [title, setTitle] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.parts().then((list) => {
      setParts(list)
      const first = list.find((p) => p.wired)
      if (first) setPartId(first.id)
    }, (e) => setError(e.message))
  }, [])

  const selected = parts.find((p) => p.id === partId)

  async function submit(event) {
    event.preventDefault()
    setError(null)
    setBusy(true)
    try {
      onCreated(await api.createRun(partId, mesh, references, title))
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
        La mesh OBJ è l'unica fonte di quote. Immagini e PDF caricati come
        riferimento restano materiale di consultazione: una tavola TinkerCAD è
        generata dalla mesh stessa, quindi non è una fonte indipendente e non
        autorizza alcun numero.
      </p>

      <div className="row">
        <label>
          Pezzo{' '}
          <select value={partId} onChange={(e) => setPartId(e.target.value)}>
            {parts.map((p) => (
              <option key={p.id} value={p.id} disabled={!p.wired}>
                {p.name}{p.wired ? '' : ' — non collegato'}
              </option>
            ))}
          </select>
        </label>
        <label>
          Titolo{' '}
          <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="facoltativo" />
        </label>
      </div>

      {selected && <p className="hint" style={{ marginTop: 10 }}>{selected.description}</p>}

      <div className="row" style={{ marginTop: 10 }}>
        <label>
          Mesh (.obj){' '}
          <input type="file" accept=".obj" required onChange={(e) => setMesh(e.target.files[0])} />
        </label>
        <label>
          Allegati (.mtl, immagini, PDF){' '}
          <input type="file" multiple onChange={(e) => setReferences([...e.target.files])} />
        </label>
      </div>

      <div className="row" style={{ marginTop: 14 }}>
        <button className="primary" type="submit" disabled={busy || !mesh || !selected?.wired}>
          {busy ? 'Caricamento…' : 'Crea run'}
        </button>
      </div>
      {error && <p className="error">{error}</p>}
    </form>
  )
}
