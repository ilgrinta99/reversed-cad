import { api } from '../api.js'

const kb = (n) => (n < 1024 ? `${n} B` : `${(n / 1024).toFixed(1)} kB`)

export default function Downloads({ runId, artifacts }) {
  if (!artifacts?.length) return null
  return (
    <div className="panel">
      <h2>6 · File del run</h2>
      <p className="hint">
        Tutto ciò che il run ha prodotto, inclusi i file di ingresso: il run è il
        documento completo di quello che è stato fatto.
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
    </div>
  )
}
