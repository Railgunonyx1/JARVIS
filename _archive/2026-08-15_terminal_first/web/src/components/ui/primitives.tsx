import { cn } from "@/lib/utils"
import type { ReactNode } from "react"

/** Uppercase micro-label used for section headers and metadata. */
export function Label({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span className={cn("text-2xs uppercase tracking-[0.12em] text-muted-foreground", className)}>{children}</span>
  )
}

export function PanelShell({
  toolbar,
  children,
  className,
}: {
  toolbar?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <div className={cn("flex h-full min-h-0 flex-col bg-panel text-panel-foreground", className)}>
      {toolbar ? (
        <div className="flex h-8 shrink-0 items-center gap-2 border-b border-border bg-background/40 px-2.5">
          {toolbar}
        </div>
      ) : null}
      <div className="min-h-0 flex-1">{children}</div>
    </div>
  )
}

const DOT: Record<string, string> = {
  online: "bg-online",
  ok: "bg-online",
  running: "bg-accent",
  degraded: "bg-warn",
  warn: "bg-warn",
  queued: "bg-info",
  offline: "bg-muted-foreground",
  error: "bg-error",
  failed: "bg-error",
  blocked: "bg-warn",
  pending: "bg-muted-foreground",
  done: "bg-online",
  sim: "bg-info",
}

export function StatusDot({ status, pulse }: { status: string; pulse?: boolean }) {
  return (
    <span className="relative inline-flex h-2 w-2 items-center justify-center">
      {pulse ? (
        <span className={cn("absolute inline-flex h-full w-full animate-ping rounded-full opacity-60", DOT[status] ?? "bg-muted-foreground")} />
      ) : null}
      <span className={cn("relative inline-flex h-2 w-2 rounded-full", DOT[status] ?? "bg-muted-foreground")} />
    </span>
  )
}

export function Chip({
  children,
  tone = "neutral",
  className,
}: {
  children: ReactNode
  tone?: "neutral" | "accent" | "online" | "warn" | "error" | "info"
  className?: string
}) {
  const tones: Record<string, string> = {
    neutral: "border-border text-muted-foreground",
    accent: "border-accent-muted text-accent",
    online: "border-online/40 text-online",
    warn: "border-warn/40 text-warn",
    error: "border-error/40 text-error",
    info: "border-info/40 text-info",
  }
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-sm border px-1.5 py-0.5 text-2xs uppercase tracking-wider",
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
  )
}

export function IconButton({
  children,
  onClick,
  title,
  active,
  className,
}: {
  children: ReactNode
  onClick?: () => void
  title?: string
  active?: boolean
  className?: string
}) {
  return (
    <button
      type="button"
      title={title}
      aria-label={title}
      onClick={onClick}
      className={cn(
        "inline-flex h-6 items-center justify-center gap-1.5 rounded-sm border border-transparent px-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground",
        active && "border-accent-muted bg-muted text-accent",
        className,
      )}
    >
      {children}
    </button>
  )
}

export function EmptyState({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-full items-center justify-center p-6 text-center text-xs text-muted-foreground">
      <span className="max-w-[36ch] text-pretty leading-relaxed">{children}</span>
    </div>
  )
}
