import { useEffect, useRef } from "react"

/**
 * Canvas sparkline — draws on a ref without React re-renders so a stream of
 * telemetry ticks stays well under one frame (keeps perceived latency low even
 * with several charts live at once).
 */
export function Sparkline({
  data,
  color,
  fill = true,
  max,
  min = 0,
  height = 40,
  className,
}: {
  data: number[]
  color: string
  fill?: boolean
  max?: number
  min?: number
  height?: number
  className?: string
}) {
  const ref = useRef<HTMLCanvasElement | null>(null)

  useEffect(() => {
    const canvas = ref.current
    if (!canvas) return
    const parent = canvas.parentElement
    if (!parent) return
    const dpr = window.devicePixelRatio || 1
    const w = parent.clientWidth
    const h = height
    canvas.width = Math.max(1, Math.floor(w * dpr))
    canvas.height = Math.max(1, Math.floor(h * dpr))
    canvas.style.width = `${w}px`
    canvas.style.height = `${h}px`
    const ctx = canvas.getContext("2d")
    if (!ctx) return
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.clearRect(0, 0, w, h)

    if (data.length < 2) return
    const hi = max ?? Math.max(...data, 1)
    const lo = min
    const range = hi - lo || 1
    const stepX = w / (data.length - 1)
    const pad = 2
    const usableH = h - pad * 2

    const yOf = (v: number) => pad + usableH - ((v - lo) / range) * usableH

    ctx.beginPath()
    data.forEach((v, i) => {
      const x = i * stepX
      const y = yOf(v)
      if (i === 0) ctx.moveTo(x, y)
      else ctx.lineTo(x, y)
    })
    ctx.strokeStyle = color
    ctx.lineWidth = 1.25
    ctx.lineJoin = "round"
    ctx.stroke()

    if (fill) {
      ctx.lineTo((data.length - 1) * stepX, h)
      ctx.lineTo(0, h)
      ctx.closePath()
      ctx.save()
      ctx.globalAlpha = 0.16
      ctx.fillStyle = color
      ctx.fill()
      ctx.restore()
    }

    // leading dot
    const lastX = (data.length - 1) * stepX
    const lastY = yOf(data[data.length - 1])
    ctx.beginPath()
    ctx.arc(lastX - 1, lastY, 1.75, 0, Math.PI * 2)
    ctx.fillStyle = color
    ctx.fill()
  }, [data, color, fill, max, min, height])

  return (
    <div className={className} style={{ height }}>
      <canvas ref={ref} />
    </div>
  )
}
