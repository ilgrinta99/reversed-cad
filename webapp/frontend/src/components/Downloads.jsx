import { api } from '../api.js'

const kb = (n) => (n < 1024 ? `${n} B` : `${(n / 1024).toFixed(1)} kB`)

// I file che si portano via, e che cosa sono.
//
// L'elenco completo di un run sono venti file: STEP, STL, i corpi singoli, i JSON
// intermedi, la mesh caricata. Metterli tutti allo stesso livello vuol dire che
// chi cerca «il disegno» deve leggerli tutti. I tre che servono quasi sempre
// stanno davanti, con il loro nome in italiano; gli altri restano, dietro.
const IMPORTANTI = [
  ['drawing.pdf', 'Il disegno tecnico', 'Tavola quotata, fogli A3. Da stampare o da mandare all’officina.'],
  ['model.step', 'Il modello 3D', 'Formato STEP: si apre in qualunque CAD e resta modificabile.'],
  ['drawing.dxf', 'Il disegno in DXF', 'Stessa tavola, per chi la deve rielaborare in CAD 2D.'],
  ['model.stl', 'Il modello per la stampa 3D', 'Formato STL, già tassellato.'],
]

export default function Downloads({ runId, artifacts, tutti }) {
  if (!artifacts?.length) return null
  const presente = (path) => artifacts.find((a) => a.path === path)
  const principali = IMPORTANTI.map(([path, titolo, nota]) => [presente(path), titolo, nota])
    .filter(([a]) => a)

  if (!principali.length && !tutti) return null

  return (
    <div className="panel">
      <h2>File da scaricare</h2>
      <ul className="files grandi">
        {principali.map(([a, titolo, nota]) => (
          <li key={a.path}>
            <a href={api.artifactUrl(runId, a.path)} download>
              <strong>{titolo}</strong>
              <span className="size">{a.path} · {kb(a.size)}</span>
            </a>
            <p className="hint">{nota}</p>
          </li>
        ))}
      </ul>

      {tutti && (
        <>
          <h3 className="colonna">Tutto quello che il run ha prodotto</h3>
          <p className="hint">
            Inclusi i file di ingresso e gli intermedi: il run è il documento
            completo di quello che è stato fatto.
          </p>
          <ul className="files">
            {artifacts.map((a) => (
              <li key={a.path}>
                <a href={api.artifactUrl(runId, a.path)} download>
                  {a.path} <span className="size">{kb(a.size)}</span>
                </a>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  )
}
