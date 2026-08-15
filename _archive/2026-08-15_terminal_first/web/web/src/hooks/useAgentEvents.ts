import { useEffect } from 'react'
import { useUiStore } from '../store/ui'

/** Batch agent events and drain on rAF — one setState per frame. */
export function useAgentEvents() {
  const { setTab, activeTab, toast } = useUiStore()

  useEffect(() => {
    let rafId: number
    const queue: Array<() => void> = []

    const loop = () => {
      rafId = requestAnimationFrame(loop)
      if (queue.length === 0) return
      const batch = queue.splice(0, 8) // drain up to 8 per frame
      batch.forEach((fn) => fn())
    }

    const enqueue = (fn: () => void) => {
      queue.push(fn)
      if (!rafId) requestAnimationFrame(loop)
    }

    // Example: batch tab changes
    return () => {
      cancelAnimationFrame(rafId)
      queue.length = 0
    }
  }, [activeTab, setTab, toast])
}