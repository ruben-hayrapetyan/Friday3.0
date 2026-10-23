// The To-do page (v22): the add box, then every open item grouped and sorted your way, each with its progress, when
// it's next planned and when it's due; one selected opens its detail beside the list.

import { useQuery } from "@tanstack/react-query"
import { useState } from "react"
import { useSearchParams } from "react-router"
import { type Item, query } from "@/api/client"
import { Check, Chip, Icon, Seg } from "@/components/fr/controls"
import { useCommand } from "@/hooks/useCommand"
import { useHorizon, useNow, useStatus } from "@/hooks/queries"
import { dur, when } from "@/lib/format"
import { nextBlocks } from "@/lib/todo"
import { toMin } from "@/lib/time"
import { useLook } from "@/theme/LookProvider"
import { useShell } from "@/shell/ShellContext"
import { AddBox } from "./AddBox"
import { GROUPS, type GroupBy, grouped, progress, SORTS, type SortBy, summary } from "./groups"
import { TodoDetail } from "./TodoDetail"

export const useAllItems = (done: boolean) =>
  useQuery({ queryKey: ["items", done ? "all" : "todo"], queryFn: () => query("items", { status: done ? "all" : "todo" }) })

export function TodoPage() {
  const { today } = useShell()
  const [by, setBy] = useState<GroupBy>("When")
  const [sort, setSort] = useState<SortBy>("Next up")
  const [showDone, setShowDone] = useState(false)
  const [fresh, setFresh] = useState<number[]>([])
  const [params, setParams] = useSearchParams()
  const selected = params.get("item") ? Number(params.get("item")) : null
  const items = (useAllItems(showDone).data ?? []).filter((i) => showDone || i.status === "todo")
  const blocks = useHorizon().data?.blocks ?? []
  const status = useStatus().data
  const solving = !!status && status.plan_generation !== null && status.plan_generation < status.generation
  const groups = grouped(items, blocks, today, by, sort)
  const select = (id: number | null) => setParams(id ? { item: String(id) } : {}, { replace: true })
  return (
    <>
      <div className="fr-page-head" style={{ gap: 12 }}>
        <span className="fr-h fr-title">To-do</span>
        <span className="tnum" style={{ color: "var(--color-neutral-500)" }}>
          {summary(items)}
        </span>
        {solving && (
          <div className="fr-pill" style={{ background: "color-mix(in srgb, var(--color-accent) 14%, transparent)", color: "var(--color-accent-200)" }}>
            <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--color-accent)" }} />
            Replanning
          </div>
        )}
        <div style={{ flex: 1 }} />
        <Chip on={showDone} onClick={() => setShowDone(!showDone)}>
          Show done
        </Chip>
        <span className="fr-kicker">Group by</span>
        <Seg options={GROUPS} value={by} onPick={setBy} />
        <span className="fr-kicker" style={{ marginLeft: 6 }}>
          Sort
        </span>
        <select className="input" value={sort} onChange={(e) => setSort(e.target.value as SortBy)} style={{ width: 130, padding: "4px 8px", fontSize: 12, minHeight: 0 }}>
          {SORTS.map((s) => (
            <option key={s}>{s}</option>
          ))}
        </select>
      </div>
      <div className="fr-panel" style={{ display: "grid", gridTemplateColumns: selected ? "minmax(0,1fr) 400px" : "minmax(0,1fr)", overflow: "hidden" }}>
        <div style={{ overflowY: "auto", minHeight: 0, padding: "18px 22px 140px", display: "flex", flexDirection: "column", gap: 22 }}>
          <AddBox onAdded={(id) => setFresh([...fresh, id])} />
          {groups.map((g) => (
            <div key={g.name} style={{ display: "flex", flexDirection: "column" }}>
              <div style={{ display: "flex", alignItems: "baseline", gap: 10, padding: "0 8px 8px" }}>
                <span className="fr-h" style={{ fontSize: 18 }}>
                  {g.name}
                </span>
                <span className="tnum" style={{ fontSize: 12, color: "var(--color-neutral-500)" }}>
                  {g.items.length} · {dur(g.items.reduce((s, i) => s + (i.remaining_min ?? 0), 0))}
                </span>
              </div>
              {g.items.map((i) => (
                <Row key={i.id} item={i} fresh={fresh.includes(i.id)} selected={i.id === selected} onSelect={() => select(i.id === selected ? null : i.id)} />
              ))}
            </div>
          ))}
          {!groups.length && <div style={{ padding: "40px 8px", color: "var(--color-neutral-400)" }}>Nothing left. Add something above, or turn on Show done to see what you finished.</div>}
        </div>
        {selected && <TodoDetail id={selected} onClose={() => select(null)} />}
      </div>
    </>
  )
}

function Row({ item, fresh, selected, onSelect }: { item: Item; fresh: boolean; selected: boolean; onSelect: () => void }) {
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
      className="fr-row fr-hover-soft"
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
          <span style={{ fontWeight: 500, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", textDecoration: isDone ? "line-through" : undefined }}>{item.title}</span>
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
        <span style={{ color: soon ? "var(--fr-due)" : "var(--color-neutral-500)" }}>{item.due ? `Due ${when(item.due, today)}` : "No due date"}</span>
      </div>
    </div>
  )
}
