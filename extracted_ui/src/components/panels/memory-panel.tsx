import { useEffect, useMemo, useRef, useState } from "react"
import { Brain, Network, List } from "lucide-react"
import { useJarvis } from "@/store/jarvis"
import { PanelShell, Label, Chip, EmptyState, IconButton } from "@/components/ui/primitives"
import { palette } from "@/lib/colors"
import { fmtAgo } from "@/lib/format"
import { cn } from "@/lib/utils"
import type { MemoryEntry, MemoryKind } from "@/lib/ipc/protocol"

const KIND_TONE: Record<MemoryKind, "accent" | "info" | "online" | "warn"> = {
  fact: "info",
  preference: "accent",
  entity: "online",
  episode: "warn",
}

export function MemoryPanel() {
  const memoryMap = useJarvis((s) => s.memory)
  const [view, setView] = useState<"graph" | "list">("graph")
  const entries = useMemo(() => Object.values(memoryMap).sort((a, b) => b.score - a.score), [memoryMap])

  return (
    <PanelShell
      toolbar={
        <>
          <Brain className="h-3.5 w-3.5 text-accent" />
          <Label>memory</Label>
          <span className="text-2xs text-muted-foreground">{entries.length} entries</span>
          <div className="ml-auto flex items-center gap-0.5">
            <IconButton title="Graph view" active={view === "graph"} onClick={() => setView("graph")}>
              <Network className="h-3.5 w-3.5" />
            </IconButton>
            <IconButton title="List view" active={view === "list"} onClick={() => setView("list")}>
              <List className="h-3.5 w-3.5" />
            </IconButton>
          </div>
        </>
      }
    >
      {entries.length === 0 ? (
        <EmptyState>No memories stored yet. Facts, preferences, and entities the agent learns appear here.</EmptyState>
      ) : view === "graph" ? (
        <MemoryGraph entries={entries} />
      ) : (
        <div className="scroll-thin h-full overflow-y-auto p-2">
          <div className="flex flex-col gap-1.5">
            {entries.map((e) => (
              <div key={e.id} className="rounded-md border border-border bg-elevated/40 px-2.5 py-2">
                <div className="flex items-center gap-2">
                  <Chip tone={KIND_TONE[e.kind]}>{e.kind}</Chip>
                  <span className="truncate font-mono text-2xs text-muted-foreground">{e.key}</span>
                  <span className="ml-auto shrink-0 font-mono text-2xs text-muted-foreground/50">{fmtAgo(e.ts)}</span>
                </div>
                <p className="mt-1 text-pretty text-xs leading-relaxed text-foreground">{e.value}</p>
                <div className="mt-1.5 flex items-center gap-2">
                  <div className="h-1 flex-1 overflow-hidden rounded-full bg-background">
                    <div className="h-full rounded-full bg-accent" style={{ width: `${Math.round(e.score * 100)}%` }} />
                  </div>
                  <span className="font-mono text-2xs tabular text-muted-foreground">{(e.score * 100).toFixed(0)}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </PanelShell>
  )
}

type Node = { id: string; x: number; y: number; vx: number; vy: number; entry: MemoryEntry }

function MemoryGraph({ entries }: { entries: MemoryEntry[] }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const wrapRef = useRef<HTMLDivElement | null>(null)
  const [hover, setHover] = useState<MemoryEntry | null>(null)
  const stateRef = useRef<{ nodes: Node[]; raf: number }>({ nodes: [], raf: 0 })

  const kindColor = (k: MemoryKind) =>
    k === "fact" ? palette.info : k === "preference" ? palette.accent : k === "entity" ? palette.online : palette.warn

  useEffect(() => {
    const wrap = wrapRef.current
    const canvas = canvasRef.current
    if (!wrap || !canvas) return
    const ctx = canvas.getContext("2d")
    if (!ctx) return

    let w = wrap.clientWidth
    let h = wrap.clientHeight
    const dpr = window.devicePixelRatio || 1

    const resize = () => {
      w = wrap.clientWidth
      h = wrap.clientHeight
      canvas.width = Math.floor(w * dpr)
      canvas.height = Math.floor(h * dpr)
      canvas.style.width = `${w}px`
      canvas.style.height = `${h}px`
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    }
    resize()
    const ro = new ResizeObserver(resize)
    ro.observe(wrap)

    // seed / merge nodes so positions persist across memory updates
    const prev = new Map(stateRef.current.nodes.map((n) => [n.id, n]))
    const nodes: Node[] = entries.map((entry, i) => {
      const ex = prev.get(entry.id)
      if (ex) return { ...ex, entry }
      const angle = (i / Math.max(1, entries.length)) * Math.PI * 2
      return {
        id: entry.id,
        x: w / 2 + Math.cos(angle) * 60 + (Math.random() - 0.5) * 20,
        y: h / 2 + Math.sin(angle) * 60 + (Math.random() - 0.5) * 20,
        vx: 0,
        vy: 0,
        entry,
      }
    })
    stateRef.current.nodes = nodes

    const index = new Map(nodes.map((n) => [n.id, n]))
    const edges: [Node, Node][] = []
    for (const n of nodes) {
      for (const ref of n.entry.refs ?? []) {
        const t = index.get(ref)
        if (t) edges.push([n, t])
      }
    }

    const step = () => {
      // simple force-directed layout
      for (let i = 0; i < nodes.length; i++) {
        const a = nodes[i]
        for (let j = i + 1; j < nodes.length; j++) {
          const b = nodes[j]
          let dx = a.x - b.x
          let dy = a.y - b.y
          let d2 = dx * dx + dy * dy || 0.01
          const d = Math.sqrt(d2)
          const rep = 900 / d2
          const fx = (dx / d) * rep
          const fy = (dy / d) * rep
          a.vx += fx
          a.vy += fy
          b.vx -= fx
          b.vy -= fy
        }
      }
      for (const [a, b] of edges) {
        const dx = b.x - a.x
        const dy = b.y - a.y
        const d = Math.sqrt(dx * dx + dy * dy) || 0.01
        const spring = (d - 70) * 0.01
        const fx = (dx / d) * spring
        const fy = (dy / d) * spring
        a.vx += fx
        a.vy += fy
        b.vx -= fx
        b.vy -= fy
      }
      const cx = w / 2
      const cy = h / 2
      for (const n of nodes) {
        n.vx += (cx - n.x) * 0.002
        n.vy += (cy - n.y) * 0.002
        n.vx *= 0.85
        n.vy *= 0.85
        n.x += n.vx
        n.y += n.vy
        n.x = Math.max(14, Math.min(w - 14, n.x))
        n.y = Math.max(14, Math.min(h - 14, n.y))
      }

      ctx.clearRect(0, 0, w, h)
      ctx.strokeStyle = palette.border
      ctx.lineWidth = 1
      for (const [a, b] of edges) {
        ctx.beginPath()
        ctx.moveTo(a.x, a.y)
        ctx.lineTo(b.x, b.y)
        ctx.stroke()
      }
      for (const n of nodes) {
        const r = 4 + n.entry.score * 7
        ctx.beginPath()
        ctx.arc(n.x, n.y, r, 0, Math.PI * 2)
        ctx.fillStyle = kindColor(n.entry.kind)
        ctx.globalAlpha = 0.9
        ctx.fill()
        ctx.globalAlpha = 1
      }
      stateRef.current.raf = requestAnimationFrame(step)
    }
    stateRef.current.raf = requestAnimationFrame(step)

    const onMove = (ev: MouseEvent) => {
      const rect = canvas.getBoundingClientRect()
      const mx = ev.clientX - rect.left
      const my = ev.clientY - rect.top
      let found: MemoryEntry | null = null
      for (const n of nodes) {
        const r = 4 + n.entry.score * 7
        if ((mx - n.x) ** 2 + (my - n.y) ** 2 <= (r + 3) ** 2) {
          found = n.entry
          break
        }
      }
      setHover(found)
    }
    canvas.addEventListener("mousemove", onMove)

    return () => {
      cancelAnimationFrame(stateRef.current.raf)
      ro.disconnect()
      canvas.removeEventListener("mousemove", onMove)
    }
  }, [entries])

  return (
    <div ref={wrapRef} className="relative h-full w-full">
      <canvas ref={canvasRef} className="block" />
      <div className="pointer-events-none absolute left-2 top-2 flex flex-wrap gap-1">
        {(["fact", "preference", "entity", "episode"] as MemoryKind[]).map((k) => (
          <span key={k} className="flex items-center gap-1 text-2xs text-muted-foreground">
            <span className="h-2 w-2 rounded-full" style={{ backgroundColor: kindColor(k) }} />
            {k}
          </span>
        ))}
      </div>
      {hover ? (
        <div className="pointer-events-none absolute bottom-2 left-2 right-2 rounded-md border border-border bg-background/95 px-2.5 py-1.5">
          <div className="flex items-center gap-2">
            <Chip tone={KIND_TONE[hover.kind]}>{hover.kind}</Chip>
            <span className="font-mono text-2xs text-muted-foreground">{hover.key}</span>
          </div>
          <p className={cn("mt-0.5 text-pretty text-2xs leading-relaxed text-foreground")}>{hover.value}</p>
        </div>
      ) : null}
    </div>
  )
}
