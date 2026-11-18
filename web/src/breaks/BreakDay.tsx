// A break day's list, beside the calendar as the to-do drawer is (18 Nov: "open like a different version of todo"):
// what to get done that day to stay on track, by name, no times ("make it about tasks"). Tick one off, or time it
// ("i really liked the timer"): what you time shows on the calendar where you worked. What's left moves on.

import { type QueryClient, useQuery } from "@tanstack/react-query"
import { query, type Schemas } from "@/api/client"
import { Check, H, Icon } from "@/components/fr/controls"
import { useStatus } from "@/hooks/queries"
import { useElapsed } from "@/hooks/useClock"
import { useCommand } from "@/hooks/useCommand"
import { dur, hms } from "@/lib/format"
import { useShell } from "@/shell/ShellContext"
import { useLook } from "@/theme/LookProvider"
import { DrawerFrame } from "@/todo/Drawer"
import { dayWords, things } from "./words"

type DayOut = Schemas["VacationDayOut"]
type Thing = Schemas["VacationThing"]

export const dayKey = (date: string) => ["vacation_day", date] as const

export const useBreakDay = (date: string | null) =>
  useQuery({ queryKey: dayKey(date ?? ""), queryFn: () => query("vacation_day", { date: date ?? "" }), enabled: !!date })

/** A tick shows at once (UI-PRINCIPLES: 1/10 s): on the day's list and on its line on the calendar. */
export function tickedNow(client: QueryClient, input: { date: string; item_id: number; ticked?: boolean }): void {
  const ticked = input.ticked ?? true
  let moved = 0
  client.setQueryData<DayOut>(dayKey(input.date), (day) => {
    if (!day) return day
    const items = day.items.map((t) => (t.item_id === input.item_id && t.ticked !== ticked ? ((moved = ticked ? 1 : -1), { ...t, ticked }) : t))
    return { ...day, items, vacation: day.vacation && { ...day.vacation, ticked: (day.vacation.ticked ?? 0) + moved } }
  })
  client.setQueriesData<Schemas["CalendarOut"]>({ queryKey: ["calendar"] }, (cal) =>
    cal && { ...cal, days: cal.days.map((d) => (d.date === input.date && d.vacation ? { ...d, vacation: { ...d.vacation, ticked: Math.max(0, (d.vacation.ticked ?? 0) + (moved || (ticked ? 1 : -1))) } } : d)) },
  )
}

export function BreakDay({ date }: { date: string }) {
  const { setBreakDay, setBreakEdit, today } = useShell()
  const day = useBreakDay(date).data
  const v = day?.vacation
  const items = day?.items ?? []
  const done = items.filter((t) => t.ticked).length
  return (
    <DrawerFrame>
      <div style={{ display: "flex", alignItems: "center", gap: 8, minHeight: 32 }}>
        <span className="fr-kicker" style={{ color: "var(--fr-break)", flex: 1, minWidth: 0, overflowWrap: "anywhere" }}>
          {v ? `${v.name} · day ${v.day_n} of ${v.days}` : "Not on a break"}
        </span>
        {v && (
          <button className="btn btn-ghost" onClick={() => setBreakEdit({ id: v.id })} style={{ fontSize: 12.5, color: "var(--color-neutral-300)" }}>
            Break settings
          </button>
        )}
        <button className="btn btn-icon btn-ghost" onClick={() => setBreakDay(null)} aria-label="Close" style={{ width: 28, height: 28, color: "var(--color-neutral-400)" }}>
          <Icon name="x" />
        </button>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <H size={24}>{date === today ? `Today, ${dayWords(date)}` : dayWords(date)}</H>
        <span style={{ fontSize: 12.5, color: "var(--color-neutral-400)" }}>
          {!v ? "" : v.mode === "off" ? "Off: nothing to do" : items.length ? `${done} of ${things(items.length)} done · whenever suits, no set times` : "Nothing to do today"}
        </span>
        {v && items.length > 0 && (
          <span className="fr-break-bar" aria-hidden style={{ flex: "none", marginTop: 4 }}>
            <span style={{ width: `${Math.round((done / items.length) * 100)}%` }} />
          </span>
        )}
      </div>
      <div style={{ overflowY: "auto", minHeight: 0, flex: 1, display: "flex", flexDirection: "column", gap: 2, paddingBottom: 24 }}>
        {v && items.length > 0 && (
          <span className="fr-kicker" style={{ display: "flex", justifyContent: "space-between", margin: "6px 4px 4px" }}>
            <span>To stay on track</span>
            <span className="tnum">{items.length - done} left</span>
          </span>
        )}
        {items.map((t) => (
          <Row key={t.item_id} date={date} thing={t} />
        ))}
        {v && v.mode !== "off" && (
          <span style={{ fontSize: 12, color: "var(--color-neutral-500)", padding: "12px 4px", textWrap: "pretty" }}>
            {date === today ? "Not done today? It moves to tomorrow, and the rest of the break evens out." : date < today ? "What wasn't ticked off moved on to the days after." : "Any time that day."}
          </span>
        )}
      </div>
    </DrawerFrame>
  )
}

function Row({ date, thing }: { date: string; thing: Thing }) {
  const { color } = useLook()
  const tick = useCommand("vacation_tick", { optimistic: tickedNow, label: (o) => o.result.message })
  const status = useStatus().data
  const running = [status?.timer, ...(status?.alongside ?? [])].find((t) => t?.item_id === thing.item_id)
  const elapsed = useElapsed(running?.elapsed_s)
  const start = useCommand("start", { label: () => `Timing ${thing.title}` })
  const stop = useCommand("stop", { label: () => `${thing.title}: timer stopped` })
  const worked = thing.timed_min + (running ? Math.floor(elapsed / 60) : 0)
  return (
    <div className="fr-hover" style={{ display: "grid", gridTemplateColumns: "16px 3px minmax(0,1fr) auto", gap: 9, alignItems: "center", padding: "7px 4px", borderRadius: "var(--radius-md)" }}>
      <Check small done={thing.ticked} onToggle={() => tick({ date, item_id: thing.item_id, ticked: !thing.ticked })} />
      <span style={{ alignSelf: "stretch", borderRadius: 2, background: color(thing.area, thing.preset) }} />
      <span style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
        <span style={{ fontWeight: 500, overflowWrap: "anywhere", ...(thing.ticked ? { textDecoration: "line-through", color: "var(--color-neutral-500)" } : {}) }}>{thing.title}</span>
        <span className="tnum" style={{ fontSize: 11, color: "var(--color-neutral-500)" }}>
          {[thing.area, worked && !running ? `worked ${dur(worked)}` : ""].filter(Boolean).join(" · ") || (thing.ticked ? "done" : "")}
        </span>
      </span>
      {!thing.ticked && !thing.done ? (
        <button
          className="btn btn-secondary tnum"
          aria-label={running ? `Stop timing ${thing.title}` : `Time ${thing.title}`}
          title={running ? "Stop the timer" : "Time it: it shows on the calendar where you worked"}
          onClick={() => (running ? stop({ id: thing.item_id }) : start({ id: thing.item_id, alongside: false }))}
          style={{ height: 26, padding: "0 10px", fontSize: 12, gap: 5, ...(running ? { color: "var(--fr-now)", boxShadow: "inset 0 0 0 1px var(--fr-now)" } : {}) }}
        >
          <Icon name={running ? "stop" : "play"} fill size={11} />
          {running ? hms(elapsed) : "Start"}
        </button>
      ) : (
        <span />
      )}
    </div>
  )
}
