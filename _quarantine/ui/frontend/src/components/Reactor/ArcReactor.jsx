import { useRef, useEffect } from 'react'
import * as THREE from 'three'
import { useTelemetryStore } from '../../stores/telemetryStore'
import { useKernelStore } from '../../stores/kernelStore'

const FPS_CONFIG = { eco: 12, balanced: 30, performance: 60 }

export default function ArcReactor() {
  const mountRef = useRef(null)
  const cpu = useTelemetryStore((s) => s.cpu)
  const mode = useKernelStore((s) => s.performanceMode)
  const status = useKernelStore((s) => s.status)
  const sceneRef = useRef(null)
  const torusRef = useRef(null)
  const innerRef = useRef(null)
  const particlesRef = useRef(null)
  const coreRef = useRef(null)
  const animRef = useRef(null)
  const lastTimeRef = useRef(0)
  const cpuRef = useRef(0)
  const modeRef = useRef('balanced')

  cpuRef.current = cpu
  modeRef.current = mode

  useEffect(() => {
    const mount = mountRef.current
    if (!mount) return
    const w = mount.clientWidth
    const h = mount.clientHeight

    const scene = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(45, w / h, 0.1, 1000)
    camera.position.z = 5

    const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true })
    renderer.setSize(w, h)
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    mount.appendChild(renderer.domElement)
    sceneRef.current = { scene, camera, renderer }

    // Main torus
    const geo = new THREE.TorusKnotGeometry(1.2, 0.35, 128, 16)
    const mat = new THREE.MeshBasicMaterial({
      color: 0x00d4ff,
      wireframe: true,
      transparent: true,
      opacity: 0.4,
    })
    const torus = new THREE.Mesh(geo, mat)
    scene.add(torus)
    torusRef.current = torus

    // Inner ring
    const ringGeo = new THREE.TorusGeometry(0.75, 0.04, 64, 64)
    const ringMat = new THREE.MeshBasicMaterial({
      color: 0x00d4ff,
      transparent: true,
      opacity: 0.25,
    })
    const innerRing = new THREE.Mesh(ringGeo, ringMat)
    scene.add(innerRing)
    innerRef.current = innerRing

    // Particles
    const particleCount = 800
    const positions = new Float32Array(particleCount * 3)
    for (let i = 0; i < particleCount * 3; i++) {
      positions[i] = (Math.random() - 0.5) * 8
    }
    const pGeo = new THREE.BufferGeometry()
    pGeo.setAttribute('position', new THREE.BufferAttribute(positions, 3))
    const pMat = new THREE.PointsMaterial({
      color: 0x00d4ff,
      size: 0.02,
      transparent: true,
      opacity: 0.3,
    })
    const particles = new THREE.Points(pGeo, pMat)
    scene.add(particles)
    particlesRef.current = particles

    // Core glow
    const spriteMap = (() => {
      const canvas = document.createElement('canvas')
      canvas.width = 128; canvas.height = 128
      const ctx = canvas.getContext('2d')
      const grad = ctx.createRadialGradient(64, 64, 0, 64, 64, 64)
      grad.addColorStop(0, 'rgba(0,212,255,1)')
      grad.addColorStop(0.2, 'rgba(0,212,255,0.6)')
      grad.addColorStop(1, 'rgba(0,212,255,0)')
      ctx.fillStyle = grad
      ctx.fillRect(0, 0, 128, 128)
      return new THREE.CanvasTexture(canvas)
    })()
    const spriteMat = new THREE.SpriteMaterial({
      map: spriteMap,
      blending: THREE.AdditiveBlending,
      transparent: true,
      opacity: 0.8,
    })
    const sprite = new THREE.Sprite(spriteMat)
    sprite.scale.set(2.5, 2.5, 1)
    scene.add(sprite)
    coreRef.current = sprite

    lastTimeRef.current = performance.now()

    function tick(now) {
      animRef.current = requestAnimationFrame(tick)
      const targetInterval = 1000 / (FPS_CONFIG[modeRef.current] || 30)
      if (now - lastTimeRef.current < targetInterval * 0.9) return
      lastTimeRef.current = now

      const speed = modeRef.current === 'eco' ? 0.3 : modeRef.current === 'performance' ? 1.0 : 0.6
      const cpuVal = cpuRef.current

      if (torusRef.current) {
        torusRef.current.rotation.x += 0.005 * speed
        torusRef.current.rotation.y += 0.01 * speed
        const op = 0.2 + (cpuVal / 100) * 0.5
        torusRef.current.material.opacity = op
      }
      if (innerRef.current) {
        innerRef.current.rotation.z += 0.008 * speed
        innerRef.current.rotation.x += 0.003 * speed
      }
      if (particlesRef.current) {
        const pos = particlesRef.current.geometry.attributes.position.array
        for (let i = 0; i < pos.length; i += 3) {
          pos[i + 1] -= 0.002 * speed
          if (pos[i + 1] < -4) pos[i + 1] = 4
        }
        particlesRef.current.geometry.attributes.position.needsUpdate = true
      }
      if (coreRef.current) {
        coreRef.current.material.opacity = 0.5 + (cpuVal / 100) * 0.5
        const s = 1.5 + Math.sin(now * 0.002) * 0.5
        coreRef.current.scale.set(s, s, 1)
      }

      renderer.render(scene, camera)
    }

    animRef.current = requestAnimationFrame(tick)

    return () => {
      if (animRef.current) cancelAnimationFrame(animRef.current)
      renderer.dispose()
      if (mount.contains(renderer.domElement)) mount.removeChild(renderer.domElement)
    }
  }, [])

  return (
    <div className="reactor-container">
      <div ref={mountRef} style={{ width: 260, height: 220 }} />
      <div className="reactor-info">
        <span>REACTOR <span className="reactor-value">{status === 'running' ? 'ONLINE' : 'OFFLINE'}</span></span>
        <span>OUTPUT <span className="reactor-value">{100 - Math.round(cpu / 2)}%</span></span>
      </div>
    </div>
  )
}
