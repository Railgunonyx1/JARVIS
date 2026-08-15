import type { ReactNode } from 'react'
import { cx } from '../../lib/cx'

interface CollapsibleProps {
  open: boolean
  onToggle: () => void
  header: ReactNode
  children: ReactNode
  className?: string
  bodyClassName?: string
}

/** Expandable container used by tool cards and inspection panels. */
export function Collapsible({
  open,
  onToggle,
  header,
  children,
  className,
  bodyClassName,
}: CollapsibleProps) {
  return (
    <div className={cx('overflow-hidden rounded-md border border-line', className)}>
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full cursor-pointer items-center justify-between bg-panel3 px-3 py-2 text-left text-[11px] text-soft transition-colors hover:bg-panel2"
      >
        <span className="min-w-0 flex-1">{header}</span>
        <span
          className={cx(
            'ml-2 shrink-0 text-[10px] text-muted transition-transform',
            open ? 'rotate-90' : '',
          )}
        >
          ▸
        </span>
      </button>
      {open && <div className={cx('border-t border-line p-2.5', bodyClassName)}>{children}</div>}
    </div>
  )
}