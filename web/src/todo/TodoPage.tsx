// The To-do page: personal's notebook (COMBINED.md 21, 22) with Friday's reading of each task. Short term in
// sections by kind (readings, assignments, errands, the rest), each ruled and ending in its own add line that takes
// due dates, lengths and tags as you'd say them; Long term in its own sepia ink; Due, every dated task soonest first
// with the now line after the ones already past. A row is one line: the title, its tag, and on the right what
// Friday made of it (start-by warnings, progress, time left, when it's next planned, the due countdown). Click one
// for everything about it beside the list. View options keep v22's grouping by when or tag, sorting, done items and
// the two-line rows with progress bars.

import { Dropdown } from "@/components/fr/Dropdown"
import { useQuery } from "@tanstack/react-query"
import { useState } from "react"
import { useSearchParams } from "react-router"
import { type Item, query } from "@/api/client"
import { Check, Chip, Icon, Seg } from "@/components/fr/controls"
import { useCommand } from "@/hooks/useCommand"
import { useHorizon, useNow, useStatus } from "@/hooks/queries"
import { DueLabel } from "@/components/DueLabel"
import { useClock } from "@/hooks/useClock"
import { dur, when } from "@/lib/format"
import { nextBlocks } from "@/lib/todo"
import { toMin } from "@/lib/time"
import { useLook } from "@/theme/LookProvider"
import { useShell } from "@/shell/ShellContext"
import { AddBox } from "./AddBox"
import { addHint, fillFor, GROUPS, type GroupBy, grouped, KINDS_FIRST, OTHER, plural, progress, SORTS, type SortBy, summary } from "./groups"
import { TodoDetail } from "./TodoDetail"

export const useAllItems = (done: boolean) =>
  useQuery({ queryKey: ["items", done ? "all" : "todo"], queryFn: () => query("items", { status: done ? "all" : "todo" }) })

const LISTS = ["Short term", "Long term", "Due"] as const
type List = (typeof LISTS)[number]

export function TodoPage() {
  const { today } = useShell()
  const { look, setLook } = useLook()
  const [by, setBy] = useStored<GroupBy>("friday-todo-group", "Kind", GROUPS)
  const [sort, setSort] = useState<SortBy>("Next up")
  const [showDone, setShowDone] = useState(false)
  const [fresh, setFresh] = useState<number[]>([])
  const [params, setParams] = useSearchParams()
  const selected = params.get("item") ? Number(params.get("item")) : null
  const list: List = (LISTS as readonly string[]).includes(params.get("list") ?? "") ? (params.get("list") as List) : "Short term"
  const all = (useAllItems(showDone).data ?? []).filter((i) => showDone || i.status === "todo")
  const items = list === "Due" ? all.filter(isDueWork) : all.filter((i) => i.long_term === (list === "Long term"))
  const blocks = useHorizon().data?.blocks ?? []
  const status = useStatus().data
  const solving = !!status && status.plan_generation !== null && status.plan_generation < status.generation
  const always = by === "Kind" ? (list === "Short term" ? [...KINDS_FIRST.filter((k) => k !== "Exam prep"), OTHER] : [OTHER]) : by === "Tag" ? ["No tag"] : []
  const groups = grouped(items, blocks, today, by, sort, list === "Due" ? [] : always)
  const compact = look.todoRows === "Compact"
  const RowOf = compact ? CompactRow : Row
  const added = (id: number) => setFresh((was) => [...was, id])
  const select = (id: number | null) => setParams({ ...(id ? { item: String(id) } : {}), ...(list !== "Short term" ? { list } : {}) }, { replace: true })
  const pickList = (next: List) => setParams(next === "Short term" ? {} : { list: next }, { replace: true })
  return (
    <>
      <div className="fr-page-head" style={{ gap: 12 }}>
        <span className="fr-h fr-title">To-do</span>
        <Seg options={LISTS} value={list} onPick={pickList} label="List" />
        <span className="tnum fr-head-note" style={{ color: "var(--color-neutral-500)" }}>
          {summary(items)}
        </span>
        {solving && (
          <div className="fr-pill" style={{ background: "color-mix(in srgb, var(--color-accent) 14%, transparent)", color: "var(--color-accent-200)" }}>
            <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--color-accent)" }} />
            Replanning
          </div>
        )}
        <div style={{ flex: 1 }} />
        <Dropdown icon="sliders-horizontal" label="View options">
          {() => (
            <div style={{ display: "flex", flexDirection: "column", gap: 12, padding: "8px 10px" }}>
              <Chip on={showDone} onClick={() => setShowDone(!showDone)}>
                Show done
              </Chip>
              <span style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <span className="fr-kicker">Rows</span>
                <Seg options={["Compact", "Detailed"] as const} value={look.todoRows} onPick={(todoRows) => setLook({ todoRows })} />
              </span>
              {list !== "Due" && (
                <>
                  <span style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    <span className="fr-kicker">Group by</span>
                    <Seg options={GROUPS} value={by} onPick={setBy} />
                  </span>
                  <span style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    <span className="fr-kicker">Sort</span>
                    <select className="input" value={sort} onChange={(e) => setSort(e.target.value as SortBy)} style={{ padding: "4px 8px", fontSize: 12, minHeight: 0 }}>
                      {SORTS.map((s) => (
                        <option key={s}>{s}</option>
                      ))}
                    </select>
                  </span>
                </>
              )}
            </div>
          )}
        </Dropdown>
      </div>
      <div className="fr-panel fr-todo-split" data-open={selected ? "" : undefined} style={{ display: "grid", gridTemplateColumns: selected ? "minmax(0,1fr) 400px" : "minmax(0,1fr)", overflow: "hidden" }}>
        <div className="fr-gutter" style={{ overflowY: "auto", minHeight: 0, padding: "16px 22px 140px" }}>
          <div style={{ maxWidth: 940, display: "flex", flexDirection: "column", gap: 22 }}>
            {(by === "When" || list === "Due") && <AddBox compact onAdded={added} longTerm={list === "Long term"} placeholder="Add a to-do…" />}
            {list === "Due" ? (
              <DueList items={items} fresh={fresh} selected={selected} onSelect={(id) => select(id === selected ? null : id)} Row={RowOf} />
            ) : (
              groups.map((g) => {
                const fill = fillFor(by, g.name)
                return (
                  <section key={g.name} style={{ display: "flex", flexDirection: "column" }}>
                    <SectionRule name={by === "Kind" ? plural(g.name) : g.name} items={g.items} />
                    {g.items.map((i) => (
                      <RowOf key={i.id} item={i} by={by} fresh={fresh.includes(i.id)} selected={i.id === selected} onSelect={() => select(i.id === selected ? null : i.id)} />
                    ))}
                    {fill && <AddBox compact onAdded={added} longTerm={list === "Long term"} fill={fill} placeholder={addHint(by, g.name)} />}
                  </section>
                )
              })
            )}
            {!groups.length && list !== "Due" && <div style={{ padding: "40px 8px", color: "var(--color-neutral-400)" }}>Nothing left. Add something above, or turn on Show done to see what you finished.</div>}
            <span className="fr-mono" style={{ fontSize: 10.5, color: "var(--color-neutral-500)" }}>
              Type it the way you’d say it: <span style={{ color: "var(--color-neutral-300)" }}>ch 4 #psych due fri 5pm ~1h</span>. Click a task for everything about it.
            </span>
          </div>
        </div>
        {selected && <TodoDetail id={selected} onClose={() => select(null)} />}
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
function DueList({ items, fresh, selected, onSelect, Row }: { items: Item[]; fresh: number[]; selected: number | null; onSelect: (id: number) => void; Row: (p: RowProps) => React.ReactNode }) {
  const now = useClock()
  const sorted = [...items].sort((a, b) => (a.due as string).localeCompare(b.due as string))
  const past = sorted.filter((i) => toMin(i.due as string) < now).length
  return (
    <div style={{ display: "flex", flexDirection: "column" }}>
      {sorted.map((i, n) => (
        <div key={i.id} style={{ display: "contents" }}>
          {n === past && past > 0 && <div role="separator" aria-label="Now" style={{ height: 2, margin: "4px 8px", borderRadius: 1, background: "var(--fr-now)" }} />}
          <Row item={i} by="Due" fresh={fresh.includes(i.id)} selected={i.id === selected} onSelect={() => onSelect(i.id)} />
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
  onSelect: () => void
}

/** A section's head, as personal ruled it: its name, a rule to the edge, how many and how long. */
function SectionRule({ name, items }: { name: string; items: Item[] }) {
  const left = items.reduce((s, i) => s + (i.status === "todo" ? (i.remaining_min ?? 0) : 0), 0)
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 9, paddingBottom: 6 }}>
      <span className="fr-mono" style={{ fontSize: 10.5, letterSpacing: "0.16em", textTransform: "uppercase", color: "var(--color-neutral-400)" }}>
        {name}
      </span>
      <span style={{ flex: 1, height: 1, background: "var(--fr-rule)" }} />
      <span className="fr-mono tnum" style={{ fontSize: 10.5, color: "var(--color-neutral-500)" }}>
        {items.length ? `${items.length}${left ? ` · ${dur(left)}` : ""}` : "nothing yet"}
      </span>
    </div>
  )
}

/** One line, as personal's notebook drew a task, with what Friday made of it on the right. */
function CompactRow({ item, by, fresh, selected, onSelect }: RowProps) {
  const { today } = useShell()
  const { color } = useLook()
  const blocks = useHorizon().data?.blocks ?? []
  const now = useNow().data
  const done = useCommand("done", { label: () => `${item.title}: done` })
  const reopen = useCommand("reopen", { label: () => `${item.title}: open again` })
  const next = nextBlocks(blocks).get(item.id)
  const isNow = now?.current?.item_id === item.id
  const startBy = now?.alerts.find((a) => a.item_id === item.id)?.latest_start
  const isDone = item.status === "done"
  const left = item.remaining_min ?? 0
  const share = item.done_min && item.done_min + left ? item.done_min / (item.done_min + left) : 0
  const meta = { fontSize: 11, color: "var(--color-neutral-500)", whiteSpace: "nowrap" } as const
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onSelect}
      onKeyDown={(e) => e.key === "Enter" && onSelect()}
      className="fr-hover-soft fr-todo-line"
      title={`${item.title}: click for everything about it`}
      style={{
        display: "grid",
        gridTemplateColumns: "24px minmax(0,1fr) auto",
        alignItems: "center",
        minHeight: 28,
        borderRadius: 4,
        background: selected ? "color-mix(in srgb, var(--color-accent) 12%, transparent)" : undefined,
        cursor: "pointer",
        opacity: isDone ? 0.55 : 1,
      }}
    >
      <span style={{ display: "flex", justifyContent: "center" }}>
        <Check small done={isDone} onToggle={() => (isDone ? reopen({ id: item.id }) : done({ id: item.id }))} />
      </span>
      {/* personal's ruled margin, in the task's tag colour */}
      <span style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0, alignSelf: "stretch", paddingLeft: 10, boxShadow: `inset ${item.area ? 2 : 1}px 0 0 ${item.area ? color(item.area) : "var(--fr-rule)"}` }}>
        <span style={{ fontSize: 13, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", textDecoration: isDone ? "line-through" : undefined, color: item.long_term ? "var(--fr-aged)" : undefined }}>{item.title}</span>
        {item.pointless_late && <ExpiresMark />}
        {fresh && <span style={{ fontSize: 10.5, color: "var(--color-accent-300)", flex: "none" }}>new</span>}
        {item.area && by !== "Tag" && (
          <span className="fr-tag-mini" style={{ display: "inline-flex", gap: 4, alignItems: "center", flex: "none", fontSize: 10.5, color: "var(--color-neutral-400)" }}>
            <span style={{ width: 6, height: 6, borderRadius: 2, background: color(item.area) }} />
            {item.area}
          </span>
        )}
        {by !== "Kind" && <span style={{ fontSize: 10.5, color: "var(--color-neutral-500)", flex: "none" }}>{item.preset ?? ""}</span>}
      </span>
      <span className="tnum fr-mono fr-todo-meta" style={{ display: "flex", alignItems: "center", gap: 12, paddingLeft: 12, paddingRight: 6 }}>
        {startBy && !isDone && (
          <span title={`Start by ${when(startBy, today)} to finish on time`} style={{ color: "var(--fr-warn)", display: "inline-flex" }}>
            <Icon name="warning" size={11} />
          </span>
        )}
        {share > 0 && <Pie share={share} />}
        <span style={{ ...meta, minWidth: 40, textAlign: "right" }} title={progress(item).text}>
          {left > 0 && !isDone ? dur(left) : ""}
        </span>
        <span style={{ ...meta, minWidth: 84, textAlign: "right" }} title={next ? "Next planned" : "Not on the plan yet"}>
          {isNow ? <span className="fr-tag accent">Now</span> : next ? when(next.start, today) : isDone ? "done" : "—"}
        </span>
        <span style={{ ...meta, minWidth: 104, textAlign: "right" }} title={item.due ? "Due" : undefined}>
          {item.due ? <DueLabel due={item.due} prefix="due " /> : ""}
        </span>
        <span className="fr-todo-more" style={{ display: "inline-flex" }}>
          <Icon name="caret-right" size={10} />
        </span>
      </span>
    </div>
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
function Row({ item, fresh, selected, onSelect }: RowProps) {
  const { today } = useShell()
  const { color } = useLook()
  const blocks = useHorizon().data?.blocks ?? []
  const now = useNow().data
  const done = useCommand("done", { label: () => `${item.title}: done` })
  const reopen = useCommand("reopen", { label: () => `${item.title}: open again` })
  const next = nextBlocks(blocks).get(item.id)
  const isNow = now?.current?.item_id === item.id
  const startBy = now?.alerts.find((a) => a.item_id === item.id)?.latest_start
  const p = progress(item)
  const isDone = item.status === "done"
  const soon = item.due && item.firmness === "hard" && toMin(item.due) - toMin(`${today}T00:00`) < 2 * 1440
  return (
    <div
      onClick={onSelect}
      className="fr-row fr-hover-soft fr-todo-row"
      style={{
        display: "grid",
        gridTemplateColumns: "22px 3px minmax(160px,1fr) minmax(90px,140px) minmax(110px,150px)",
        gap: 12,
        alignItems: "center",
        padding: "10px 8px",
        borderRadius: "var(--radius-md)",
        background: selected ? "color-mix(in srgb, var(--color-accent) 10%, transparent)" : undefined,
        cursor: "pointer",
        opacity: isDone ? 0.55 : 1,
      }}
    >
      <Check done={isDone} onToggle={() => (isDone ? reopen({ id: item.id }) : done({ id: item.id }))} />
      <span style={{ alignSelf: "stretch", borderRadius: 2, background: color(item.area) }} />
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
              <span style={{ width: 7, height: 7, borderRadius: 2, background: color(item.area) }} />
              {item.area}
            </span>
          )}
          {startBy && (
            <span style={{ color: "var(--fr-warn)" }}>
              <Icon name="warning" size={11} /> start by {when(startBy, today)}
            </span>
          )}
        </span>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <div style={{ height: 4, borderRadius: 2, background: "color-mix(in srgb, var(--color-text) 8%, transparent)", overflow: "hidden" }}>
          <div style={{ height: "100%", width: `${p.pct}%`, borderRadius: 2, background: color(item.area) }} />
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
        <span style={{ color: soon ? "var(--fr-due)" : "var(--color-neutral-500)" }}>{item.due ? <DueLabel due={item.due} /> : "No due date"}</span>
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
