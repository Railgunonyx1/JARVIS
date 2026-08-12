import { useEffect } from "react"
import { initJarvis, useJarvis } from "@/store/jarvis"

export function App() {
  useEffect(() => initJarvis(), [])
  const conn = useJarvis((s) => s.connection)
  const tel = useJarvis((s) => s.telemetry)
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 font-mono text-sm">
      <div className="text-accent">JARVIS // boot check</div>
      <div className="text-muted-foreground">connection: {conn.state}</div>
      <div className="text-muted-foreground">cpu: {tel ? tel.cpu.toFixed(0) : "--"}%</div>
    </div>
  )
}
