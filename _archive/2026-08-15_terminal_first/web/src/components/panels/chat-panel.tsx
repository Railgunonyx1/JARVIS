import { useEffect, useRef, useState } from "react"
import { ArrowUp, Square, Cpu } from "lucide-react"
import { useJarvis } from "@/store/jarvis"
import { PanelShell, Label, Chip } from "@/components/ui/primitives"
import { fmtClock, fmtNum, fmtUsd } from "@/lib/format"
import { cn } from "@/lib/utils"
import type { ChatMessage } from "@/lib/ipc/protocol"

export function ChatPanel() {
  const messages = useJarvis((s) => s.messages)
  const sendChat = useJarvis((s) => s.sendChat)
  const cancelRun = useJarvis((s) => s.cancelRun)
  const activeModel = useJarvis((s) => s.activeModel)
  const [draft, setDraft] = useState("")
  const scrollRef = useRef<HTMLDivElement | null>(null)
  const taRef = useRef<HTMLTextAreaElement | null>(null)

  const streaming = messages.find((m) => m.streaming)

  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    el.scrollTop = el.scrollHeight
  }, [messages])

  function submit() {
    if (!draft.trim()) return
    sendChat(draft)
    setDraft("")
    requestAnimationFrame(() => taRef.current?.focus())
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      if (e.nativeEvent.isComposing || e.keyCode === 229) return
      e.preventDefault()
      submit()
    }
  }

  return (
    <PanelShell
      toolbar={
        <>
          <Label>session</Label>
          <span className="text-2xs text-muted-foreground">conversation</span>
          <div className="ml-auto flex items-center gap-1.5 text-muted-foreground">
            <Cpu className="h-3 w-3" />
            <span className="text-2xs">{activeModel || "no model"}</span>
          </div>
        </>
      }
    >
      <div className="flex h-full min-h-0 flex-col">
        <div ref={scrollRef} className="scroll-thin min-h-0 flex-1 overflow-y-auto px-3 py-3">
          {messages.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center gap-2 text-center">
              <span className="text-sm text-muted-foreground">JARVIS console ready</span>
              <span className="max-w-[42ch] text-pretty text-xs leading-relaxed text-muted-foreground/70">
                Ask a question or issue a command. Agent reasoning and tool calls stream into the timeline panel in
                real time.
              </span>
            </div>
          ) : (
            <div className="flex flex-col gap-4">
              {messages.map((m) => (
                <MessageRow key={m.id} m={m} onCancel={m.runId ? () => cancelRun(m.runId as string) : undefined} />
              ))}
            </div>
          )}
        </div>

        <div className="shrink-0 border-t border-border bg-background/40 p-2.5">
          <div className="flex items-end gap-2 rounded-md border border-border bg-input px-2.5 py-2 focus-within:border-accent-muted">
            <textarea
              ref={taRef}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={onKeyDown}
              rows={1}
              placeholder="message jarvis…"
              className="scroll-thin max-h-40 min-h-[20px] flex-1 resize-none bg-transparent text-sm leading-relaxed text-foreground outline-none placeholder:text-muted-foreground/60"
            />
            {streaming ? (
              <button
                type="button"
                onClick={() => streaming.runId && cancelRun(streaming.runId)}
                className="inline-flex h-7 items-center gap-1.5 rounded-sm border border-error/40 px-2 text-2xs uppercase tracking-wider text-error transition-colors hover:bg-error/10"
              >
                <Square className="h-3 w-3" /> stop
              </button>
            ) : (
              <button
                type="button"
                onClick={submit}
                disabled={!draft.trim()}
                className="inline-flex h-7 w-7 items-center justify-center rounded-sm bg-accent text-accent-foreground transition-opacity disabled:opacity-40"
                aria-label="Send message"
              >
                <ArrowUp className="h-4 w-4" />
              </button>
            )}
          </div>
          <div className="mt-1 flex items-center justify-between px-1">
            <span className="text-2xs text-muted-foreground/60">enter to send · shift+enter for newline</span>
          </div>
        </div>
      </div>
    </PanelShell>
  )
}

function MessageRow({ m, onCancel }: { m: ChatMessage; onCancel?: () => void }) {
  const isUser = m.role === "user"
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-2">
        <span
          className={cn(
            "text-2xs uppercase tracking-[0.12em]",
            isUser ? "text-info" : m.role === "system" ? "text-muted-foreground" : "text-accent",
          )}
        >
          {isUser ? "user" : m.role === "system" ? "system" : "jarvis"}
        </span>
        <span className="text-2xs text-muted-foreground/50">{fmtClock(m.ts)}</span>
        {m.streaming ? <Chip tone="accent">streaming</Chip> : null}
        {onCancel && m.streaming ? (
          <button onClick={onCancel} className="text-2xs text-error hover:underline">
            cancel
          </button>
        ) : null}
      </div>
      <div
        className={cn(
          "whitespace-pre-wrap text-pretty rounded-md border px-3 py-2 text-sm leading-relaxed",
          isUser
            ? "border-info/25 bg-info/5 text-foreground"
            : m.role === "system"
              ? "border-border bg-elevated/50 text-muted-foreground"
              : "border-border bg-elevated text-foreground",
        )}
      >
        {m.content}
        {m.streaming ? <span className="ml-0.5 inline-block h-3.5 w-1.5 translate-y-0.5 animate-pulse bg-accent" /> : null}
      </div>
      {m.usage ? (
        <div className="flex items-center gap-3 px-1 text-2xs text-muted-foreground/60">
          <span className="tabular">in {fmtNum(m.usage.input)}</span>
          <span className="tabular">out {fmtNum(m.usage.output)}</span>
          {m.usage.totalCostUsd != null ? <span className="tabular">{fmtUsd(m.usage.totalCostUsd)}</span> : null}
          {m.model ? <span>{m.model}</span> : null}
        </div>
      ) : null}
    </div>
  )
}
