import { useUiStore } from '../../store/ui'
import { cx } from '../../lib/cx'

interface FooterBarProps {
  className?: string
}

export function FooterBar({ className }: FooterBarProps = {}) {
  const { toast } = useUiStore()

  return (
    <footer
      className={cx(
        'flex h-[70px] items-center justify-between px-4 border-t border-line bg-panel/95 backdrop-filter blur-sm',
        className,
      )}
    >
      {/* Left: Version + Settings */}
      <div className="flex items-center gap-4">
        <span className="text-[10px] text-muted">JARVIS MK-X v0.1.0</span>
        <button
          aria-label="Open settings"
          className="p-2 rounded-lg hover:bg-panel3 transition-colors text-[10px]"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10" />
            <path d="M12 6v6l4 2" />
          </svg>
        </button>
      </div>

      {/* Center: Feature cards (placeholders) */}
      <div className="flex items-center gap-2">
        <button
          aria-label="Voice mode"
          className="flex-1 flex items-center justify-center px-3 py-1 rounded-md text-[10px] text-soft hover:bg-panel3 transition-colors"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10" />
            <path d="M12 6v6l4 2" />
          </svg>
          <span>VOICE</span>
        </button>
        <button
          aria-label="Vision mode"
          className="flex-1 flex items-center justify-center px-3 py-1 rounded-md text-[10px] text-soft hover:bg-panel3 transition-colors"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
            <circle cx="8" cy="8" r="2" />
            <circle cx="16" cy="16" r="2" />
          </svg>
          <span>VISION</span>
        </button>
        <button
          aria-label="Screen share"
          className="flex-1 flex items-center justify-center px-3 py-1 rounded-md text-[10px] text-soft hover:bg-panel3 transition-colors"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
            <circle cx="8" cy="8" r="2" />
          </svg>
          <span>SCREEN</span>
        </button>
      </div>

      {/* Right: Audit + Settings */}
      <div className="flex items-center gap-2">
        <button
          aria-label="Audit log"
          className="flex-1 flex items-center justify-center px-3 py-1 rounded-md text-[10px] text-soft hover:bg-panel3 transition-colors"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M14.7 6.3a1 1 0 0 1 1.4 0l1.6 1.6a1 1 0 0 1 0 1.4l-1.6 1.6a1 1 0 0 1-1.4 0l-1.6-1.6a1 1 0 0 1 0-1.4z" />
            <line x1="9" y1="9" x2="12" y2="12" />
            <path d="M1.6 17.3a1 1 0 0 1 0 1.4l1.6 1.6" />
          </svg>
          <span>AUDIT</span>
        </button>
        <button
          aria-label="Settings"
          className="flex-1 flex items-center justify-center px-3 py-1 rounded-md text-[10px] text-soft hover:bg-panel3 transition-colors"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="3" />
            <path d="M3 9l9-7 9 7M9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v3" />
          </svg>
          <span>SETTINGS</span>
        </button>
      </div>
    </footer>
  )
}