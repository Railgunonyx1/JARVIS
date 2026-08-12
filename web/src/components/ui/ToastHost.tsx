import { useUiStore } from '../../store/ui'

/** Bottom-right toast stack (prototype `.toast`), driven by the ui store. */
export function ToastHost() {
  const toasts = useUiStore((s) => s.toasts)
  if (toasts.length === 0) return null
  return (
    <div className="pointer-events-none fixed right-5 bottom-24 z-50 flex flex-col gap-2">
      {toasts.map((t) => (
        <div
          key={t.id}
          className="animate-toast-in rounded-md border border-[#17617b] bg-[#071722] px-3.5 py-2.5 font-mono text-[10px] text-[#bfe4ee] shadow-glow"
        >
          {t.message}
        </div>
      ))}
    </div>
  )
}
