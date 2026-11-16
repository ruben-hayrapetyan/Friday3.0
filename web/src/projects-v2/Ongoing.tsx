// The Ongoing shelf: projects with hours a week and no deadline (commands/ongoing.py), each a card with eight weeks of
// days lit where you worked on it, this week's hours against its budget. Opened, its detail: this week
// (budget, what carried in, done, still planned), week by week, and its options, each saying what it's set to now.

import { type QueryClient, useQuery } from "@tanstack/react-query"
import { useState } from "react"
import { query } from "@/api/client"
import { H, Icon, Seg } from "@/components/fr/controls"
import { useCommand } from "@/hooks/useCommand"
import { dur, weekday } from "@/lib/format"
import { addDays } from "@/lib/time"
import { useLook } from "@/theme/LookProvider"
import { behindRhythm, CARRIES, gridDays, hoursText, type Ongoing, PRIORITIES, rhythmWords, touchedWords } from "./model"

export const ONGOING_KEY = ["ongoing_projects"] as const
export const useOngoing = () => useQuery({ queryKey: ONGOING_KEY, queryFn: () => query("ongoing_projects") })

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
/** "Mon 9", with its month when it isn't this one: "Fri 4 Dec". */
export const dayText = (date: string, today: string) => `${weekday(date)} ${Number(date.slice(8, 10))}${date.slice(0, 7) !== today.slice(0, 7) ? ` ${MONTHS[Number(date.slice(5, 7)) - 1]}` : ""}`

/** An ongoing project changed on screen at once, before the server answers (rolled back if it refuses). */
export function changedOngoing(client: QueryClient, id: number, change: Partial<Ongoing>): void {
  client.setQueryData<Ongoing[]>(ONGOING_KEY, (list) => list?.map((o) => (o.id === id ? { ...o, ...change } : o)))
}

function Bar({ share, planned, color }: { share: number; planned: number; color: string }) {
  return (
    <span style={{ display: "flex", height: 6, borderRadius: 3, overflow: "hidden", background: "color-mix(in srgb, var(--color-text) 8%, transparent)" }}>
      <span style={{ width: `${Math.min(100, share * 100)}%`, background: color }} />
      <span style={{ width: `${Math.max(0, Math.min(100 - share * 100, planned * 100))}%`, background: `color-mix(in srgb, ${color} 35%, transparent)` }} />
    </span>
  )
}

/** Eight weeks of days, Monday on top: lit where you worked on it. */
export function Days({ touched, today, tint }: { touched: string[]; today: string; tint: string }) {
  return (
    <span role="img" aria-label={`Worked on ${touched.length} of the last 56 days`} style={{ display: "grid", gridTemplateRows: "repeat(7, 10px)", gridAutoFlow: "column", gridAutoColumns: "10px", gap: 3, flex: "none" }} title="The last eight weeks, Monday on top">
      {gridDays(today).map((d) => (
        <span key={d} style={{ width: 10, height: 10, borderRadius: 3, opacity: d > today ? 0 : 1, background: touched.includes(d) ? tint : "color-mix(in srgb, var(--color-text) 9%, transparent)", outline: d === today ? "1px solid var(--color-neutral-400)" : undefined, outlineOffset: 1 }} />
      ))}
    </span>
  )
}

export function OngoingShelf({ ongoing, today, opened, onOpen }: { ongoing: Ongoing[]; today: string; opened: number | null; onOpen: (id: number) => void }) {
  const { color } = useLook()
  return (
    <section aria-label="Ongoing" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <span style={{ display: "flex", gap: 10, alignItems: "baseline", flexWrap: "wrap" }}>
        <H size={20}>Ongoing</H>
        <span className="fr-kicker">hours a week, no deadline · eight weeks of days</span>
      </span>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(min(100%, 300px), 1fr))", gap: 10 }}>
        {ongoing.map((o) => {
          const tint = color(o.area, "Goal")
          const w = o.week
          const paused = !o.active
          return (
            <div
              key={o.id}
              role="button"
              tabIndex={0}
              aria-label={o.title}
              className="fr-well fr-hover"
              onClick={() => onOpen(o.id)}
              onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && e.target === e.currentTarget && (e.preventDefault(), onOpen(o.id))}
              style={{ display: "flex", flexDirection: "column", gap: 12, padding: "14px 16px", borderRadius: "var(--radius-lg)", cursor: "pointer", opacity: paused ? 0.6 : 1, boxShadow: opened === o.id ? "inset 0 0 0 1.5px var(--color-accent)" : undefined }}
            >
              <span style={{ display: "flex", gap: 10, alignItems: "center", minWidth: 0 }}>
                <span style={{ width: 10, height: 10, borderRadius: 3, background: tint, flex: "none" }} />
                <span style={{ fontWeight: 600, flex: 1, minWidth: 0, overflowWrap: "anywhere" }}>{o.title}</span>
              </span>
              <span style={{ display: "flex", gap: 16, alignItems: "flex-end", flexWrap: "wrap" }}>
                <Days touched={o.touched} today={today} tint={tint} />
                <span style={{ display: "flex", flexDirection: "column", gap: 4, flex: 1, minWidth: 140 }}>
                  <span style={{ fontSize: 12, color: !paused && behindRhythm(o, today) ? "var(--fr-warn)" : "var(--color-neutral-400)" }}>
                    {touchedWords(o, today, (d) => dayText(d, today))}
                    {!paused && o.rhythm_days ? ` · ${o.rhythm_days} ${o.rhythm_days === 1 ? "day" : "days"} a week` : ""}
                  </span>
                  {w && <Bar share={w.target_min ? w.done_min / w.target_min : 0} planned={w.target_min ? w.planned_min / w.target_min : 0} color={tint} />}
                  <span className="tnum fr-kicker">
                    {w ? `${dur(w.done_min) || "0m"} of ${dur(w.target_min)} this week${w.carried_min ? ` · ${dur(w.carried_min)} carried` : ""}` : `${hoursText(o.hours_per_week)} a week`}
                  </span>
                </span>
              </span>
            </div>
          )
        })}
      </div>
      {!ongoing.length && <span className="fr-kicker">No ongoing projects. Add one from the box above with hours a week, like “Guitar 3h a week”.</span>}
    </section>
  )
}

/** One ongoing project, opened beside the page. */
export function OngoingDetail({ o, today, onDeleted }: { o: Ongoing; today: string; onDeleted: () => void }) {
  const { color } = useLook()
  const set = useCommand("ongoing_set", { label: () => `${o.title}: saved; Friday plans its weeks again`, optimistic: (client, input) => changedOngoing(client, input.id, shown(input)) })
  const stop = useCommand("series_stop", { label: () => `${o.title} paused`, optimistic: (client) => changedOngoing(client, o.id, { active: false, week: null }) })
  const remove = useCommand("ongoing_delete", { label: (out) => out.result.message, optimistic: (client) => client.setQueryData<Ongoing[]>(ONGOING_KEY, (list) => list?.filter((x) => x.id !== o.id)) })
  const [sure, setSure] = useState(false)
  const [hours, setHours] = useState(String(o.hours_per_week))
  const tint = color(o.area, "Goal")
  const w = o.week
  const weeks = [...o.past, ...(w ? [w] : [])]
  const most = Math.max(1, ...weeks.map((x) => Math.max(x.target_min, x.done_min)))
  const saveHours = () => {
    const h = Number(hours)
    if (h > 0 && h <= 60 && h !== o.hours_per_week) set({ id: o.id, hours_per_week: h })
    else setHours(String(o.hours_per_week))
  }
  const carry = CARRIES.find((c) => c.value === o.carry) ?? CARRIES[1]
  const aim = o.aim_min - Math.round(o.hours_per_week * 60)
  const paused = !o.active
  return (
    <div style={{ minHeight: 0, padding: "8px 0 0", display: "flex", flexDirection: "column", gap: 24, maxWidth: 760, minWidth: 0 }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        <span className="fr-eyebrow" style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <span style={{ width: 10, height: 10, borderRadius: 3, background: tint }} />
          {o.area ?? "No tag"}, ongoing · {hoursText(o.hours_per_week)} a week
        </span>
        <H size={32} style={{ overflowWrap: "anywhere", paddingRight: 40 }}>
          {o.title}
        </H>
        <span style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap", paddingTop: 6 }}>
          {paused ? (
            <>
              <span style={{ fontSize: 12, color: "var(--color-neutral-400)" }}>{o.paused_until ? `Paused until ${dayText(o.paused_until, today)}` : "Paused"}</span>
              <button className="btn btn-secondary" onClick={() => set({ id: o.id, paused_until: "" })} style={{ fontSize: 12, padding: "4px 10px" }}>
                <Icon name="play" size={13} /> Resume
              </button>
            </>
          ) : (
            <>
              <button className="btn btn-secondary" onClick={() => stop({ id: o.id })} title="Pause it until you resume it" style={{ fontSize: 12, padding: "4px 10px" }}>
                <Icon name="pause" size={13} /> Pause
              </button>
              <span style={{ fontSize: 12, color: "var(--color-neutral-400)" }}>or until</span>
              {(
                [
                  ["Next week", addDays(today, ((8 - new Date(`${today}T00:00Z`).getUTCDay()) % 7) || 7)],
                  ["In two weeks", addDays(today, 14)],
                  ["In a month", addDays(today, 30)],
                ] as const
              ).map(([label, date]) => (
                <button key={label} className="btn btn-ghost" onClick={() => set({ id: o.id, paused_until: date })} title={`Paused until ${dayText(date, today)}; it comes back that morning`} style={{ fontSize: 12, padding: "4px 8px" }}>
                  {label} <span className="tnum" style={{ color: "var(--color-neutral-400)" }}>{dayText(date, today)}</span>
                </button>
              ))}
            </>
          )}
          <span style={{ flex: 1 }} />
          {sure ? (
            <span style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
              <span style={{ fontSize: 12 }}>Its weeks to come go; the hours you put in stay in your history.</span>
              <button className="btn btn-secondary" onClick={() => (setSure(false), onDeleted(), remove({ id: o.id }))} style={{ fontSize: 12, padding: "4px 10px", color: "var(--fr-due)" }}>
                Delete it
              </button>
              <button className="btn btn-ghost" onClick={() => setSure(false)} style={{ fontSize: 12, padding: "4px 10px" }}>
                Keep it
              </button>
            </span>
          ) : (
            <button className="btn btn-ghost" onClick={() => setSure(true)} style={{ fontSize: 12, padding: "4px 10px" }}>
              <Icon name="trash" size={13} /> Delete
            </button>
          )}
        </span>
      </div>
      {w && (
        <div className="fr-well" style={{ display: "flex", flexDirection: "column", gap: 10, padding: "14px 16px" }}>
          <span style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 8 }}>
            <span style={{ fontWeight: 500 }}>This week</span>
            <span className="tnum" style={{ fontSize: 13 }}>
              {dur(w.done_min) || "0m"} of {dur(w.target_min)}
            </span>
          </span>
          <Bar share={w.target_min ? w.done_min / w.target_min : 0} planned={w.target_min ? w.planned_min / w.target_min : 0} color={tint} />
          <span className="fr-kicker">
            {[w.planned_min ? `${dur(w.planned_min)} more planned` : "Nothing more planned yet", w.carried_min ? `${dur(w.carried_min)} carried from a short last week` : "", `until ${dayText(w.end.slice(0, 10), today)}`].filter(Boolean).join(" · ")}
          </span>
        </div>
      )}
      {weeks.length > 1 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <span className="fr-kicker">Week by week: done, against each week's hours (the dashed line)</span>
          <div style={{ display: "flex", gap: 10, alignItems: "flex-end", height: 90 }}>
            {weeks.map((x) => (
              <span key={x.start} title={`Week of ${dayText(x.start.slice(0, 10), today)}: ${dur(x.done_min) || "0m"} of ${dur(x.target_min)}`} style={{ flex: 1, maxWidth: 48, display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}>
                <span style={{ position: "relative", width: "100%", height: 70, display: "flex", alignItems: "flex-end" }}>
                  <span style={{ position: "absolute", left: 0, right: 0, bottom: `${(x.target_min / most) * 100}%`, borderTop: "1px dashed var(--color-neutral-500)" }} />
                  <span style={{ width: "100%", height: `${(x.done_min / most) * 100}%`, minHeight: 2, borderRadius: "3px 3px 0 0", background: x.done_min >= x.target_min ? tint : `color-mix(in srgb, ${tint} 55%, transparent)` }} />
                </span>
                <span className="tnum" style={{ fontSize: 11, color: "var(--color-neutral-400)" }}>
                  {Number(x.start.slice(5, 7))}/{Number(x.start.slice(8, 10))}
                </span>
              </span>
            ))}
          </div>
        </div>
      )}
      <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
        <Option label="Hours a week" value={hoursText(o.hours_per_week)}>
          <span style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <input className="input tnum" type="number" min={0.25} max={60} step={0.25} value={hours} onChange={(e) => setHours(e.target.value)} onBlur={saveHours} onKeyDown={(e) => e.key === "Enter" && saveHours()} aria-label="Hours a week" style={{ width: 90 }} />
            <span className="fr-kicker">hours, from this week on</span>
          </span>
        </Option>
        <Option label="When a week falls short" value={`${carry.label}: ${carry.desc}`}>
          <Seg options={CARRIES.map((c) => ({ value: c.value, label: c.label }))} value={carry.value} onPick={(v) => set({ id: o.id, carry: v })} size="small" label="When a week falls short" />
        </Option>
        <Option label="Rhythm" value={rhythmWords(o.hours_per_week, o.rhythm_days ?? 0)}>
          <Seg options={[0, 1, 2, 3, 4, 5, 6, 7].map((d) => ({ value: d, label: d ? String(d) : "Any" }))} value={o.rhythm_days ?? 0} onPick={(v) => set({ id: o.id, rhythm_days: v })} size="small" label="Days a week" />
        </Option>
        <Option label="Priority" value={`${PRIORITIES[o.priority - 1]}: ${dur(o.aim_min) || "nothing"} this week at your pace${aim > 0 ? `, ${dur(aim)} more` : aim < 0 ? `, ${dur(-aim)} less` : ""}`}>
          <Seg options={PRIORITIES.map((p, i) => ({ value: i + 1, label: p }))} value={o.priority} onPick={(v) => set({ id: o.id, priority: v })} size="small" label="Priority" />
          <span className="fr-kicker" style={{ textWrap: "pretty" }}>
            A busier pace adds to every week's hours and an easier one takes some off; a higher priority takes more of what's added and gives up less of what's taken.
          </span>
        </Option>
      </div>
    </div>
  )
}

/** What a change looks like on screen before the server answers. */
function shown(input: { hours_per_week?: number | null; carry?: number | null; rhythm_days?: number | null; priority?: number | null; paused_until?: string | null }): Partial<Ongoing> {
  const out: Partial<Ongoing> = {}
  if (input.hours_per_week != null) out.hours_per_week = input.hours_per_week
  if (input.carry != null) out.carry = input.carry
  if (input.rhythm_days != null) out.rhythm_days = input.rhythm_days || null
  if (input.priority != null) out.priority = input.priority
  if (input.paused_until === "") Object.assign(out, { active: true, paused_until: null })
  else if (input.paused_until) Object.assign(out, { active: false, paused_until: input.paused_until, week: null })
  return out
}

function Option({ label, value, children }: { label: string; value: string; children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <span style={{ display: "flex", flexDirection: "column", gap: 2 }}>
        <span style={{ fontWeight: 500, fontSize: 13 }}>{label}</span>
        <span style={{ fontSize: 12, color: "var(--color-neutral-300)", textWrap: "pretty" }}>{value}</span>
      </span>
      {children}
    </div>
  )
}
