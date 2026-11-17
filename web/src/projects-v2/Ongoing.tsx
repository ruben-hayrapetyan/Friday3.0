// The Ongoing shelf: projects with hours a week and no deadline (commands/ongoing.py), each a card with eight weeks of
// days lit where you worked on it, this week's hours against its budget. Opened, its detail: this week
// (budget, what carried in, done, still planned), week by week, and its options, each saying what it's set to now.

import { type QueryClient, useQuery } from "@tanstack/react-query"
import { useState } from "react"
import { query } from "@/api/client"
import { Chip, H, Icon } from "@/components/fr/controls"
import { useAreas } from "@/hooks/queries"
import { useCommand } from "@/hooks/useCommand"
import { dur, weekday } from "@/lib/format"
import { addDays } from "@/lib/time"
import { useLook } from "@/theme/LookProvider"
import { LengthInput } from "@/todo/Pickers"
import { Choices, Rows, SettingRow } from "./Rows"
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
      {!ongoing.length && <span className="fr-kicker">No ongoing projects. New ongoing adds one: hours a week for something with no deadline, like an instrument.</span>}
    </section>
  )
}

/** One ongoing project, in the side panel: this week, week by week, and its settings as rows. */
export function OngoingDetail({ o, today, onDeleted }: { o: Ongoing; today: string; onDeleted: () => void }) {
  const { color } = useLook()
  const set = useCommand("ongoing_set", { label: () => `${o.title}: saved; Friday plans its weeks again`, optimistic: (client, input) => changedOngoing(client, input.id, shown(input)) })
  const remove = useCommand("ongoing_delete", { label: (out) => out.result.message, optimistic: (client) => client.setQueryData<Ongoing[]>(ONGOING_KEY, (list) => list?.filter((x) => x.id !== o.id)) })
  const [open, setOpen] = useState<"tag" | "hours" | "days" | "priority" | "pause" | "carry" | null>(null)
  const tags = (useAreas().data ?? []).filter((a) => !a.archived).map((a) => a.name)
  const [newTag, setNewTag] = useState("")
  const toggle = (k: typeof open) => setOpen(open === k ? null : k)
  const [sure, setSure] = useState(false)
  const [until, setUntil] = useState("")
  const tint = color(o.area, "Goal")
  const w = o.week
  const weeks = [...o.past, ...(w ? [w] : [])]
  const most = Math.max(1, ...weeks.map((x) => Math.max(x.target_min, x.done_min)))
  const carry = CARRIES.find((c) => c.value === o.carry) ?? CARRIES[1]
  const aim = o.aim_min - Math.round(o.hours_per_week * 60)
  const days = o.rhythm_days ?? 0
  const monday = addDays(today, ((8 - new Date(`${today}T00:00Z`).getUTCDay()) % 7) || 7)
  const tomorrow = addDays(today, 1)
  const pausedWords = o.paused_until ? `Until ${dayText(o.paused_until, today)}` : !o.active ? "Until you resume it" : "No"
  const pick = <T,>(then: (v: T) => void) => (v: T) => (then(v), setOpen(null))
  return (
    <>
      <div style={{ display: "flex", flexDirection: "column", gap: 6, paddingRight: 36 }}>
        <span className="fr-eyebrow" style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <span style={{ width: 10, height: 10, borderRadius: 3, background: tint }} />
          {o.area ?? "No tag"} · ongoing
        </span>
        <H size={26} style={{ overflowWrap: "anywhere" }}>
          {o.title}
        </H>
        {o.as_before && (
          <span className="fr-kicker" style={{ textWrap: "pretty" }}>
            A weekly goal from before ongoing projects: its weeks plan as they always have. Change a setting below and it plans as an ongoing project, its priority counting and a short week carrying over as that row says.
          </span>
        )}
      </div>
      {w ? (
        <div className="fr-well" style={{ display: "flex", flexDirection: "column", gap: 8, padding: "12px 14px" }}>
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
      ) : (
        <span className="fr-kicker">{pausedWords === "No" ? "Its first week starts soon." : `Paused ${pausedWords.toLowerCase()}: no time is planned for it.`}</span>
      )}
      <Rows>
        {/* a client: "can't add a tag on projects of type ongoing" */}
        <SettingRow label="Tag" value={o.area ?? "No tag"} open={open === "tag"} onToggle={() => toggle("tag")} note="Its color, and what it counts toward">
          <Choices label="Tag" value={o.area ?? null} onPick={pick((t: string | null) => t !== (o.area ?? null) && set({ id: o.id, area: t ?? "" }))} options={[{ value: null as string | null, label: "No tag" }, ...[...new Set([...tags, ...(o.area ? [o.area] : [])])].map((t) => ({ value: t as string | null, label: t }))]} />
          <label style={{ display: "flex", gap: 8, alignItems: "center", padding: "6px 8px", fontSize: 12, color: "var(--color-neutral-300)" }}>
            Or a new one
            <input className="input" value={newTag} onChange={(e) => setNewTag(e.target.value)} onKeyDown={(e) => e.key === "Enter" && newTag.trim() && (set({ id: o.id, area: newTag.trim() }), setNewTag(""), setOpen(null))} placeholder="A tag's name, then Enter" aria-label="A new tag" style={{ padding: "2px 6px", minHeight: 0, fontSize: 12, width: 180 }} />
          </label>
        </SettingRow>
        <SettingRow label="Hours a week" value={`${hoursText(o.hours_per_week)} a week`} open={open === "hours"} onToggle={() => toggle("hours")} note={aim ? `${dur(o.aim_min)} this week at your pace` : undefined}>
          <LengthPicks value={Math.round(o.hours_per_week * 60)} amounts={[60, 120, 180, 300, 480, 600]} label="Hours a week" onPick={pick((m: number) => m !== Math.round(o.hours_per_week * 60) && set({ id: o.id, hours_per_week: m / 60 }))} />
        </SettingRow>
        <SettingRow label="Days a week" value={rhythmWords(o.hours_per_week, days)} open={open === "days"} onToggle={() => toggle("days")}>
          <Choices
            label="Days a week"
            value={days}
            onPick={pick((d: number) => d !== days && set({ id: o.id, rhythm_days: d }))}
            options={[0, 1, 2, 3, 4, 5, 7].map((d) => ({ value: d, label: d === 0 ? "Any day" : d === 7 ? "Every day" : `${d} ${d === 1 ? "day" : "days"} a week`, desc: d ? `About ${dur(Math.round((o.hours_per_week * 60) / d))} each time, on different days` : "Whenever it fits, some days more" }))}
          />
        </SettingRow>
        <SettingRow label="Priority" value={PRIORITIES[o.priority - 1]} open={open === "priority"} onToggle={() => toggle("priority")} note="How much of a busier or easier pace it takes on">
          <Choices
            label="Priority"
            value={o.priority}
            onPick={pick((p: number) => p !== o.priority && set({ id: o.id, priority: p }))}
            options={[
              { value: 5, label: "Highest", desc: "Gets the most extra time when you push, and keeps its hours when you ease off" },
              { value: 4, label: "High", desc: "More of the extra when you push; gives up little when you ease off" },
              { value: 3, label: "Normal", desc: "Grows and shrinks with your pace, like everything else" },
              { value: 2, label: "Low", desc: "Little of the extra when you push; gives way first when you ease off" },
              { value: 1, label: "Lowest", desc: "Stays near its hours when you push; mostly waits when you ease off" },
            ]}
          />
        </SettingRow>
        <SettingRow label="Paused" value={pausedWords} open={open === "pause"} onToggle={() => toggle("pause")}>
          <Choices
            label="Paused"
            value={o.paused_until ? "date" : o.active ? "no" : "resume"}
            onPick={pick((v: string) => (v === "no" ? (!o.active || o.paused_until) && set({ id: o.id, paused_until: "" }) : v === "resume" ? o.active && set({ id: o.id, paused_until: "resume" }) : v !== "date" && set({ id: o.id, paused_until: v })))}
            options={[
              { value: "no", label: "No", desc: "Friday plans its hours every week" },
              { value: "resume", label: "Until I resume it", desc: "No time planned until you set this back to No" },
              { value: monday, label: `Until next week, ${dayText(monday, today)}`, desc: "It comes back that morning" },
              { value: addDays(today, 14), label: `For two weeks, until ${dayText(addDays(today, 14), today)}`, desc: "It comes back that morning" },
              { value: addDays(today, 30), label: `For a month, until ${dayText(addDays(today, 30), today)}`, desc: "It comes back that morning" },
            ]}
          />
          <label style={{ display: "flex", gap: 8, alignItems: "center", padding: "6px 8px", fontSize: 12, color: "var(--color-neutral-300)" }}>
            Or until
            {/* a date before tomorrow is a year still being typed, not a pause */}
            <input type="date" className="input" min={tomorrow} value={until} onChange={(e) => (setUntil(e.target.value), e.target.value >= tomorrow && (set({ id: o.id, paused_until: e.target.value }), setOpen(null)))} aria-label="Paused until a date" style={{ padding: "2px 6px", minHeight: 0, fontSize: 12, width: 140 }} />
          </label>
        </SettingRow>
        <SettingRow label="A short week" value={o.as_before ? `Each week starts fresh for now; once you change a setting here, ${carry.desc}` : `${carry.label}: ${carry.desc}`} open={open === "carry"} onToggle={() => toggle("carry")}>
          <Choices
            label="A short week"
            value={carry.value as number}
            onPick={pick((c: number) => c !== o.carry && set({ id: o.id, carry: c }))}
            options={CARRIES.map((c) => ({ value: c.value as number, label: c.label === "None" ? "Start each week fresh" : c.label === "Half" ? "Carry half" : "Carry all", desc: c.desc[0].toUpperCase() + c.desc.slice(1) }))}
          />
        </SettingRow>
      </Rows>
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
      <span style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
        {sure ? (
          <>
            <span style={{ fontSize: 12 }}>Its weeks to come go; the hours you put in stay in your history.</span>
            <button className="btn btn-secondary" onClick={() => (setSure(false), onDeleted(), remove({ id: o.id }))} style={{ fontSize: 12, padding: "4px 10px", color: "var(--fr-due)" }}>
              Delete it
            </button>
            <button className="btn btn-ghost" onClick={() => setSure(false)} style={{ fontSize: 12, padding: "4px 10px" }}>
              Keep it
            </button>
          </>
        ) : (
          <button className="btn btn-ghost" onClick={() => setSure(true)} style={{ fontSize: 12, padding: "4px 10px" }}>
            <Icon name="trash" size={13} /> Delete
          </button>
        )}
      </span>
    </>
  )
}

/** Common amounts and a box to type any: a length's choices inside a row. */
export function LengthPicks({ value, amounts, label, onPick }: { value: number; amounts: number[]; label: string; onPick: (minutes: number) => void }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
        {amounts.map((m) => (
          <Chip key={m} on={value === m} onClick={() => onPick(m)}>
            {dur(m)}
          </Chip>
        ))}
      </div>
      <label style={{ display: "flex", alignItems: "flex-start", gap: 8, fontSize: 12, color: "var(--color-neutral-300)" }}>
        <span style={{ paddingTop: 5, flex: "none" }}>Or type</span>
        <LengthInput value={null} onPick={(m) => m && m >= 15 && onPick(m)} width={150} label={`${label}, typed`} placeholder="e.g. 12h, 2.5 hours" />
      </label>
    </div>
  )
}

/** What a change looks like on screen before the server answers. */
function shown(input: { area?: string | null; hours_per_week?: number | null; carry?: number | null; rhythm_days?: number | null; priority?: number | null; paused_until?: string | null }): Partial<Ongoing> {
  const out: Partial<Ongoing> = {}
  if (input.area != null) out.area = input.area || null
  if (input.hours_per_week != null) out.hours_per_week = input.hours_per_week
  if (input.carry != null) out.carry = input.carry
  if (input.rhythm_days != null) out.rhythm_days = input.rhythm_days || null
  if (input.priority != null) out.priority = input.priority
  if (input.paused_until === "") Object.assign(out, { active: true, paused_until: null })
  else if (input.paused_until === "resume") Object.assign(out, { active: false, paused_until: null, week: null })
  else if (input.paused_until) Object.assign(out, { active: false, paused_until: input.paused_until, week: null })
  return { ...out, as_before: false } // a setting changed: an ongoing project from now on
}
