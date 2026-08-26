import { useRef, useState } from 'react'
import { api, streamJob } from '../api.js'

// Un pulsante solo, e i quattro passaggi che fa.
//
// Prima erano quattro pannelli numerati con quattro pulsanti «Esegui», in un
// ordine che bisognava conoscere: misura, costruisci, confronta, disegna. È
// l'ordine giusto e non cambia mai — quindi non è una scelta da chiedere, è una
// sequenza da eseguire. I singoli passaggi restano raggiungibili in modalità
// tecnica, per rifarne uno solo dopo aver cambiato una quota.
//
// Se un passaggio fallisce la catena si ferma lì e lo dice: proseguire
// costruirebbe una tavola su un modello che non c'è.

export const PASSAGGI = [
  { kind: 'analyze', label: 'Misuro il file' },
  { kind: 'build', label: 'Ricostruisco il solido' },
  { kind: 'compare', label: 'Confronto con l’originale' },
  { kind: 'draw', label: 'Disegno la tavola' },
]

export default function Pipeline({ runId, onFinito, disabled, disabledReason }) {
  const [stato, setStato] = useState({})     // kind -> 'incorso' | 'fatto' | 'fallito'
  const [attivo, setAttivo] = useState(null)
  const [errore, setErrore] = useState(null)
  const [righe, setRighe] = useState([])
  const stop = useRef(null)

  const inCorso = attivo !== null

  function eseguiUno(kind) {
    return new Promise((resolve, reject) => {
      api.startJob(runId, kind).then((job) => {
        stop.current = streamJob(
          job.id,
          (riga) => setRighe((prev) => [...prev.slice(-40), riga]),
          (finito) => {
            if (finito.state === 'succeeded') resolve(finito)
            else reject(new Error(finito.error || `«${kind}» non è riuscito`))
          },
        )
      }, reject)
    })
  }

  async function avvia() {
    setErrore(null)
    setStato({})
    setRighe([])
    for (const passaggio of PASSAGGI) {
      setAttivo(passaggio.kind)
      setStato((prev) => ({ ...prev, [passaggio.kind]: 'in corso' }))
      try {
        await eseguiUno(passaggio.kind)
        setStato((prev) => ({ ...prev, [passaggio.kind]: 'fatto' }))
      } catch (e) {
        setStato((prev) => ({ ...prev, [passaggio.kind]: 'fallito' }))
        setErrore(e.message)
        setAttivo(null)
        onFinito?.()
        return
      }
    }
    setAttivo(null)
    onFinito?.()
  }

  return (
    <div className="panel">
      <h2>Ricostruisci il modello</h2>
      <p className="hint">
        Misuro il file, ricostruisco un solido con le misure trovate, lo confronto
        con l’originale e disegno la tavola quotata. Nessun numero entra nel
        modello se non è misurato dal file o approvato da te.
      </p>

      <div className="row">
        <button className="primary" onClick={avvia} disabled={inCorso || disabled}>
          {inCorso ? 'In corso…' : 'Avvia'}
        </button>
        {disabled && disabledReason && <span className="note">{disabledReason}</span>}
      </div>

      <ol className="passaggi">
        {PASSAGGI.map((p) => (
          <li key={p.kind} className={stato[p.kind] ?? ''}>
            <span className="segno" />
            {p.label}
          </li>
        ))}
      </ol>

      {inCorso && righe.length > 0 && (
        <p className="ultima-riga">{righe[righe.length - 1]}</p>
      )}
      {errore && <p className="error">{errore}</p>}
    </div>
  )
}
