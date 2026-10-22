// Your Google calendars (M12b), alphabetized: each one read or not, its events read per event or all as one kind,
// and trusted (straight to the plan) or through the Inbox. The list is what the last sync saw, folded under one line
// saying how many are read.

import { useQuery } from "@tanstack/react-query"
import { useState } from "react"
import { query } from "@/api/client"
import { Icon, Menu, Switch } from "@/components/fr/controls"
import { useCommand } from "@/hooks/useCommand"
import { when } from "@/lib/format"
import { useShell } from "@/shell/ShellContext"
import { usePresets } from "@/todo/AddBox"

export const useCalendars = () => useQuery({ queryKey: ["google_calendars"], queryFn: () => query("google_calendars") })

const COLUMNS = "36px minmax(150px,1fr) 150px 72px"

export function Calendars() {
  const calendars = useCalendars().data ?? []
  const [open, setOpen] = useState(false)
  if (!calendars.length) return <span className="fr-kicker">Your calendars list here after the first sync with Google connected.</span>
  const reading = calendars.filter((c) => c.on)
  return (
    <div style={{ display: "flex", flexDirection: "column" }}>
      <button className="fr-plain fr-hover" onClick={() => setOpen(!open)} aria-expanded={open} style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 10px", margin: "0 -10px", borderRadius: "var(--radius-md)", textAlign: "left" }}>
        <Icon name={open ? "caret-down" : "caret-right"} size={13} style={{ color: "var(--color-neutral-400)" }} />
        <span style={{ fontWeight: 500 }}>Calendars</span>
        <span className="fr-kicker" style={{ flex: 1, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
          {reading.length} of {calendars.length} read{reading.length ? `: ${reading.map((c) => c.name).join(", ")}` : ""}
        </span>
      </button>
      {open && <List calendars={calendars} />}
    </div>
  )
}

function List({ calendars }: { calendars: NonNullable<ReturnType<typeof useCalendars>["data"]> }) {
  const { today } = useShell()
  const presets = usePresets()
  const set = useCommand("calendar_set", { label: (o) => o.result.message ?? "Saved" })
  const kinds = [{ value: "auto", label: "Per event" }, ...presets.map((p) => ({ value: p, label: p }))]
  return (
    <>
      <div className="fr-kicker" style={{ display: "grid", gridTemplateColumns: COLUMNS, gap: 12, padding: "6px 0 4px" }}>
        <span />
        <span>Calendar</span>
        <span>Read events as</span>
        <span title="Its events go straight into the plan">Skip Inbox</span>
      </div>
      {calendars.map((c) => (
        <div key={c.id} className="fr-row" style={{ display: "grid", gridTemplateColumns: COLUMNS, gap: 12, alignItems: "center", padding: "8px 0" }}>
          <Switch on={c.on} onToggle={() => set({ id: c.id, on: !c.on })} label={`Read ${c.name}`} />
          <span style={{ display: "flex", flexDirection: "column", gap: 1, minWidth: 0, opacity: c.on ? 1 : 0.6 }}>
            <span title={c.name} style={{ fontWeight: 500, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
              {c.name}
              {c.primary && <span className="fr-kicker"> · primary</span>}
            </span>
            <span title={c.error ?? undefined} style={{ fontSize: 12, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", color: c.on && c.error ? "var(--fr-due)" : "var(--color-neutral-500)" }}>
              {!c.on ? "Not read" : (c.error ?? (c.last_sync ? `Read ${when(c.last_sync, today)}` : "Reading now"))}
            </span>
          </span>
          <Menu options={kinds} value={c.kind} onPick={(kind) => set({ id: c.id, kind })} label={`How ${c.name} is read`} disabled={!c.on} />
          <span style={{ opacity: c.on ? 1 : 0.4 }}>
            <Switch on={c.trusted} onToggle={() => c.on && set({ id: c.id, trusted: !c.trusted })} label={`${c.name} straight to the plan`} />
          </span>
        </div>
      ))}
      <span className="fr-kicker" style={{ paddingTop: 8, textWrap: "pretty" }}>
        “Per event” reads due dates, exams (with prep), classes and other commitments from each event’s title; a kind reads every event as that kind. Turning a calendar off withdraws what it suggested that you haven’t answered; what you accepted stays.
      </span>
    </>
  )
}
