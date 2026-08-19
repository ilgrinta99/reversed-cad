// Unico punto che parla con il backend.

async function req(path, options = {}) {
  const res = await fetch(`/api${path}`, options)
  if (!res.ok) {
    let detail = res.statusText
    try {
      detail = (await res.json()).detail ?? detail
    } catch {
      /* corpo non JSON: resta statusText */
    }
    throw new Error(detail)
  }
  return res.status === 204 ? null : res.json()
}

const json = (body) => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

export const api = {
  health: () => req('/health'),
  parts: () => req('/parts'),

  createRun: (partId, mesh, references, title) => {
    const form = new FormData()
    form.append('part_id', partId)
    form.append('title', title ?? '')
    form.append('mesh', mesh)
    for (const ref of references) form.append('references', ref)
    return req('/runs', { method: 'POST', body: form })
  },

  listRuns: () => req('/runs'),
  getRun: (id) => req(`/runs/${id}`),
  forkRun: (id) => req(`/runs/${id}/fork`, { method: 'POST' }),
  readiness: (id) => req(`/runs/${id}/readiness`),
  dimensions: (id) => req(`/runs/${id}/dimensions`),
  decisions: (id) => req(`/runs/${id}/decisions`),

  acceptMeasured: (runId, dimId) =>
    req(`/runs/${runId}/dimensions/${dimId}/accept-measured`, { method: 'POST' }),
  approve: (runId, dimId, value, rationale) =>
    req(`/runs/${runId}/dimensions/${dimId}/approve`, json({ value, rationale })),
  resolveDecision: (runId, decisionId, optionId, rationale) =>
    req(`/runs/${runId}/decisions/${decisionId}`, json({ option_id: optionId, rationale })),

  startJob: (runId, kind) => req(`/runs/${runId}/jobs/${kind}`, { method: 'POST' }),
  getJob: (jobId) => req(`/jobs/${jobId}`),
  runJobs: (runId) => req(`/runs/${runId}/jobs`),
  artifacts: (runId) => req(`/runs/${runId}/artifacts`),

  artifactUrl: (runId, path) => `/api/runs/${runId}/artifacts/${path}`,
  artifactText: (runId, path) =>
    fetch(`/api/runs/${runId}/artifacts/${path}`).then((r) => {
      if (!r.ok) throw new Error(`artefatto non disponibile: ${path}`)
      return r.text()
    }),
  artifactJson: (runId, path) =>
    fetch(`/api/runs/${runId}/artifacts/${path}`).then((r) => {
      if (!r.ok) throw new Error(`artefatto non disponibile: ${path}`)
      return r.json()
    }),
}

// Log di un job in streaming. `onLine` per ogni riga, `onDone` a job concluso.
export function streamJob(jobId, onLine, onDone) {
  const source = new EventSource(`/api/jobs/${jobId}/stream`)
  source.addEventListener('log', (e) => onLine(JSON.parse(e.data).line))
  source.addEventListener('state', (e) => {
    source.close()
    onDone(JSON.parse(e.data))
  })
  source.onerror = () => source.close()
  return () => source.close()
}
