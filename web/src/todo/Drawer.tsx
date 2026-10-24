// The to-do drawer beside the plan (v22): a quick add with what Friday read, the list grouped by when or tag, rows
// you can tick off or drag onto the calendar. Its frame also holds an open event (COMBINED.md 12), and its left edge
// drags to make it wider or narrower, kept for next time (personal's drawer, COMBINED.md 11).

import { type ReactNode, useState } from "react"
import { useNavigate } from "react-router"
import type { Item } from "@/api/client"
import { useDragging } from "@/components/calendar/useDrag"
import { DueLabel } from "@/components/DueLabel"
import { Check, Icon, Seg } from "@/components/fr/controls"
import { readFields, useAdd, useParsed } from "@/components/todo/QuickAdd"
import { useCommand } from "@/hooks/useCommand"
import { useHorizon, useItems } from "@/hooks/queries"
import { dur, when } from "@/lib/format"
import { nextBlocks } from "@/lib/todo"
import { useLook } from "@/theme/LookProvider"
import { useShell } from "@/shell/ShellContext"
import { Dropdown } from "@/components/fr/Dropdown"
import { grouped, type SortBy } from "./groups"
import { SortPicker } from "./SortPicker"
import { ExpiresMark } from "./TodoPage"

/** The drawer's frame: over the calendar's right side, below the title row, resized by its left edge. */
export function DrawerFrame({ children, todo }: { children: ReactNode; todo?: boolean }) {
  const { drawerWidth, setDrawerWidth, drawerOver } = useShell()
  const grab = (e: React.PointerEvent) => {
    e.preventDefault()
    const from = e.clientX
    const was = drawerWidth
    const move = (ev: PointerEvent) => setDrawerWidth(was + from - ev.clientX)
    const up = () => (window.removeEventListener("pointermove", move), window.removeEventListener("pointerup", up))
    window.addEventListener("pointermove", move)
    window.addEventListener("pointerup", up)
  }
  return (
    <aside
      data-drop={todo ? "todo" : undefined}
      className="fr-float"
      style={{ position: "absolute", right: 12, top: 60, bottom: 0, ...(drawerOver ? { left: "calc(var(--fr-side) + 12px)", maxWidth: drawerWidth + 160, marginLeft: "auto", boxShadow: "0 12px 40px color-mix(in srgb, #000 35%, transparent)" } : { width: drawerWidth }), zIndex: 7, display: "flex", flexDirection: "column", gap: 12, minHeight: 0, padding: "12px 14px 0", borderRadius: "var(--radius-lg) var(--radius-lg) 0 0" }}
    >
      <div
        role="separator"
        aria-orientation="vertical"
        aria-label="Drag to resize"
        title="Drag to make the drawer wider or narrower"
        onPointerDown={grab}
        hidden={drawerOver}
        style={{ position: "absolute", left: -4, top: 0, bottom: 0, width: 8, cursor: "ew-resize", touchAction: "none" }}
      />
      {children}
    </aside>
  )
}

export function Drawer() {
  const { today, setDrawer } = useShell()
  const navigate = useNavigate()
  const [by, setBy] = useState<"When" | "Tag">("When")
  const [sort, setSort] = useState<SortBy>("Next up")
  const items = useItems().data ?? []
  const blocks = useHorizon().data?.blocks ?? []
  const groups = grouped(items, blocks, today, by, sort)
  return (
    <DrawerFrame todo>
      <div style={{ display: "flex", alignItems: "center", gap: 8, height: 32 }}>
        <span className="fr-h" style={{ fontSize: 20, lineHeight: 1 }}>
          To-do
        </span>
        <span className="tnum fr-kicker">{items.length}</span>
        <div style={{ flex: 1 }} />
        <button className="btn btn-icon btn-ghost" onClick={() => navigate("/todo")} aria-label="Open full to-do" title="Open full to-do" style={{ width: 28, height: 28, color: "var(--color-neutral-400)" }}>
          <Icon name="arrows-out-simple" />
        </button>
        <button className="btn btn-icon btn-ghost" onClick={() => setDrawer(false)} aria-label="Close" style={{ width: 28, height: 28, color: "var(--color-neutral-400)" }}>
          <Icon name="x" />
        </button>
      </div>
      <QuickLine />
      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <Seg options={["When", "Tag"] as const} value={by} onPick={setBy} size="small" />
        <div style={{ flex: 1 }} />
        <Dropdown icon="sort-ascending" label={sort}>
          {(close) => (
            <div style={{ padding: 6, width: 210 }}>
              <SortPicker value={sort} onPick={(v) => (setSort(v), close())} compact />
            </div>
          )}
        </Dropdown>
      </div>
      <div style={{ overflowY: "auto", minHeight: 0, flex: 1, display: "flex", flexDirection: "column", gap: 14, paddingBottom: 24 }}>
        {groups.map((g) => (
          <div key={g.name} style={{ display: "flex", flexDirection: "column" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", padding: "0 4px 4px" }}>
              <span style={{ fontSize: 12, color: "var(--color-neutral-400)" }}>{g.name}</span>
              <span className="tnum" style={{ fontSize: 11, color: "var(--color-neutral-600)" }}>
                {g.items.length}
              </span>
            </div>
            {g.items.map((i) => (
              <Row key={i.id} item={i} />
            ))}
          </div>
        ))}
      </div>
    </DrawerFrame>
  )
}

/** A to-do typed in one line, with the fields Friday read from it. */
export function QuickLine({ placeholder = "Add a to-do" }: { placeholder?: string }) {
  const { today } = useShell()
  const [text, setText] = useState("")
  const parsed = readFields(useParsed(text)?.fields ?? {})
  const add = useAdd()
  const chips = [
    ["Kind", parsed.preset],
    ["Tag", parsed.area],
    ["Due", parsed.due ? when(parsed.due, today) : null],
    ["Length", parsed.duration_min ? `~${dur(parsed.duration_min)}` : null],
    ["Repeats", parsed.every ? "yes" : null],
  ].filter(([, v]) => v != null) as [string, string][]
  return (
    <>
      <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "0 10px", height: 34, borderRadius: "var(--radius-md)", background: "var(--color-surface)", boxShadow: "inset 0 0 0 1px color-mix(in srgb, var(--color-text) 8%, transparent)" }}>
        <Icon name="plus" style={{ color: "var(--color-neutral-500)" }} />
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={async (e) => {
            if (e.key === "Enter" && text.trim() && (await add({ text }))) setText("")
            if (e.key === "Escape") setText("")
          }}
          placeholder={placeholder}
          style={{ flex: 1, minWidth: 0, border: 0, outline: 0, background: "transparent", color: "var(--color-text)", font: "inherit" }}
        />
        <span style={{ fontSize: 11, color: "var(--color-neutral-600)" }}>N</span>
      </div>
      {text && chips.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: -6 }}>
          {chips.map(([k, v]) => (
            <span key={k} style={{ display: "inline-flex", gap: 4, padding: "2px 8px", borderRadius: "var(--radius-sm)", background: "color-mix(in srgb, var(--color-accent) 16%, transparent)", color: "var(--color-accent-200)", fontSize: 11 }}>
              <span style={{ color: "var(--color-accent-400)" }}>{k}</span>
              {v}
            </span>
          ))}
        </div>
      )}
    </>
  )
}

function Row({ item }: { item: Item }) {
  const { today } = useShell()
  const navigate = useNavigate()
  const { color } = useLook()
  const { begin } = useDragging()
  const blocks = useHorizon().data?.blocks ?? []
  const done = useCommand("done", { label: () => `${item.title}: done` })
  const next = nextBlocks(blocks).get(item.id)
  const length = item.remaining_min ?? item.duration_min ?? 60
  const overdue = !!item.due && item.due < `${today}T00:00`
  return (
    <div
      onClick={() => navigate(`/todo?item=${item.id}`)}
      onPointerDown={(e) => begin(e, { kind: "row", start: 0, end: length, grab: 0, itemId: item.id, blockKey: null, title: item.title })}
      className="fr-hover"
      style={{ display: "grid", gridTemplateColumns: "16px 3px minmax(0,1fr) auto", gap: 9, alignItems: "center", padding: "6px 4px", borderRadius: "var(--radius-md)", cursor: "pointer", touchAction: "none" }}
    >
      <Check small done={false} onToggle={() => done({ id: item.id })} />
      <span style={{ alignSelf: "stretch", borderRadius: 2, background: color(item.area) }} />
      <span style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
        <span style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", color: item.long_term ? "var(--fr-aged)" : undefined }}>
          {item.pointless_late && <ExpiresMark />} {item.title}
        </span>
        <span className="tnum" style={{ fontSize: 11, color: overdue ? "var(--fr-due)" : "var(--color-neutral-500)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
          {next ? when(next.start, today) : "not planned"}
          {item.due && (
            <>
              {" · "}
              <DueLabel due={item.due} prefix="due " />
            </>
          )}
        </span>
      </span>
      <span className="tnum" style={{ fontSize: 11, color: "var(--color-neutral-500)" }}>
        {item.remaining_min ? dur(item.remaining_min) : ""}
      </span>
    </div>
  )
}
