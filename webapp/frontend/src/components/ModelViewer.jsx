import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { STLLoader } from 'three/examples/jsm/loaders/STLLoader.js'
import { api } from '../api.js'

// Anteprima del solido costruito, con sopra la mesh di partenza colorata per
// scostamento. I due oggetti restano distinti: il modello è ciò che abbiamo
// costruito, la nuvola è ciò che la mesh dice davvero.
export default function ModelViewer({ runId, modelPath, hasModel, hasDeviation }) {
  const mount = useRef(null)
  const [error, setError] = useState(null)
  const [stats, setStats] = useState(null)
  const [showDeviation, setShowDeviation] = useState(true)
  const deviationRef = useRef(null)

  useEffect(() => {
    if (!mount.current || !hasModel) return
    const el = mount.current
    const scene = new THREE.Scene()
    scene.background = new THREE.Color(0x0b0d13)

    const camera = new THREE.PerspectiveCamera(45, el.clientWidth / el.clientHeight, 0.1, 5000)
    const renderer = new THREE.WebGLRenderer({ antialias: true })
    renderer.setPixelRatio(window.devicePixelRatio)
    renderer.setSize(el.clientWidth, el.clientHeight)
    el.appendChild(renderer.domElement)

    scene.add(new THREE.AmbientLight(0xffffff, 0.6))
    const key = new THREE.DirectionalLight(0xffffff, 0.9)
    key.position.set(1, 1, 1)
    scene.add(key)

    const controls = new OrbitControls(camera, renderer.domElement)
    controls.enableDamping = true

    let raf = 0
    const cleanupFns = []

    new STLLoader().load(
      api.artifactUrl(runId, modelPath),
      (geometry) => {
        geometry.computeVertexNormals()
        geometry.computeBoundingSphere()
        const { center, radius } = geometry.boundingSphere
        const model = new THREE.Mesh(
          geometry,
          new THREE.MeshStandardMaterial({
            color: 0x6ea8fe, metalness: 0.1, roughness: 0.75,
            transparent: true, opacity: 0.85,
          }),
        )
        scene.add(model)
        cleanupFns.push(() => { geometry.dispose(); model.material.dispose() })

        camera.position.set(center.x + radius * 2, center.y - radius * 2, center.z + radius * 1.6)
        camera.up.set(0, 0, 1)
        controls.target.copy(center)
        controls.update()

        const animate = () => {
          raf = requestAnimationFrame(animate)
          controls.update()
          renderer.render(scene, camera)
        }
        animate()
      },
      undefined,
      () => setError('anteprima non disponibile: model.stl non è stato prodotto'),
    )

    if (hasDeviation) {
      loadDeviationCloud(runId)
        .then(({ points, stats: s }) => {
          scene.add(points)
          deviationRef.current = points
          setStats(s)
          cleanupFns.push(() => { points.geometry.dispose(); points.material.dispose() })
        })
        .catch((e) => setError(e.message))
    }

    const onResize = () => {
      camera.aspect = el.clientWidth / el.clientHeight
      camera.updateProjectionMatrix()
      renderer.setSize(el.clientWidth, el.clientHeight)
    }
    window.addEventListener('resize', onResize)

    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('resize', onResize)
      controls.dispose()
      cleanupFns.forEach((fn) => fn())
      renderer.dispose()
      el.removeChild(renderer.domElement)
      deviationRef.current = null
    }
  }, [runId, modelPath, hasModel, hasDeviation])

  useEffect(() => {
    if (deviationRef.current) deviationRef.current.visible = showDeviation
  }, [showDeviation])

  if (!hasModel) {
    return (
      <div className="panel">
        <h2>4 · Anteprima 3D</h2>
        <p className="hint">Disponibile dopo la build.</p>
      </div>
    )
  }

  return (
    <div className="panel">
      <h2>4 · Anteprima 3D e scostamento</h2>
      <p className="hint">
        In blu il solido costruito; i punti sono i vertici della mesh campionati dal
        confronto, colorati per distanza dalla superficie del modello — verde vicino,
        rosso lontano.
      </p>
      <div className="row" style={{ marginBottom: 10 }}>
        <label>
          <input type="checkbox" checked={showDeviation} disabled={!hasDeviation}
                 onChange={(e) => setShowDeviation(e.target.checked)} />{' '}
          mostra la mappa di scostamento
        </label>
        {stats && (
          <span className="provenance">
            mediana {stats.mediana_mm.toFixed(3)} mm · p90 {stats.p90_mm.toFixed(3)} mm ·
            p99 {stats.p99_mm.toFixed(3)} mm · max {stats.max_mm.toFixed(3)} mm
          </span>
        )}
      </div>
      <div className="viewer" ref={mount} />
      {error && <p className="error">{error}</p>}
    </div>
  )
}

// Ogni punto del confronto porta con sé le proprie coordinate, nel riferimento
// dell'assieme: nessuna dipendenza dall'ordine dei vertici del file di partenza.
async function loadDeviationCloud(runId) {
  const deviation = await api.artifactJson(runId, 'deviation.json')
  const raw = deviation.points ?? []

  // La scala del colore si ferma alla soglia sulle superfici curve: oltre quella
  // il rosso è pieno, e le differenze che contano restano leggibili sotto.
  const limit = deviation.soglie_mm?.curva ?? Math.max(...raw.map((p) => p[3]), 1e-9)

  const coords = new Float32Array(raw.length * 3)
  const colors = new Float32Array(raw.length * 3)
  const color = new THREE.Color()
  raw.forEach(([x, y, z, d], i) => {
    coords[i * 3] = x
    coords[i * 3 + 1] = y
    coords[i * 3 + 2] = z
    color.setHSL(0.33 * (1 - Math.min(d / limit, 1)), 0.85, 0.55) // verde → rosso
    colors[i * 3] = color.r
    colors[i * 3 + 1] = color.g
    colors[i * 3 + 2] = color.b
  })

  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.BufferAttribute(coords, 3))
  geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3))

  const points = new THREE.Points(
    geometry,
    new THREE.PointsMaterial({ size: 0.5, vertexColors: true }),
  )
  return { points, stats: deviation.stats, parts: deviation.parts }
}
