import type { ReactNode } from 'react'
import { cx } from '../../lib/cx'

interface PanelCardProps {
  /** Rendered in the 34px card header. When omitted, the header is hidden. */
  title?: ReactNode
  /** Rendered right-aligned in the card header (badges, close buttons...). */
  right?: ReactNode
  children: ReactNode
  className?: string
  bodyClassName?: string
  id?: string
}

/**
 * The prototype `.panel` / `.card` surface: gradient fill, hairline border,
 * soft glow, optional 34px header, scrollable body.
 */
export function PanelCard({
  title,
  right,
  children,
  className,
  bodyClassName,
  id,
}: PanelCardProps) {
  return (
    <section
      id={id}
      className={cx(
        'flex min-h-0 flex-col overflow-hidden rounded-lg border border-line shadow-glow',
        'bg-gradient-to-b from-panel/94 to-panel2/94',
        className,
      )}
    >
      {(title !== undefined || right !== undefined) && (
        <header className="flex h-[34px] shrink-0 items-center justify-between border-b border-line px-3 text-[10px] tracking-[.08em] text-label">
          <span className="truncate">{title}</span>
          {right !== undefined && <span className="shrink-0">{right}</span>}
        </header>
      )}
      <div className={cx('min-h-0 flex-1 overflow-auto p-2.5', bodyClassName)}>{children}</div>
    </section>
  )
}