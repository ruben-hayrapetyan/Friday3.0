// The To-do page: personal's notebook (COMBINED.md 21, 22) with Friday's reading of each task. Short term in
// sections by kind (readings, assignments, errands, the rest), each ruled and ending in its own add line that takes
// due dates, lengths and tags as you'd say them; Long term in its own sepia ink; Due, every dated task soonest first
// with the now line after the ones already past. A row is one line: the title, its tag, and on the right what
// Friday made of it (start-by warnings, progress, time left, when it's next planned, the due countdown). Click one
// for everything about it beside the list; ⌘-click or Shift-click several (⌘A for all) to change them together.
// View options keep v22's grouping by when or tag, sorting, done items and the two-line rows with progress bars.

import { Dropdown } from "@/components/fr/Dropdown"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useEffect, useState } from "react"
import { NavLink, useSearchParams } from "react-router"
import { type Item, query } from "@/api/client"
import { Check, Chip, Icon, Seg } from "@/components/fr/controls"
import { useToast } from "@/components/Toasts"
import { rememberTogether, runCommand, undoAll, useCommand } from "@/hooks/useCommand"
import { useHorizon, useNow, useStatus } from "@/hooks/queries"
import { DueLabel } from "@/components/DueLabel"
import { useClock } from "@/hooks/useClock"
import { dur, lateBy, when } from "@/lib/format"
import { nextBlocks } from "@/lib/todo"
import { ProjectName } from "@/projects/StepOf"
import { toMin } from "@/lib/time"
import { useLook } from "@/theme/LookProvider"
import { pigment } from "@/lib/pigments"
import { useShell } from "@/shell/ShellContext"
import { AddBox } from "./AddBox"
import { BulkBar, menuOpen, pickWith, tasks } from "./Bulk"
import { addHint, fillFor, GROUPS, type GroupBy, grouped, KINDS_FIRST, OTHER, plural, progress, SORTS, type SortBy, summary } from "./groups"
import { flashRow, listHolding } from "./found"
import { DuePicker, LengthInput } from "./Pickers"
import { useDuplicates } from "@/inbox/queries"
import { SortPicker } from "./SortPicker"
import { TodoDetail } from "./TodoDetail"

const DRAG = "text/x-friday-item" // tasks dragged to another section: their ids, comma-separated

/** What a drag from a row carries: every picked task when it's one of them (27 Oct: "dragging multiple items from one
 * todo to the other"), else that task alone. */
export function draggedIds(id: number, picked: number[]): number[] {
  return picked.length > 1 && picked.includes(id) ? picked : [id]
}

/** The tasks a drop brings, from what the drag carried. */
export function droppedIds(data: string): number[] {
  return data.split(",").map(Number).filter((n) => Number.isInteger(n) && n > 0)
}

/** A drag's picture: "3 tasks" rather than the one row under the pointer. */
function dragPicture(e: React.DragEvent, n: number): void {
  if (n < 2) return
  const tag = document.createElement("div")
  tag.textContent = tasks(n)
  Object.assign(tag.style, { position: "fixed", top: "-100px", padding: "4px 10px", borderRadius: "6px", font: "500 12px system-ui", color: "#fff", background: "#3b6fd4" })
  document.body.appendChild(tag)
  e.dataTransfer.setDragImage(tag, 12, 12)
  setTimeout(() => tag.remove(), 0)
}

export const useAllItems = (done: boolean) =>
  useQuery({ queryKey: ["items", done ? "all" : "todo"], queryFn: () => query("items", { status: done ? "all" : "todo" }) })

const LISTS = ["Short term", "Long term", "Due"] as const
type List = (typeof LISTS)[number]

export function TodoPage() {
  const { today } = useShell()
  const { look, setLook, light } = useLook()
  const copies = useDuplicates().data?.groups.length ?? 0
  const move = useCommand("edit", { label: (o) => `Moved ${o.result.item?.title ?? ""}` })
  const client = useQueryClient()
  const toast = useToast()
  // Several dropped together: each moved, said once, undone together, as the bar's changes are (todo/Bulk.tsx).
  const moveAll = async (ids: number[], fields: Record<string, unknown>, where: string) => {
    if (ids.length === 1) return void move({ id: ids[0], ...fields })
    const done: number[] = []
    for (const id of ids) {
      const out = await runCommand(client, toast, "edit", { id, ...fields }, { quiet: true })
      if (out?.command_id != null) done.push(out.command_id)
    }
    rememberTogether(done)
    if (done.length) toast({ message: `Moved ${tasks(done.length)} to ${where}. ⌘Z undoes it`, action: { label: "Undo", run: () => undoAll(client, toast, done) } })
  }
  const [over, setOver] = useState<string | null>(null) // the section a task is being dragged over
  const [by, setBy] = useStored<GroupBy>("friday-todo-group", "Kind", GROUPS)
  const [sort, setSort] = useStored<SortBy>("friday-todo-sort", "Next up", SORTS)
  const [showDone, setShowDone] = useState(false)
  const [fresh, setFresh] = useState<number[]>([])
  const [params, setParams] = useSearchParams()
  const selected = params.get("item") ? Number(params.get("item")) : null
  const found = params.get("found") === "1"
  const list: List = (LISTS as readonly string[]).includes(params.get("list") ?? "") ? (params.get("list") as List) : "Short term"
  const all = (useAllItems(showDone).data ?? []).filter((i) => showDone || i.status === "todo")
  const items = list === "Due" ? all.filter(isDueWork) : all.filter((i) => i.long_term === (list === "Long term"))
  const blocks = useHorizon().data?.blocks ?? []
  const status = useStatus().data
  const solving = !!status && status.plan_generation !== null && status.plan_generation < status.generation
  const always = by === "Kind" ? (list === "Short term" ? [...KINDS_FIRST.filter((k) => k !== "Exam prep"), OTHER] : [OTHER]) : by === "Tag" ? ["No tag"] : []
  const groups = grouped(items, blocks, today, by, sort, list === "Due" ? [] : always, all)
  const compact = look.todoRows === "Compact"
  const RowOf = compact ? CompactRow : Row
  const added = (id: number) => setFresh((was) => [...was, id])
  const select = (id: number | null) => setParams({ ...(id ? { item: String(id) } : {}), ...(list !== "Short term" ? { list } : {}) }, { replace: true })
  const pickList = (next: List) => setParams(next === "Short term" ? {} : { list: next }, { replace: true })
  // Several at once: ⌘ (or Ctrl) adds one, Shift a run, ⌘A all shown; a plain click goes back to one task's detail.
  const [picked, setPicked] = useState<number[]>([])
  const [anchor, setAnchor] = useState<number | null>(null)
  const order = list === "Due" ? [...items].sort((a, b) => (a.due as string).localeCompare(b.due as string)).map((i) => i.id) : groups.flatMap((g) => g.items.map((i) => i.id))
  const pickedItems = items.filter((i) => picked.includes(i.id))
  const choose = (id: number, e: { metaKey: boolean; ctrlKey: boolean; shiftKey: boolean }) => {
    const toggle = e.metaKey || e.ctrlKey
    if (!toggle && !e.shiftKey) return (setPicked([]), select(id === selected ? null : id))
    setPicked(pickWith(order, picked.length ? picked : selected ? [selected] : [], anchor ?? selected, id, toggle, e.shiftKey))
    setAnchor(id)
    if (selected) select(null)
  }
  // Found from the calendar: in the list that holds it, its row scrolled to and flashed blue, its detail open.
  const target = found && selected !== null ? all.find((i) => i.id === selected) : undefined
  useEffect(() => {
    if (!target) return
    const there = items.some((i) => i.id === target.id)
    const want = listHolding(target, list, there)
    if (want !== list) return setParams({ item: String(target.id), found: "1", ...(want !== "Short term" ? { list: want } : {}) }, { replace: true })
    const frame = requestAnimationFrame(() => {
      flashRow(target.id, pigment("blue", light) ?? "#2a6c9c")
      setParams({ item: String(target.id), ...(list !== "Short term" ? { list } : {}) }, { replace: true })
    })
    return () => cancelAnimationFrame(frame)
  }, [target, items, list, light, setParams])
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLElement && e.target.closest("input, textarea, select, [contenteditable]")) return
      if (e.key === "Escape" && picked.length && !menuOpen()) setPicked([])
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "a" && order.length) {
        e.preventDefault()
        setPicked(order)
      }
    }
    window.addEventListener("keydown", key)
    return () => window.removeEventListener("keydown", key)
  })
  return (
    <>
      <div className="fr-page-head" style={{ gap: 12 }}>
        <span className="fr-h fr-title">To-do</span>
        <span data-tour="todo-lists" style={{ flex: "none", display: "flex" }}>
          <Seg options={LISTS} value={list} onPick={pickList} label="List" />
        </span>
        <span className="tnum fr-head-note" style={{ color: "var(--color-neutral-500)" }}>
          {summary(items)}
        </span>
        {copies > 0 && (
          <NavLink to="/inbox" className="fr-pill fr-hover" style={{ fontSize: 12, color: "var(--fr-warn)", textDecoration: "none" }} title="The same task more than once: a message each in your Inbox">
            <Icon name="copy" size={12} />
            {copies} with copies · In your Inbox
          </NavLink>
        )}
        {solving && (
          <div className="fr-pill" style={{ background: "color-mix(in srgb, var(--color-accent) 14%, transparent)", color: "var(--color-accent-200)" }}>
            <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--color-accent)" }} />
            Replanning
          </div>
        )}
        <div style={{ flex: 1 }} />
        <Dropdown icon="sliders-horizontal" label="View options">
          {() => (
            <div style={{ display: "flex", flexDirection: "column", gap: 14, padding: "10px 12px", width: 250 }}>
              {list !== "Due" && (
                <>
                  <span style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    <span className="fr-eyebrow">Sections</span>
                    <Seg options={GROUPS.map((g) => ({ value: g, label: g === "Kind" ? "By kind" : g === "When" ? "By when" : "By tag" }))} value={by} onPick={setBy} />
                  </span>
                  <span style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    <span className="fr-eyebrow">Sort</span>
                    <SortPicker value={sort} onPick={setSort} />
                  </span>
                </>
              )}
              <span style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <span className="fr-eyebrow">Rows</span>
                <Seg options={[{ value: "Compact" as const, label: "One line" }, { value: "Detailed" as const, label: "Two lines" }]} value={look.todoRows} onPick={(todoRows) => setLook({ todoRows })} />
              </span>
              <Chip on={showDone} onClick={() => setShowDone(!showDone)}>
                <Icon name={showDone ? "eye" : "eye-slash"} size={12} />
                Show done
              </Chip>
            </div>
          )}
        </Dropdown>
      </div>
      <div className="fr-panel fr-todo-split" data-open={selected ? "" : undefined} style={{ display: "grid", gridTemplateColumns: selected ? "minmax(0,1fr) 400px" : "minmax(0,1fr)", overflow: "hidden", position: "relative" }}>
        {pickedItems.length > 0 && <BulkBar items={pickedItems} onClear={() => setPicked([])} />}
        <div className="fr-gutter" style={{ overflowY: "auto", minHeight: 0, padding: "16px 22px 140px" }}>
          <div data-tour="todo-list" style={{ display: "flex", flexDirection: "column", gap: 22 }}>
            {(by === "When" || list === "Due") && <AddBox compact onAdded={added} longTerm={list === "Long term"} placeholder="Add a to-do…" />}
            {list === "Due" ? (
              <DueList items={items} fresh={fresh} selected={selected} picked={picked} onSelect={choose} Row={RowOf} />
            ) : (
              groups.map((g) => {
                const fill = fillFor(by, g.name)
                return (
                  <section
                    key={g.name}
                    // Drag a task here to make it this kind (or give it this tag): an assignment that's really an errand.
                    onDragOver={(e) => fill && e.dataTransfer.types.includes(DRAG) && (e.preventDefault(), setOver(g.name))}
                    onDragLeave={(e) => !e.currentTarget.contains(e.relatedTarget as Node) && setOver(null)}
                    onDrop={(e) => {
                      setOver(null)
                      const ids = droppedIds(e.dataTransfer.getData(DRAG)).filter((id) => !g.items.some((i) => i.id === id))
                      if (!fill || !ids.length) return
                      moveAll(ids, by === "Tag" ? { area: fill.area ?? null } : { preset: fill.preset ?? null }, by === "Kind" && g.name !== "Done" ? plural(g.name) : g.name)
                    }}
                    style={{ display: "flex", flexDirection: "column", borderRadius: 6, outline: over === g.name ? "1.5px dashed var(--color-accent)" : undefined, outlineOffset: 4 }}
                  >
                    <SectionRule name={by === "Kind" && g.name !== "Done" ? plural(g.name) : g.name} items={g.items} />
                    {g.items.map((i) => (
                      <RowOf key={i.id} item={i} by={by} fresh={fresh.includes(i.id)} selected={i.id === selected} picked={picked.includes(i.id)} onSelect={(e) => choose(i.id, e)} dragging={draggedIds(i.id, picked)} />
                    ))}
                    {fill && <AddBox compact onAdded={added} longTerm={list === "Long term"} fill={fill} placeholder={addHint(by, g.name)} />}
                  </section>
                )
              })
            )}
            {!groups.length && list !== "Due" && <div style={{ padding: "40px 8px", color: "var(--color-neutral-400)" }}>Nothing left. Add something above, or turn on Show done to see what you finished.</div>}
            <span className="fr-mono" style={{ fontSize: 11.5, color: "var(--color-neutral-500)" }}>
              Type it the way you’d say it: <span style={{ color: "var(--color-neutral-300)" }}>ch 4 #psych due fri 5pm ~1h</span>. Click a task for everything about it; ⌘-click or Shift-click to pick several; drag one (or one of those picked, and they all go) onto another section to change its kind.
            </span>
          </div>
        </div>
        {selected && <TodoDetail key={selected} id={selected} onClose={() => select(null)} />}
      </div>
    </>
  )
}

/** What the Due view lists: work with a due date, not each day's meals and habits (personal's Due page held tasks). */
export function isDueWork(i: Item): boolean {
  return !!i.due && i.amount === "fixed" && i.preset !== "Routine" && i.preset !== "Habit"
}

/** personal's ⏳: work that is pointless once its deadline has passed, so never planned after it. */
export function ExpiresMark() {
  return (
    <span title="Pointless once late: never planned after it's due" aria-label="Pointless once late" style={{ fontSize: 11, flex: "none" }}>
      ⏳
    </span>
  )
}

/** Every dated task, soonest first, with the now line after the ones already past (personal's Due page). */
function DueList({ items, fresh, selected, picked, onSelect, Row }: { items: Item[]; fresh: number[]; selected: number | null; picked: number[]; onSelect: (id: number, e: React.MouseEvent | React.KeyboardEvent) => void; Row: (p: RowProps) => React.ReactNode }) {
  const now = useClock()
  const sorted = [...items].sort((a, b) => (a.due as string).localeCompare(b.due as string))
  const past = sorted.filter((i) => toMin(i.due as string) < now).length
  return (
    <div style={{ display: "flex", flexDirection: "column" }}>
      {sorted.map((i, n) => (
        <div key={i.id} style={{ display: "contents" }}>
          {n === past && past > 0 && <div role="separator" aria-label="Now" style={{ height: 2, margin: "4px 8px", borderRadius: 1, background: "var(--fr-now)" }} />}
          <Row item={i} by="Due" fresh={fresh.includes(i.id)} selected={i.id === selected} picked={picked.includes(i.id)} onSelect={(e) => onSelect(i.id, e)} />
        </div>
      ))}
      {!sorted.length && <div style={{ padding: "40px 8px", color: "var(--color-neutral-400)" }}>Nothing has a due date.</div>}
    </div>
  )
}

interface RowProps {
  item: Item
  by: GroupBy | "Due" // what the list is grouped by, which the row then needn't repeat
  fresh: boolean
  selected: boolean
  picked: boolean // one of several picked to change together
  onSelect: (e: React.MouseEvent | React.KeyboardEvent) => void
  dragging?: number[] // what a drag from it carries onto another section: it, or all picked with it
}

/** A row's drag onto another section: the tasks it carries, and their picture. */
function dragFrom(dragging: number[] | undefined, id: number) {
  const ids = dragging ?? [id]
  return (e: React.DragEvent) => {
    e.dataTransfer.setData(DRAG, ids.join(","))
    e.dataTransfer.effectAllowed = "move"
    dragPicture(e, ids.length)
  }
}

/** A section's head, as personal ruled it: its name, a rule to the edge, how many and how long. */
function SectionRule({ name, items }: { name: string; items: Item[] }) {
  const left = items.reduce((s, i) => s + (i.status === "todo" ? (i.remaining_min ?? 0) : 0), 0)
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 9, paddingBottom: 6 }}>
      <span className="fr-mono" style={{ fontSize: 11.5, letterSpacing: "0.16em", textTransform: "uppercase", color: "var(--color-neutral-400)" }}>
        {name}
      </span>
      <span style={{ flex: 1, height: 1, background: "var(--fr-rule)" }} />
      <span className="fr-mono tnum" style={{ fontSize: 11.5, color: "var(--color-neutral-500)" }}>
        {items.length ? `${items.length}${left ? ` · ${dur(left)}` : ""}` : "nothing yet"}
      </span>
    </div>
  )
}

/** One line, as personal's notebook drew a task, with what Friday made of it on the right. */
function CompactRow({ item, by, fresh, selected, picked, onSelect, dragging }: RowProps) {
  const { today } = useShell()
  const { color } = useLook()
  const blocks = useHorizon().data?.blocks ?? []
  const now = useNow().data
  const done = useCommand("done", { label: () => `${item.title}: done` })
  const reopen = useCommand("reopen", { label: () => `${item.title}: open again` })
  const next = nextBlocks(blocks, useAllItems(false).data).get(item.id) // a project's: its steps' soonest
  const isNow = now?.current?.item_id === item.id
  const alert = now?.alerts.find((a) => a.item_id === item.id)
  const late = useStatus().data?.late_items?.find((l) => l.item_id === item.id)
  // Not once it's due: the due beside it says how far over it is.
  const due = useClock() >= (item.due ? toMin(item.due) : Infinity)
  const slip = useStatus().data?.slipping?.find((l) => l.item_id === item.id && !due)
  const isDone = item.status === "done"
  const left = item.remaining_min ?? 0
  const share = item.done_min && item.done_min + left ? item.done_min / (item.done_min + left) : 0
  const meta = { fontSize: 11, color: "var(--color-neutral-500)", whiteSpace: "nowrap" } as const
  // What can be changed in the line is changed in the line (double-click the title; click the time left or the
  // due); everything else is a click away, beside the list.
  const edit = useCommand("edit", { label: () => "Saved" })
  const [editing, setEditing] = useState<"title" | "due" | "length" | null>(null)
  const [title, setTitle] = useState(item.title)
  const inline = (what: "due" | "length") => (e: React.MouseEvent) => (e.stopPropagation(), setEditing(editing === what ? null : what))
  const rename = () => {
    if (title.trim() && title.trim() !== item.title) edit({ id: item.id, title: title.trim() })
    setEditing(null)
  }
  const cell = { ...meta, textAlign: "right", cursor: "text", borderRadius: 3, padding: "1px 3px" } as const
  return (
    <>
    <div
      data-todo-row={item.id}
      role="button"
      tabIndex={0}
      onClick={(e) => editing === null && onSelect(e)}
      onMouseDown={(e) => e.shiftKey && e.preventDefault()}
      draggable={editing === null}
      onDragStart={dragFrom(dragging, item.id)}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && e.target === e.currentTarget && editing === null && (e.preventDefault(), onSelect(e))}
      className="fr-hover-soft fr-todo-line"
      title={`${item.title}: click for everything about it, double-click the title to rename`}
      style={{
        display: "grid",
        gridTemplateColumns: "24px minmax(0,1fr) auto",
        alignItems: "center",
        minHeight: 28,
        borderRadius: 4,
        background: picked ? "color-mix(in srgb, var(--color-accent) 22%, transparent)" : selected ? "color-mix(in srgb, var(--color-accent) 12%, transparent)" : undefined,
        boxShadow: picked ? "inset 0 0 0 1px color-mix(in srgb, var(--color-accent) 55%, transparent)" : undefined,
        cursor: "pointer",
        opacity: isDone ? 0.55 : 1,
      }}
    >
      <span style={{ display: "flex", justifyContent: "center" }}>
        <Check small done={isDone} onToggle={() => (isDone ? reopen({ id: item.id }) : done({ id: item.id }))} />
      </span>
      {/* personal's ruled margin, in the task's paint: its tag's, else its kind's, as on the calendar */}
      <span style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0, alignSelf: "stretch", paddingLeft: 10, boxShadow: `inset 2px 0 0 ${color(item.area, item.preset)}` }}>
        {editing === "title" ? (
          <input
            autoFocus
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            onClick={(e) => e.stopPropagation()}
            onBlur={rename}
            onKeyDown={(e) => {
              e.stopPropagation()
              if (e.key === "Enter") rename()
              if (e.key === "Escape") (setTitle(item.title), setEditing(null))
            }}
            aria-label="Title"
            style={{ flex: 1, minWidth: 0, font: "inherit", fontSize: 13, color: "var(--color-text)", background: "transparent", border: 0, outline: 0, boxShadow: "inset 0 -1.5px 0 var(--color-accent)", padding: 0 }}
          />
        ) : (
          <span
            onDoubleClick={(e) => (e.stopPropagation(), setTitle(item.title), setEditing("title"))}
            style={{ fontSize: 13, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", textDecoration: isDone ? "line-through" : undefined, color: item.long_term ? "var(--fr-aged)" : undefined }}
          >
            {item.title}
          </span>
        )}
        {item.pointless_late && <ExpiresMark />}
        {fresh && <span style={{ fontSize: 11.5, color: "var(--color-accent-300)", flex: "none" }}>new</span>}
        {item.area && by !== "Tag" && (
          <span className="fr-tag-mini" style={{ display: "inline-flex", gap: 4, alignItems: "center", flex: "none", fontSize: 11.5, color: "var(--color-neutral-400)" }}>
            <span style={{ width: 6, height: 6, borderRadius: 2, background: color(item.area, item.preset) }} />
            {item.area}
          </span>
        )}
        <ProjectName item={item} style={{ flex: "0 0.4 auto", minWidth: 52, maxWidth: "40%", fontSize: 11.5, color: "var(--color-neutral-400)" }} />
        {by !== "Kind" && <span style={{ fontSize: 11.5, color: "var(--color-neutral-500)", flex: "none" }}>{item.preset ?? ""}</span>}
      </span>
      <span className="tnum fr-mono fr-todo-meta" style={{ display: "flex", alignItems: "center", gap: 12, paddingLeft: 12, paddingRight: 6 }}>
        {late && !isDone && <LateTag hours={late.hours} />}
        {slip && !late && !isDone && <SlipTag slip={slip} />}
        {alert && !isDone && !late && <StartBy alert={alert} today={today} />}
        {share > 0 && <Pie share={share} />}
        <span className="fr-hover" onClick={inline("length")} style={{ ...cell, minWidth: 40 }} title={`${progress(item).text}. Click to change`}>
          {left > 0 && !isDone ? dur(left) : "·"}
        </span>
        <span style={{ ...meta, minWidth: 84, textAlign: "right" }} title={next ? "Next planned" : "Not on the plan yet"}>
          {isNow ? <span className="fr-tag accent">Now</span> : next ? when(next.start, today) : isDone ? "done" : "—"}
        </span>
        <span className="fr-hover" onClick={inline("due")} style={{ ...cell, minWidth: 104 }} title={item.due ? "Due. Click to change" : "Click to set a due date"}>
          {item.due ? <DueLabel due={item.due} prefix="due " routine={item.preset === "Routine"} /> : <span className="fr-todo-more">+ due</span>}
        </span>
        <span className="fr-todo-more" style={{ display: "inline-flex" }}>
          <Icon name="caret-right" size={10} />
        </span>
      </span>
    </div>
    {editing === "due" && (
      <InlineEditor onClose={() => setEditing(null)}>
        <DuePicker value={item.due ?? null} today={today} onPick={(due) => edit({ id: item.id, due })} onDone={() => setEditing(null)} />
      </InlineEditor>
    )}
    {editing === "length" && (
      <InlineEditor onClose={() => setEditing(null)}>
        <span style={{ fontSize: 12, color: "var(--color-neutral-400)" }}>How long it takes in all{item.done_min ? `, ${dur(item.done_min)} done so far` : ""}</span>
        <LengthInput value={item.duration_min ?? null} onPick={(duration_min) => (edit({ id: item.id, duration_min }), setEditing(null))} width={160} />
      </InlineEditor>
    )}
    </>
  )
}

/** An editor opened under its row, in the list rather than over it; Escape or Done closes it. */
function InlineEditor({ children, onClose }: { children: React.ReactNode; onClose: () => void }) {
  return (
    <div
      onKeyDown={(e) => e.key === "Escape" && onClose()}
      style={{ margin: "2px 0 8px 34px", padding: "10px 12px", borderRadius: "var(--radius-md)", background: "var(--color-surface)", boxShadow: "0 0 0 1px var(--fr-rule)", display: "flex", flexDirection: "column", gap: 8, position: "relative" }}
    >
      {children}
      <button className="fr-link" onClick={onClose} style={{ position: "absolute", top: 8, right: 10, fontSize: 11 }}>
        Done
      </button>
    </div>
  )
}

/** The plan finishes it after its due, by about this much. */
function LateTag({ hours }: { hours: number }) {
  return (
    <span className="fr-tag" title={`The plan finishes this about ${lateBy(hours)} after it's due`} style={{ color: "var(--fr-due)", background: "color-mix(in srgb, var(--fr-now) 14%, transparent)", flex: "none", alignSelf: "flex-start" }}>
      {lateBy(hours)} late
    </span>
  )
}

/** Work with a soft deadline the plan finishes after its due, or doesn't plan at all (27 Oct: readings ran days past
 * their due and nothing said so). In the warning color, not the late red: a soft deadline may slip. */
function SlipTag({ slip }: { slip: { hours: number; planned?: boolean } }) {
  const planned = slip.planned !== false
  return (
    <span
      className="fr-tag"
      title={planned ? `The plan finishes this about ${lateBy(slip.hours)} after it's due` : "There's no time for this in the plan before it's due"}
      style={{ color: "var(--fr-warn)", background: "color-mix(in srgb, var(--fr-mark) 14%, transparent)", flex: "none", alignSelf: "flex-start", whiteSpace: "nowrap" }}
    >
      {planned ? `${lateBy(slip.hours)} late` : "not planned"}
    </span>
  )
}

/** How much is done, as personal's little pie. */
function Pie({ share }: { share: number }) {
  const a = Math.min(share, 0.999) * 2 * Math.PI
  const x = 5 + 4 * Math.sin(a)
  const y = 5 - 4 * Math.cos(a)
  return (
    <svg width={10} height={10} viewBox="0 0 10 10" aria-label={`${Math.round(share * 100)}% done`} style={{ flex: "none" }}>
      <circle cx={5} cy={5} r={4.4} fill="none" stroke="var(--color-neutral-400)" strokeWidth={1.1} />
      <path d={`M5 5 L5 1 A4 4 0 ${share > 0.5 ? 1 : 0} 1 ${x} ${y} Z`} fill="var(--color-neutral-300)" />
    </svg>
  )
}

/** The two-line row (v22), for those who like progress bars: View options → Rows → Detailed. */
function Row({ item, fresh, selected, picked, onSelect, dragging }: RowProps) {
  const { today } = useShell()
  const { color } = useLook()
  const blocks = useHorizon().data?.blocks ?? []
  const now = useNow().data
  const done = useCommand("done", { label: () => `${item.title}: done` })
  const reopen = useCommand("reopen", { label: () => `${item.title}: open again` })
  const next = nextBlocks(blocks, useAllItems(false).data).get(item.id) // a project's: its steps' soonest
  const isNow = now?.current?.item_id === item.id
  const alert = now?.alerts.find((a) => a.item_id === item.id)
  const late = useStatus().data?.late_items?.find((l) => l.item_id === item.id)
  // Not once it's due: the due beside it says how far over it is.
  const due = useClock() >= (item.due ? toMin(item.due) : Infinity)
  const slip = useStatus().data?.slipping?.find((l) => l.item_id === item.id && !due)
  const p = progress(item)
  const isDone = item.status === "done"
  const soon = item.due && item.firmness === "hard" && toMin(item.due) - toMin(`${today}T00:00`) < 2 * 1440
  return (
    <div
      data-todo-row={item.id}
      role="button"
      tabIndex={0}
      onClick={onSelect}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && e.target === e.currentTarget && (e.preventDefault(), onSelect(e))}
      onMouseDown={(e) => e.shiftKey && e.preventDefault()}
      draggable
      onDragStart={dragFrom(dragging, item.id)}
      className="fr-row fr-hover-soft fr-todo-row"
      style={{
        display: "grid",
        gridTemplateColumns: "22px 3px minmax(160px,1fr) minmax(90px,140px) minmax(110px,150px)",
        gap: 12,
        alignItems: "center",
        padding: "10px 8px",
        borderRadius: "var(--radius-md)",
        background: picked ? "color-mix(in srgb, var(--color-accent) 22%, transparent)" : selected ? "color-mix(in srgb, var(--color-accent) 10%, transparent)" : undefined,
        boxShadow: picked ? "inset 0 0 0 1px color-mix(in srgb, var(--color-accent) 55%, transparent)" : undefined,
        cursor: "pointer",
        opacity: isDone ? 0.55 : 1,
      }}
    >
      <Check done={isDone} onToggle={() => (isDone ? reopen({ id: item.id }) : done({ id: item.id }))} />
      <span style={{ alignSelf: "stretch", borderRadius: 2, background: color(item.area, item.preset) }} />
      <div style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
        <span style={{ display: "flex", gap: 8, alignItems: "baseline", minWidth: 0 }}>
          <span style={{ fontWeight: 500, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", textDecoration: isDone ? "line-through" : undefined, color: item.long_term ? "var(--fr-aged)" : undefined }}>{item.title}</span>
          {item.pointless_late && <ExpiresMark />}
          {fresh && <span style={{ fontSize: 11, color: "var(--color-accent-300)" }}>new</span>}
        </span>
        <span style={{ fontSize: 12, color: "var(--color-neutral-500)", display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
          <span>{item.preset ?? "To-do"}</span>
          {item.area && (
            <span style={{ display: "inline-flex", gap: 5, alignItems: "center" }}>
              <span style={{ width: 7, height: 7, borderRadius: 2, background: color(item.area, item.preset) }} />
              {item.area}
            </span>
          )}
          <ProjectName item={item} style={{ maxWidth: "100%" }} />
          {alert && !late && <StartBy alert={alert} today={today} />}
        </span>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <div style={{ height: 4, borderRadius: 2, background: "color-mix(in srgb, var(--color-text) 8%, transparent)", overflow: "hidden" }}>
          <div style={{ height: "100%", width: `${p.pct}%`, borderRadius: 2, background: color(item.area, item.preset) }} />
        </div>
        <span className="tnum" style={{ fontSize: 11, color: "var(--color-neutral-500)" }}>
          {p.text}
        </span>
      </div>
      <div className="tnum" style={{ display: "flex", flexDirection: "column", gap: 1, fontSize: 12 }}>
        {isNow ? (
          <span className="fr-tag accent" style={{ alignSelf: "flex-start" }}>
            Now
          </span>
        ) : (
          <span style={{ color: "var(--color-neutral-300)" }}>{next ? when(next.start, today) : isDone ? "Done" : "not planned"}</span>
        )}
        <span style={{ color: soon ? "var(--fr-due)" : "var(--color-neutral-500)" }}>{item.due ? <DueLabel due={item.due} routine={item.preset === "Routine"} /> : "No due date"}</span>
        {late && !isDone && <LateTag hours={late.hours} />}
        {slip && !late && !isDone && <SlipTag slip={slip} />}
      </div>
    </div>
  )
}

/** A choice kept on this device. */
function useStored<T extends string>(key: string, initial: T, allowed: readonly T[]): [T, (value: T) => void] {
  const [value, setValue] = useState<T>(() => {
    try {
      const saved = localStorage.getItem(key) as T | null
      return saved && allowed.includes(saved) ? saved : initial
    } catch {
      return initial
    }
  })
  const set = (next: T) => {
    setValue(next)
    try {
      localStorage.setItem(key, next)
    } catch {
      // private mode: kept for this visit
    }
  }
  return [value, set]
}


/** When to start to finish on time, in words (27 Oct: a bare ⚠ said nothing until you hovered over it): "start now"
 * when that's now or past, else "start by 6pm". Work that will be late says so instead (LateTag). */
function StartBy({ alert, today }: { alert: { kind: string; latest_start: string }; today: string }) {
  const urgent = alert.kind !== "soon"
  return (
    <span
      className="fr-tag"
      title={urgent ? "Start now to finish it on time" : `Start by ${when(alert.latest_start, today)} to finish it on time`}
      style={{ color: "var(--fr-warn)", background: "color-mix(in srgb, var(--fr-mark) 14%, transparent)", flex: "none", alignSelf: "flex-start", whiteSpace: "nowrap" }}
    >
      {urgent ? "start now" : `start by ${when(alert.latest_start, today)}`}
    </span>
  )
}
