// The to-do drawer beside the plan (v22): a quick add with what Friday read, the list grouped by when or tag, rows
// you can tick off or drag onto the calendar. Its frame also holds an open event (COMBINED.md 12), and its left edge
// drags to make it wider or narrower, kept for next time (personal's drawer, COMBINED.md 11).

import { useWhatIf } from "@/whatif/store"
import { type ReactNode, useEffect, useRef, useState } from "react"
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
import { BulkBar, menuOpen, pickWith } from "./Bulk"
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
  const trying = useWhatIf().on
  // Several at once, as on the To-do page: ⌘ adds one, Shift a run. Dragged together onto the calendar, they're
  // planned one after another; onto a day, all due that day.
  const [picked, setPicked] = useState<number[]>([])
  const [anchor, setAnchor] = useState<number | null>(null)
  const order = groups.flatMap((g) => g.items.map((i) => i.id))
  const pickedItems = items.filter((i) => picked.includes(i.id))
  const choose = (id: number, e: React.MouseEvent | React.KeyboardEvent) => {
    const toggle = e.metaKey || e.ctrlKey
    if (!toggle && !e.shiftKey) return (setPicked([]), navigate(`/todo?item=${id}`))
    setPicked(pickWith(order, picked, anchor, id, toggle, e.shiftKey))
    setAnchor(id)
  }
  useEffect(() => {
    if (!picked.length) return
    const key = (e: KeyboardEvent) => e.key === "Escape" && !menuOpen() && setPicked([])
    window.addEventListener("keydown", key)
    return () => window.removeEventListener("keydown", key)
  }, [picked.length])
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
      {trying && (
        <span style={{ display: "flex", gap: 6, alignItems: "center", marginTop: -6, fontSize: 11.5, color: "var(--color-accent-200)" }}>
          <Icon name="flask" size={12} />
          What if is on: a to-do added here is tried on the calendar, not saved.
        </span>
      )}
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
              <span className="tnum" style={{ fontSize: 11, color: "var(--color-neutral-500)" }}>
                {g.items.length}
              </span>
            </div>
            {g.items.map((i) => (
              <Row key={i.id} item={i} picked={picked.includes(i.id)} together={picked.includes(i.id) && pickedItems.length > 1 ? pickedItems : null} onClick={(e) => choose(i.id, e)} />
            ))}
          </div>
        ))}
      </div>
      {pickedItems.length > 0 && <BulkBar items={pickedItems} onClear={() => setPicked([])} hint="Drag them onto the calendar or a day" place="drawer" />}
    </DrawerFrame>
  )
}

/** A to-do typed in one line, with the fields Friday read from it. */
export function QuickLine({ placeholder = "Add a to-do" }: { placeholder?: string }) {
  const { today } = useShell()
  const [text, setText] = useState("")
  const parsed = readFields(useParsed(text)?.fields ?? {})
  const add = useAdd()
  const sending = useRef(false) // ↩ held or pressed twice adds it once
  const chips = [
    ["Kind", parsed.preset],
    ["Tag", parsed.area],
    ["Due", parsed.due ? when(parsed.due, today) : null],
    ["Length", parsed.duration_min ? `~${dur(parsed.duration_min)}` : null],
    ["Repeats", parsed.every ? "yes" : null],
  ].filter(([, v]) => v != null) as [string, string][]
  return (
    <>
      <div data-tour="drawer-add" style={{ display: "flex", alignItems: "center", gap: 8, padding: "0 10px", height: 34, borderRadius: "var(--radius-md)", background: "var(--color-surface)", boxShadow: "inset 0 0 0 1px color-mix(in srgb, var(--color-text) 8%, transparent)" }}>
        <Icon name="plus" style={{ color: "var(--color-neutral-500)" }} />
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={async (e) => {
            if (e.key === "Enter" && text.trim() && !sending.current) {
              sending.current = true
              if (await add({ text })) setText("")
              sending.current = false
            }
            if (e.key === "Escape") setText("")
          }}
          placeholder={placeholder}
          style={{ flex: 1, minWidth: 0, border: 0, outline: 0, background: "transparent", color: "var(--color-text)", font: "inherit" }}
        />
        <span style={{ fontSize: 11, color: "var(--color-neutral-500)" }}>N</span>
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

const lengthOf = (item: Item) => item.remaining_min ?? item.duration_min ?? 60

function Row({ item, picked, together, onClick }: { item: Item; picked: boolean; together: Item[] | null; onClick: (e: React.MouseEvent | React.KeyboardEvent) => void }) {
  const { today } = useShell()
  const { color } = useLook()
  const { begin } = useDragging()
  const blocks = useHorizon().data?.blocks ?? []
  const done = useCommand("done", { label: () => `${item.title}: done` })
  const next = nextBlocks(blocks).get(item.id)
  const length = lengthOf(item)
  const overdue = !!item.due && item.due < `${today}T00:00`
  // A picked row takes the others picked with it, in the list's order.
  const rows = together?.map((i) => ({ id: i.id, title: i.title, length: lengthOf(i) }))
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && e.target === e.currentTarget && (e.preventDefault(), onClick(e))}
      onPointerDown={(e) => begin(e, { kind: "row", start: 0, end: rows ? rows.reduce((sum, r) => sum + r.length, 0) : length, grab: 0, itemId: item.id, blockKey: null, title: rows ? `${rows.length} to-dos` : item.title, rows })}
      className="fr-hover"
      style={{
        display: "grid",
        gridTemplateColumns: "16px 3px minmax(0,1fr) auto",
        gap: 9,
        alignItems: "center",
        padding: "6px 4px",
        borderRadius: "var(--radius-md)",
        cursor: "pointer",
        touchAction: "none",
        ...(picked ? { background: "color-mix(in srgb, var(--color-accent) 22%, transparent)", boxShadow: "inset 0 0 0 1px color-mix(in srgb, var(--color-accent) 55%, transparent)" } : {}),
      }}
    >
      <Check small done={false} onToggle={() => done({ id: item.id })} />
      <span style={{ alignSelf: "stretch", borderRadius: 2, background: color(item.area, item.preset) }} />
      <span style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
        <span style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", color: item.long_term ? "var(--fr-aged)" : undefined }}>
          {item.pointless_late && <ExpiresMark />} {item.title}
        </span>
        <span className="tnum" style={{ fontSize: 11, color: overdue ? "var(--fr-due)" : "var(--color-neutral-500)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
          {next ? when(next.start, today) : "not planned"}
          {item.due && (
            <>
              {" · "}
              <DueLabel due={item.due} prefix="due " routine={item.preset === "Routine"} />
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
