// Repeating (v22): everything that comes back, grouped (classes and commitments, habits and routines, from your
// calendars and feeds), each with a switch, how often, when next and where it came from.

import { useQuery } from "@tanstack/react-query"
import { query, type Schemas } from "@/api/client"
import { H, Icon, Switch } from "@/components/fr/controls"
import { useCommand } from "@/hooks/useCommand"
import { when } from "@/lib/format"
import { useLook } from "@/theme/LookProvider"
import { useShell } from "@/shell/ShellContext"
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
  const { today } = useShell()
  const { color } = useLook()
  const stop = useCommand("series_stop", { label: () => `${row.title} stopped; future ones removed` })
  const resume = useCommand("series_resume", { label: () => `${row.title} repeats again` })
  const remove = useCommand("series_delete", { label: (o) => o.result.message ?? "Deleted" })
  return (
    <div className="fr-row" style={{ display: "grid", gridTemplateColumns: "36px 10px minmax(0,1fr) auto 28px", gap: 12, alignItems: "center", padding: "10px 0", opacity: row.active ? 1 : 0.5 }}>
      <Switch on={row.active} onToggle={() => (row.active ? stop({ id: row.id }) : resume({ id: row.id }))} label={`${row.active ? "Stop" : "Start"} ${row.title}`} />
      <span style={{ width: 10, height: 10, borderRadius: 3, background: color(row.area) }} />
      <span style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
        <span style={{ fontWeight: 500 }}>{row.title}</span>
        <span className="tnum fr-kicker">{row.pattern}</span>
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
