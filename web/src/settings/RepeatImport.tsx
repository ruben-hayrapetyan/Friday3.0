// The Google card atop Repeating (v22): repeating events found in your calendars, each to come in as one repeat
// with a tag and a kind you pick. "Not now" hides the card on this device until another repeating event turns up.

import { useQuery } from "@tanstack/react-query"
import { useState } from "react"
import { query, type Schemas } from "@/api/client"
import { Box, Icon, Menu } from "@/components/fr/controls"
import { useAreas, useSettings } from "@/hooks/queries"
import { useCommand } from "@/hooks/useCommand"

type Found = Schemas["RepeatFound"]
interface Pick {
  on: boolean
  area: string
  kind: string
}

const HIDDEN = "friday.repeats.notNow"
const COLUMNS = "18px minmax(0,1fr) auto auto 56px"

export const useCalendarRepeats = () => useQuery({ queryKey: ["calendar_repeats"], queryFn: () => query("calendar_repeats") })

function hiddenSet(): string {
  try {
    return localStorage.getItem(HIDDEN) ?? ""
  } catch {
    return "" // storage blocked: the card shows every time
  }
}

export function RepeatImport() {
  const found = useCalendarRepeats().data ?? []
  const [picks, setPicks] = useState<Record<string, Pick>>({})
  const [hidden, setHidden] = useState(hiddenSet)
  const run = useCommand("repeats_import", { label: (o) => o.result.message ?? "Imported" })
  const key = found.map((f) => f.batch).join(",")
  if (!found.length || hidden === key) return null
  const pickOf = (f: Found): Pick => picks[f.batch] ?? { on: true, area: f.tag ?? "", kind: f.kind }
  const chosen = found.filter((f) => pickOf(f).on)
  const notNow = () => {
    try {
      localStorage.setItem(HIDDEN, key)
    } catch {
      // storage blocked: hidden until the page reloads
    }
    setHidden(key)
  }
  const importChosen = () =>
    run({ repeats: chosen.map((f) => ({ batch: f.batch, area: pickOf(f).area || null, kind: pickOf(f).kind === f.kind ? null : pickOf(f).kind })) })
  return (
    <div className="fr-well" style={{ display: "flex", flexDirection: "column", gap: 4, padding: "16px 18px", marginBottom: 24, borderRadius: "var(--radius-lg)" }}>
      <div style={{ display: "flex", gap: 12, alignItems: "center", paddingBottom: 8 }}>
        <Icon name="google-logo" size={20} />
        <span style={{ flex: 1, display: "flex", flexDirection: "column", gap: 2 }}>
          <span style={{ fontWeight: 500 }}>
            {found.length} repeating {found.length === 1 ? "event" : "events"} in your Google calendars
          </span>
          <span style={{ fontSize: 12, color: "var(--color-neutral-500)" }}>Each series comes in as one repeat, not as separate events. Pick a tag and whether it’s fixed.</span>
        </span>
      </div>
      {found.map((f) => (
        <Line key={f.batch} found={f} pick={pickOf(f)} onChange={(p) => setPicks({ ...picks, [f.batch]: p })} />
      ))}
      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", paddingTop: 10 }}>
        <button className="btn btn-ghost" onClick={notNow}>
          Not now
        </button>
        <button className="btn btn-primary" onClick={importChosen} disabled={!chosen.length}>
          Import {chosen.length === found.length ? (found.length === 1 ? "it" : `all ${found.length}`) : chosen.length}
        </button>
      </div>
    </div>
  )
}

function Line({ found, pick, onChange }: { found: Found; pick: Pick; onChange: (p: Pick) => void }) {
  const known = (useAreas().data ?? []).map((a) => a.name)
  const areas = found.tag && !known.includes(found.tag) ? [...known, found.tag] : known // a course's own tag, new until imported
  const presets = (useSettings().data as { presets?: Record<string, { when?: string }> } | undefined)?.presets ?? {}
  const fixed = presets[found.kind]?.when === "fixed"
  const kinds = Object.keys(presets).filter((k) => (presets[k].when === "fixed") === fixed)
  return (
    <div className="fr-row" style={{ display: "grid", gridTemplateColumns: COLUMNS, gap: 12, alignItems: "center", padding: "8px 0", opacity: pick.on ? 1 : 0.55 }}>
      <button className="fr-plain" onClick={() => onChange({ ...pick, on: !pick.on })} aria-label={`Include ${found.title}`}>
        <Box on={pick.on} />
      </button>
      <span style={{ display: "flex", flexDirection: "column", gap: 1, minWidth: 0 }}>
        <span style={{ fontWeight: 500, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{found.title}</span>
        <span className="fr-kicker" style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
          {found.pattern} · {found.calendar}
        </span>
      </span>
      <Menu options={[{ value: "", label: "No tag" }, ...areas.map((a) => ({ value: a, label: a }))]} value={pick.area} onPick={(area) => onChange({ ...pick, area })} label={`Tag for ${found.title}`} disabled={!pick.on} />
      <Menu options={kinds.map((k) => ({ value: k, label: k }))} value={pick.kind} onPick={(kind) => onChange({ ...pick, kind })} label={`Kind for ${found.title}`} disabled={!pick.on} />
      <span className="tnum fr-kicker" style={{ textAlign: "right" }}>
        {found.count}×
      </span>
    </div>
  )
}
