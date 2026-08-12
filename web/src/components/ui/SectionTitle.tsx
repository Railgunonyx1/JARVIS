import type { ReactNode } from 'react'

interface SectionTitleProps {
  children: ReactNode
  right?: ReactNode
  className?: string
}

/** The prototype `.section-title`: 10px tracked uppercase label with optional right slot. */
export function SectionTitle({ children, right, className }: SectionTitleProps) {
  return (
    <div
      className={`flex items-center justify-between text-[10px] tracking-[.08em] text-label ${className ?? ''}`}
    >
      <span className="truncate">{children}</span>
      {right !== undefined && <span className="shrink-0">{right}</span>}
    </div>
  )
}
