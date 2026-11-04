// One question about a coming day (v22 Insights): two versions that finish the same work, drawn as mini day columns
// on one hour axis and painted as the calendar paints them: work in its area's colour, events in their pigment. What
// the versions place differently is outlined; what they share sits back.

import { useQuery } from "@tanstack/react-query"
import { type Item, query } from "@/api/client"
import { useCommand } from "@/hooks/useCommand"
import { useItems } from "@/hooks/queries"
import { clock, dayLabel, weekday } from "@/lib/format"
import { eventPaint, wash } from "@/lib/pigments"
import { addDays, layout, type Placed, toMin } from "@/lib/time"
import { useLook } from "@/theme/LookProvider"
import type { Skin } from "@/theme/skin"
import { Section } from "./Section"
import { elsewhere, moved, type Piece, spanOf, ticks } from "./shapes"

const PER_MIN = 40 / 60 // 40px an hour
const DAY_NAME: Record<string, string> = { Mon: "Monday", Tue: "Tuesday", Wed: "Wednesday", Thu: "Thursday", Fri: "Friday", Sat: "Saturday", Sun: "Sunday" }

interface Thing extends Piece {
  fixed: boolean
  changed?: boolean
}

export function Comparison() {
  const questions = useQuery({ queryKey: ["questions"], queryFn: () => query("questions") }).data
  const answer = useCommand("compare_answer", { label: (o) => o.result.message ?? "Thanks" })
  const q = questions?.comparisons[0]
  const day = q ? String(q.day) : ""
  // The question carries titles and times only: areas come from the items, an event's paint from the day's plan.
  const items = useItems().data
  const start = `${day}T00:00`
  const end = day ? `${addDays(day, 1)}T04:00` : ""
  const plan = useQuery({ queryKey: ["plan", start, end], queryFn: () => query("plan", { start, end }), enabled: !!q }).data
  if (!q) return null
  const a = q.a as unknown as Piece[]
  const b = q.b as unknown as Piece[]
  const fixed = ((q.fixed ?? []) as unknown as Omit<Piece, "item_id">[]).map((f, i) => ({ ...f, item_id: -1 - i, fixed: true }))
  const versions = [
    { letter: "A", mine: a, theirs: b },
    { letter: "B", mine: b, theirs: a },
  ]
  const { lo, hi } = spanOf([...a, ...b, ...fixed])
  const axis = { startMin: lo - toMin(day), endMin: hi - toMin(day) }
  const marks = ticks(lo, hi)
  const height = (hi - lo) * PER_MIN
  const areaOf = (id: number) => items?.find((i) => i.id === id)?.area ?? plan?.blocks.find((x) => x.item_id === id)?.area ?? null
  const eventOf = (f: Piece) => plan?.fixed.find((x) => x.title === f.title && x.start === f.start)
  const lines = (
    <div style={{ position: "absolute", inset: 0, pointerEvents: "none" }}>
      {marks.map((m) => (
        <div key={m.at} style={{ position: "absolute", left: 0, right: 0, top: (m.at - lo) * PER_MIN, height: 1, background: "color-mix(in srgb, var(--color-text) 6%, transparent)" }} />
      ))}
    </div>
  )
  const name = DAY_NAME[weekday(day)] ?? weekday(day)
  return (
    <Section title={`Which ${name} looks better?`} note={`Two ways to plan ${dayLabel(day)}. One quick question helps Friday learn what you prefer`}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 24, alignItems: "flex-start" }}>
        <div style={{ flex: "1 1 320px", maxWidth: 620, minWidth: 0, display: "grid", gridTemplateColumns: "38px minmax(0,1fr) minmax(0,1fr)", columnGap: 10, rowGap: 8 }}>
          <span />
          {versions.map((v) => (
            <span key={v.letter} style={{ display: "flex", alignItems: "baseline", gap: 8, minWidth: 0 }}>
              <span style={{ fontWeight: 500, whiteSpace: "nowrap", flex: "none" }}>Version {v.letter}</span>
              <span className="fr-kicker" style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                {moved(v.mine, v.theirs).size || "nothing"} moved
              </span>
            </span>
          ))}
          <div style={{ position: "relative", height }}>
            {marks.map((m) => (
              <span key={m.at} className="tnum" style={{ position: "absolute", right: 0, top: (m.at - lo) * PER_MIN, transform: "translateY(-50%)", fontSize: 11, color: "var(--color-neutral-500)", whiteSpace: "nowrap" }}>
                {m.label}
              </span>
            ))}
          </div>
          {versions.map((v) => {
            const changed = moved(v.mine, v.theirs)
            const things: Thing[] = [...fixed, ...v.mine.map((p) => ({ ...p, fixed: false, changed: changed.has(p) }))]
            return (
              <div key={v.letter} style={{ position: "relative", height, borderRadius: "var(--radius-md)", background: "var(--color-bg)", overflow: "hidden" }}>
                {lines}
                {layout(things, day, axis).map((p) =>
                  p.item.fixed ? (
                    <EventPiece key={`f${p.item.item_id}`} p={p} event={eventOf(p.item)} />
                  ) : (
                    <WorkPiece key={`${p.item.item_id}${p.item.start}`} p={p} area={areaOf(p.item.item_id)} changed={!!p.item.changed} other={elsewhere(p.item, v.theirs, clock)} />
                  ),
                )}
              </div>
            )
          })}
          <span />
          {versions.map((v) => (
            <button key={v.letter} className="btn btn-secondary" onClick={() => answer({ id: q.id, answer: v.letter.toLowerCase() as "a" | "b" })}>
              Pick {v.letter}
            </button>
          ))}
        </div>
        <div style={{ flex: "1 1 200px", display: "flex", flexDirection: "column", gap: 12, minWidth: 0 }}>
          <span style={{ color: "var(--color-neutral-300)", textWrap: "pretty" }}>Both finish the same work, placed differently around what can't move. Pick the day you'd rather have.</span>
          <Key />
          <button className="btn btn-ghost" onClick={() => answer({ id: q.id, answer: "skip" })} style={{ alignSelf: "flex-start" }}>
            Skip
          </button>
        </div>
      </div>
    </Section>
  )
}

/** What the three looks mean: work, an event, and work the versions place differently. */
function Key() {
  const { skinOf, light } = useLook()
  const work = skinOf("planned", null)
  const paint = eventPaint({}, light)
  const event = { bg: wash(paint, light), stripe: paint }
  const swatch = (s: Pick<Skin, "bg" | "stripe">, ring?: boolean) => (
    <span style={{ position: "relative", flex: "none", width: 22, height: 14, borderRadius: 4, overflow: "hidden", background: s.bg, boxShadow: ring ? "inset 0 0 0 1.5px var(--color-accent)" : "none" }}>
      <span style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: 3, background: s.stripe }} />
    </span>
  )
  const row = (icon: React.ReactNode, text: string) => (
    <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
      {icon}
      {text}
    </span>
  )
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6, fontSize: 12, color: "var(--color-neutral-400)" }}>
      {row(swatch(work), "Work, in its area's colour")}
      {row(swatch(event), "Classes and events, which stay put")}
      {row(swatch(work, true), "Placed differently in the other version")}
    </div>
  )
}

/** A piece's box on the mini column: under an hour, one line with the title and its time; longer, the range below. */
function Box({ p, s, title, ring, calm }: { p: Placed<Thing>; s: Pick<Skin, "bg" | "bd" | "fg" | "sub" | "stripe">; title: string; ring?: boolean; calm?: boolean }) {
  const it = p.item
  const h = Math.max(p.height * PER_MIN - 2, 12)
  const tall = p.height >= 60
  const share = 1 / p.columns
  return (
    <div
      title={title}
      style={{
        position: "absolute",
        top: p.top * PER_MIN,
        height: h,
        left: `calc(100% * ${p.column * share} + 4px)`,
        width: `calc(100% * ${share} - 8px)`,
        borderRadius: 5,
        background: s.bg,
        border: s.bd,
        color: s.fg,
        opacity: calm ? 0.78 : 1,
        boxShadow: ring ? "inset 0 0 0 1.5px var(--color-accent)" : "none",
        overflow: "hidden",
        fontSize: 11,
        ...(tall ? { padding: "3px 6px 3px 9px", lineHeight: 1.3 } : { padding: "0 6px 0 9px", lineHeight: `${h}px` }),
      }}
    >
      <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: 3, background: s.stripe }} />
      <div style={{ display: "flex", alignItems: "baseline", gap: 5, fontWeight: 500, whiteSpace: "nowrap", overflow: "hidden" }}>
        <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{it.title}</span>
        {!tall && (
          <span className="tnum" style={{ flex: "none", fontWeight: 400, color: s.sub }}>
            {clock(it.start)}
          </span>
        )}
      </div>
      {tall && (
        <div className="tnum" style={{ color: s.sub, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
          {clock(it.start)}–{clock(it.end)}
        </div>
      )}
    </div>
  )
}

function WorkPiece({ p, area, changed, other }: { p: Placed<Thing>; area: string | null; changed: boolean; other: string }) {
  const { skinOf } = useLook()
  const it = p.item
  const range = `${it.title} ${clock(it.start)}–${clock(it.end)}`
  return <Box p={p} s={skinOf("planned", area)} title={changed ? `${range} (${other})` : `${range}, the same in both`} ring={changed} calm={!changed} />
}

/** Painted as the calendar paints an event (plan/Pieces FixedBox): the event's paint as a wash with it on the spine,
 * the title in ink. */
function EventPiece({ p, event }: { p: Placed<Thing>; event: Item | undefined }) {
  const { skinOf, light } = useLook()
  const base = skinOf(event?.event_kind === "shove" ? "shove" : "fixed", event?.area)
  const paint = eventPaint(event ?? {}, light)
  const s = event?.event_kind === "shove" ? base : { ...base, bg: wash(paint, light), stripe: paint, fg: "var(--color-text)", sub: "var(--color-neutral-400)" }
  return <Box p={p} s={s} title={`${p.item.title} ${clock(p.item.start)}–${clock(p.item.end)}, fixed`} />
}
