// Che cosa è successo, in italiano comune.
//
// Il resto della pagina dice il vero con precisione: «feature non ricostruibili»,
// «scostamento p90», `c1_cupola1_semiasse_x`. Sono i nomi giusti per chi il pezzo
// lo deve fabbricare, e restano dove sono. Ma chi apre l'app per la prima volta ha
// bisogno di sapere un'altra cosa — è andata bene? cosa manca? — e quella risposta
// non stava da nessuna parte.
//
// Le frasi arrivano dal backend (`parts/auto/summary.py`): le parole con cui si
// descrive il lavoro sono parte del lavoro, non della presentazione, e scriverle
// qui vorrebbe dire tenerle lontane dai numeri che descrivono.

const TONO = {
  fedele: ['ok', 'ricalca l’originale'],
  parziale: ['warn', 'ricostruito in parte'],
  grossolano: ['bad', 'approssimazione grossolana'],
  costruito: ['warn', 'da confrontare'],
  analizzato: ['warn', 'da costruire'],
  da_analizzare: ['warn', 'da analizzare'],
}

export default function Riepilogo({ summary, onApri }) {
  if (!summary || summary.stato === 'da_analizzare') return null
  const [tono, etichetta] = TONO[summary.stato] ?? ['warn', summary.stato]

  return (
    <div className="panel riepilogo">
      <div className="row">
        <h2 style={{ margin: 0 }}>Com’è andata</h2>
        <div className="spacer" />
        <span className={`badge ${tono}`}>{etichetta}</span>
      </div>

      {summary.frasi.map((frase) => (
        <p key={frase} className="frase">{frase}</p>
      ))}

      <div className="due-colonne">
        <Colonna titolo="Nel modello" voci={summary.trovato} tono="ok" />
        <Colonna
          titolo="Fuori dal modello"
          voci={summary.mancante}
          tono="warn"
          nota="Sul disegno queste hanno il contorno viola: ci sono nel file di
                partenza, non nel solido."
        />
      </div>

      {onApri && (
        <div className="row" style={{ marginTop: 12 }}>
          <button onClick={onApri}>Vedi i numeri esatti</button>
        </div>
      )}
    </div>
  )
}

function Colonna({ titolo, voci, tono, nota }) {
  if (!voci?.length) return null
  return (
    <div>
      <h3 className="colonna">{titolo}</h3>
      <ul className="conteggio">
        {voci.map((v) => (
          <li key={v.kind}>
            <span className={`pallino ${tono}`} /> {v.quanti} {v.nome}
          </li>
        ))}
      </ul>
      {nota && <p className="hint">{nota}</p>}
    </div>
  )
}
