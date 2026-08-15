import { useUiStore } from '../../store/ui'
import { cx } from '../../lib/cx'

interface ComposerProps {
  onSubmit: (text: string) => void
  onCancel?: () => void
}

export function Composer({ onSubmit, onCancel }: ComposerProps) {
  const [value, setValue] = React.useState('')
  const { toast } = useUiStore()

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      if (value.trim()) {
        onSubmit(value)
        setValue('')
      }
    }
    if (e.key === 'Escape' && onCancel) {
      e.preventDefault()
      onCancel()
    }
    if (e.key === 'Tab') {
      e.preventDefault()
      // TODO: cycle through / commands
    }
  }

  const handleTyping = () => {
    // TODO: update / command hints
  }

  return (
    <PanelCard title="COMPOSER" className="h-20">
      <div className="flex h-full">
        <textarea
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="/ ask JARVIS ..."
          className={cx(
            'flex-1 bg-panel4 border border-line rounded-t-md text-[10px] text-body placeholder:[#536d7d] focus:outline-none focus:ring-2 focus:ring-cyan/30 resize-none min-h-[32px]',
          )}
          rows={1}
        />
        <button
          type="button"
          onClick={() => onSubmit(value)}
          className="flex shrink-0 items-center justify-center w-14 bg-cyan text-white text-[10px] rounded-b-md hover:bg-cyan/90"
          disabled={!value.trim()}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="12" y1="5" x2="12" y2="19" />
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
        </button>
      </div>
    </PanelCard>
  )
}