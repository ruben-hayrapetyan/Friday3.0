// Repeating (v22): everything that comes back, grouped (classes and commitments, habits and routines, from your
// calendars and feeds), each with a switch, how often, when next and where it came from.

import { useQuery } from "@tanstack/react-query"
import { useRef } from "react"
import { query, type Schemas } from "@/api/client"
import { H, Icon, Menu, Switch } from "@/components/fr/controls"
import { useCommand } from "@/hooks/useCommand"
import { useAreas } from "@/hooks/queries"
import { when } from "@/lib/format"
import { useLook } from "@/theme/LookProvider"
import { useShell } from "@/shell/ShellContext"
import { useNavigate } from "react-router"
import { draftOf } from "@/shell/EventPane"
import { foundHref } from "@/todo/found"
import { RepeatImport } from "./RepeatImport"
import { SectionHead } from "./SettingsPage"

type Row = Schemas["SeriesRow"]

export function Repeating() {
  const series = useQuery({ queryKey: ["series_list"], queryFn: () => query("series_list") }).data ?? []
  const groups: [string, string, Row[]][] = [
    ["Classes and commitments", "At set times; Friday plans around them", series.filter((s) => s.fixed && s.source === "you" && !s.external)],
    ["Habits and routines", "Flexible; Friday finds the time", series.filter((s) => !s.fixed && s.source === "you" && !s.external)],
    ["From your calendars and feeds", "Kept up to date from the source", series.filter((s) => s.source !== "you" || s.external)],
  ]
  return (
    <>
      <SectionHead title="Repeating" note="Everything that comes back. Add repeats from the to-do box (“gym 3x a week ~1h”), or bring them in from your calendar." />
      <RepeatImport />
      {groups
        .filter(([, , rows]) => rows.length)
        .map(([name, desc, rows]) => (
          <div key={name} style={{ display: "flex", flexDirection: "column", paddingBottom: 18 }}>
            <div style={{ display: "flex", alignItems: "baseline", gap: 10, paddingBottom: 6 }}>
              <H size={18}>{name}</H>
              <span className="fr-kicker">{desc}</span>
            </div>
            {rows.map((r) => (
              <SeriesLine key={r.id} row={r} />
            ))}
          </div>
        ))}
      {!series.length && <span className="fr-kicker">Nothing repeats yet.</span>}
    </>
  )
}

function SeriesLine({ row }: { row: Row }) {
  const { today, setEvent } = useShell()
  const { color } = useLook()
  const stop = useCommand("series_stop", { label: () => `${row.title} stopped; future ones removed` })
  const resume = useCommand("series_resume", { label: () => `${row.title} repeats again` })
  const remove = useCommand("series_delete", { label: (o) => o.result.message ?? "Deleted" })
  // Its tag, from today on (one from a calendar keeps its times there; 3 Nov: `series_edit` had no button)
  const retag = useCommand("series_edit", { label: () => `${row.title}: tag changed from today on` })
  const tags = (useAreas().data ?? []).filter((a) => !a.archived).map((a) => a.name)
  // Everything about a repeat is in its editor (8 Nov): an event's opens over the calendar, a task's in the to-do.
  const navigate = useNavigate()
  const open = async (r: Row) => {
    if (r.next_id == null) return
    if (!r.fixed) return navigate(foundHref(r.next_id))
    const found = await query("item", { id: r.next_id })
    navigate("/")
    setEvent(draftOf(found.item))
  }
  return (
    <div className="fr-row" style={{ display: "grid", gridTemplateColumns: "36px 10px minmax(0,1fr) auto 28px", gap: 12, alignItems: "center", padding: "10px 0", opacity: row.active ? 1 : 0.5 }}>
      <Switch on={row.active} onToggle={() => (row.active ? stop({ id: row.id }) : resume({ id: row.id }))} label={`${row.active ? "Stop" : "Start"} ${row.title}`} />
      <span style={{ width: 10, height: 10, borderRadius: 3, background: color(row.area) }} />
      <span style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
        {row.next_id != null ? (
          <button className="fr-link" onClick={() => open(row)} title={row.fixed ? "Open in its editor" : "Open it in the to-do"} style={{ fontWeight: 500, fontSize: "inherit", textAlign: "left", color: "var(--color-text)" }}>
            {row.title}
          </button>
        ) : (
          <span style={{ fontWeight: 500 }}>{row.title}</span>
        )}
        <span className="tnum fr-kicker" style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
          {row.pattern} ·
          <Menu label={`Tag for ${row.title}`} value={row.area ?? ""} onPick={(tag) => tag !== (row.area ?? "") && retag({ id: row.id, area: tag || null })} options={[{ value: "", label: "No tag" }, ...[...new Set([...tags, ...(row.area ? [row.area] : [])])].map((t) => ({ value: t, label: t }))]} />
          {!row.fixed && !row.external && (
            <>
              ·
              <TimesApart row={row} />
            </>
          )}
        </span>
      </span>
      <span className="tnum" style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 2, fontSize: 12 }}>
        <span style={{ color: "var(--color-neutral-300)" }}>{row.next ? `Next ${when(row.next, today)}` : row.active ? "None coming up" : "Stopped"}</span>
        <span style={{ color: "var(--color-neutral-500)" }}>{row.source === "you" ? "Added by you" : row.external ? `From ${row.source}; times follow the calendar` : `From ${row.source}`}</span>
      </span>
      {row.external ? (
        <span />
      ) : (
        <button className="btn btn-ghost" onClick={() => remove({ id: row.id })} aria-label={`Delete ${row.title}`} title="Delete; what you did stays in your history" style={{ padding: "2px 6px", color: "var(--color-neutral-500)" }}>
          <Icon name="trash" />
        </button>
      )}
    </div>
  )
}

const GAPS = ["2", "3", "5", "7", "10", "14"]

/** A repeat's times kept apart, counted from when you did the last one (C50: "laundry at least 7 days apart"): here
 * and in a repeating task's detail (8 Nov: one place for everything about a repeat). */
export function TimesApart({ row }: { row: Pick<Row, "id" | "title" | "min_gap_days"> }) {
  const picked = useRef<string>("")
  const space = useCommand("series_spacing", { label: () => `${row.title}: ${picked.current ? `at least ${picked.current} days apart` : "times not kept apart"}` })
  const gap = row.min_gap_days ? String(row.min_gap_days) : ""
  return (
    <Menu
      label={`Days between ${row.title}`}
      value={gap}
      onPick={(days) => days !== gap && ((picked.current = days), space({ id: row.id, days: days ? Number(days) : null }))}
      options={[{ value: "", label: "Times apart: any" }, ...GAPS.map((d) => ({ value: d, label: `At least ${d} days apart` })), ...(gap && !GAPS.includes(gap) ? [{ value: gap, label: `At least ${gap} days apart` }] : [])]}
    />
  )
}

/** The repeat a task or event belongs to, as Settings → Repeating lists it. */
export function useSeriesRow(seriesId: number | null | undefined): Row | undefined {
  const rows = useQuery({ queryKey: ["series_list"], queryFn: () => query("series_list"), enabled: seriesId != null }).data
  return rows?.find((r) => r.id === seriesId)
}
