import { useState } from "react"
import { ChevronRight, File, Folder, FolderOpen, HardDrive } from "lucide-react"
import { useJarvis } from "@/store/jarvis"
import { PanelShell, Label, EmptyState } from "@/components/ui/primitives"
import { fmtBytes } from "@/lib/format"
import { cn } from "@/lib/utils"
import type { FsNode } from "@/lib/ipc/protocol"

export function FilesPanel() {
  const tree = useJarvis((s) => s.fsTree)
  const [selected, setSelected] = useState<string | null>(null)

  return (
    <PanelShell
      toolbar={
        <>
          <HardDrive className="h-3.5 w-3.5 text-accent" />
          <Label>files</Label>
          {tree ? <span className="truncate text-2xs text-muted-foreground">{tree.path}</span> : null}
        </>
      }
    >
      {!tree ? (
        <EmptyState>Filesystem tree not loaded.</EmptyState>
      ) : (
        <div className="scroll-thin h-full overflow-auto py-1 font-mono text-xs">
          {(tree.children ?? []).map((node) => (
            <TreeNode key={node.path} node={node} depth={0} selected={selected} onSelect={setSelected} />
          ))}
        </div>
      )}
    </PanelShell>
  )
}

function TreeNode({
  node,
  depth,
  selected,
  onSelect,
}: {
  node: FsNode
  depth: number
  selected: string | null
  onSelect: (p: string) => void
}) {
  const [open, setOpen] = useState(depth < 1)
  const isDir = node.type === "dir"
  const isSel = selected === node.path

  return (
    <div>
      <button
        onClick={() => {
          onSelect(node.path)
          if (isDir) setOpen((v) => !v)
        }}
        className={cn(
          "flex w-full items-center gap-1 py-0.5 pr-2 text-left transition-colors hover:bg-elevated/60",
          isSel && "bg-elevated",
        )}
        style={{ paddingLeft: `${depth * 12 + 6}px` }}
      >
        {isDir ? (
          <ChevronRight className={cn("h-3 w-3 shrink-0 text-muted-foreground transition-transform", open && "rotate-90")} />
        ) : (
          <span className="w-3 shrink-0" />
        )}
        {isDir ? (
          open ? (
            <FolderOpen className="h-3.5 w-3.5 shrink-0 text-accent" />
          ) : (
            <Folder className="h-3.5 w-3.5 shrink-0 text-accent" />
          )
        ) : (
          <File className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        )}
        <span className={cn("truncate", isDir ? "text-foreground" : "text-muted-foreground")}>{node.name}</span>
        {!isDir ? <span className="ml-auto shrink-0 pl-2 text-2xs text-muted-foreground/50">{fmtBytes(node.size)}</span> : null}
      </button>
      {isDir && open ? (
        <div>
          {(node.children ?? []).map((c) => (
            <TreeNode key={c.path} node={c} depth={depth + 1} selected={selected} onSelect={onSelect} />
          ))}
        </div>
      ) : null}
    </div>
  )
}
