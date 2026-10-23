// Insights (v22): the last few weeks in three numbers, how long things really take by kind (and whether Friday
// adjusts estimates for you), when you get things done, what Friday learned for you to approve, one comparison
// question, and the load ahead against what you can do.

import { useQuery } from "@tanstack/react-query"
import { useState } from "react"
import { query } from "@/api/client"
import { H, Icon, Seg, Switch } from "@/components/fr/controls"
import { useCommand } from "@/hooks/useCommand"
import { useLoad } from "@/hooks/queries"
import { clock, weekday } from "@/lib/format"
import { toMin } from "@/lib/time"
import { useLook } from "@/theme/LookProvider"
import { useShell } from "@/shell/ShellContext"
import { Learned } from "./Learned"

const RANGES = [
  { value: 2, label: "2 weeks" },
  { value: 4, label: "4 weeks" },
  { value: 12, label: "12 weeks" },
]
const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
const HOURS = Array.from({ length: 16 }, (_, i) => String(i + 8).padStart(2, "0"))

export function InsightsPage() {
  const [weeks, setWeeks] = useState(4)
  const data = useQuery({ queryKey: ["insights", weeks], queryFn: () => query("insights", { weeks }) }).data
  return (
    <>
      <div className="fr-page-head">
        <span className="fr-h fr-title">Insights</span>
        <Seg options={RANGES} value={weeks} onPick={setWeeks} />
        <div style={{ flex: 1 }} />
        <span className="fr-kicker fr-head-note" style={{ whiteSpace: "nowrap" }}>
          {data ? `Based on ${data.done} finished ${data.done === 1 ? "thing" : "things"}` : ""}
        </span>
      </div>
      <div className="fr-panel" style={{ overflowY: "auto" }}>
        {data && (
          <div className="fr-gutter" style={{ maxWidth: 1080, padding: "28px 40px 120px", display: "flex", flexDirection: "column", gap: 28 }}>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 28 }}>
              <Big big={String(data.done)} line={`things finished in ${data.weeks} weeks`} />
              <Big big={`${data.hours} h`} line="of work recorded" />
              <Big big={data.estimate_ratio ? `${data.estimate_ratio}×` : "—"} line={data.estimate_ratio ? "how long things take against the estimate" : "Finish a few things to compare with estimates"} />
            </div>
            <Section title="How long things really take" note="Actual time compared with the estimate, by kind">
              <Accuracy kinds={data.by_kind} />
            </Section>
            <Section title="When you get things done" note="Minutes worked, by hour" right={<Legend />}>
              <Heat heat={data.heat} />
              <span style={{ color: "var(--color-neutral-300)", textWrap: "pretty" }}>{data.best_hours ?? "Not enough recorded work yet to see a pattern."}</span>
            </Section>
            <Section title="What Friday learned" note="Suggestions from how you actually work. Nothing changes until you approve.">
              <Learned />
            </Section>
            <Comparison />
            <Section title="Load ahead" note="Planned hours per week against what you can do" right={<LoadLegend />}>
              <Load />
            </Section>
          </div>
        )}
      </div>
    </>
  )
}

function Big({ big, line }: { big: string; line: string }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <H size={40} style={{ fontVariantNumeric: "tabular-nums" }}>
        {big}
      </H>
      <span style={{ color: "var(--color-neutral-300)", textWrap: "pretty" }}>{line}</span>
    </div>
  )
}

export function Section({ title, note, right, children }: { title: string; note: string; right?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="fr-row" style={{ display: "flex", flexDirection: "column", gap: 14, paddingTop: 24 }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 12, flexWrap: "wrap" }}>
        <H size={20}>{title}</H>
        <span className="fr-kicker">{note}</span>
        <span style={{ flex: 1 }} />
        {right}
      </div>
      {children}
    </section>
  )
}

/** A ratio on a log scale: the middle is on estimate, either edge twice off. */
const place = (r: number) => Math.max(2, Math.min(98, 50 + Math.log2(r) * 48))

function Accuracy({ kinds }: { kinds: { kind: string; n: number; median: number; low: number; high: number }[] }) {
  const learning = useQuery({ queryKey: ["learning"], queryFn: () => query("learning") }).data
  const use = useCommand("learn_module", { label: (o) => o.result.message ?? "Saved" })
  const durations = learning?.durations as { in_use: boolean; n: number } | null | undefined
  return (
    <>
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {kinds.map((k) => {
          const from = place(k.low)
          const to = place(k.high)
          const fill = k.median > 1.15 ? "var(--fr-warn)" : k.median < 0.85 ? "var(--color-accent)" : "var(--color-neutral-400)"
          const label = Math.abs(k.median - 1) < 0.08 ? "On estimate" : k.median > 1 ? `${k.median}× as long` : `${Math.round((1 - k.median) * 100)}% quicker`
          return (
            <div key={k.kind} style={{ display: "grid", gridTemplateColumns: "120px minmax(0,1fr) 150px", gap: 16, alignItems: "center" }}>
              <span>{k.kind}</span>
              <div style={{ position: "relative", height: 22 }}>
                <div style={{ position: "absolute", left: "50%", top: -3, bottom: -3, width: 1, background: "var(--color-neutral-500)" }} />
                <div style={{ position: "absolute", top: 6, height: 10, borderRadius: 5, left: `${Math.min(from, to - 1)}%`, width: `${Math.max(2, to - from)}%`, background: fill }} />
              </div>
              <span className="tnum" style={{ fontSize: 12, color: fill === "var(--color-neutral-400)" ? "var(--color-neutral-400)" : fill, textAlign: "right" }}>
                {label} ({k.n})
              </span>
            </div>
          )
        })}
        {!kinds.length && <span className="fr-kicker">Nothing finished with an estimate yet.</span>}
        <div style={{ display: "grid", gridTemplateColumns: "120px minmax(0,1fr) 150px", gap: 16, fontSize: 11, color: "var(--color-neutral-500)" }}>
          <span />
          <span style={{ display: "flex", justifyContent: "space-between" }}>
            <span>Quicker</span>
            <span>On estimate</span>
            <span>Longer</span>
          </span>
          <span />
        </div>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 12px", borderRadius: "var(--radius-md)", background: "var(--color-bg)" }}>
        <Switch on={!!durations?.in_use} onToggle={() => use({ module: "durations", use: !durations?.in_use })} label="Adjust estimates" />
        <span style={{ display: "flex", flexDirection: "column" }}>
          <span>Adjust new estimates automatically</span>
          <span className="fr-kicker">{durations ? `Learned from ${durations.n} finished things.` : "Friday needs a few more finished things before it can."}</span>
        </span>
      </div>
    </>
  )
}

function Legend() {
  return (
    <div style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 11, color: "var(--color-neutral-500)" }}>
      Less
      {[0.08, 0.25, 0.45, 0.7, 1].map((a) => (
        <span key={a} style={{ width: 14, height: 10, borderRadius: 3, background: `color-mix(in srgb, var(--color-accent) ${a * 100}%, transparent)` }} />
      ))}
      More
    </div>
  )
}

function Heat({ heat }: { heat: number[][] }) {
  const top = Math.max(1, ...heat.flat())
  return (
    <div style={{ display: "grid", gridTemplateColumns: "40px repeat(16, minmax(0,1fr))", gap: 3, alignItems: "center" }}>
      <span />
      {HOURS.map((h) => (
        <span key={h} className="tnum" style={{ fontSize: 10, color: "var(--color-neutral-500)" }}>
          {h}
        </span>
      ))}
      {heat.map((row, d) => (
        <Row key={DAYS[d]} day={DAYS[d]} row={row} top={top} />
      ))}
    </div>
  )
}

function Row({ day, row, top }: { day: string; row: number[]; top: number }) {
  return (
    <>
      <span style={{ fontSize: 11, color: "var(--color-neutral-400)" }}>{day}</span>
      {row.map((m, h) => (
        <span
          key={h}
          title={`${day} ${HOURS[h]}:00, ${m} min`}
          style={{ height: 22, borderRadius: 4, background: m ? `color-mix(in srgb, var(--color-accent) ${Math.round(8 + (m / top) * 92)}%, transparent)` : "color-mix(in srgb, var(--color-text) 4%, transparent)" }}
        />
      ))}
    </>
  )
}

/** One question about tomorrow: two versions that finish the same work. */
function Comparison() {
  const questions = useQuery({ queryKey: ["questions"], queryFn: () => query("questions") }).data
  const answer = useCommand("compare_answer", { label: (o) => o.result.message ?? "Thanks" })
  const { skinOf } = useLook()
  const q = questions?.comparisons[0]
  if (!q) return null
  const day = String(q.day)
  type B = { item_id: number; title: string; start: string; end: string; area?: string | null }
  const versions = [
    { letter: "A", blocks: q.a as unknown as B[] },
    { letter: "B", blocks: q.b as unknown as B[] },
  ]
  const fixed = (q.fixed ?? []) as unknown as B[]
  const all = [...versions.flatMap((v) => v.blocks), ...fixed]
  const lo = Math.min(...all.map((b) => toMin(b.start))) - 30
  const hi = Math.max(...all.map((b) => toMin(b.end))) + 30
  const scale = 380 / Math.max(60, hi - lo)
  return (
    <Section title={`Which ${weekday(day) === "Thu" ? "Thursday" : weekday(day)} looks better?`} note="One quick question helps Friday learn what you prefer">
      <div className="fr-stack" style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 300px)) minmax(0,1fr)", gap: 20, alignItems: "start" }}>
        {versions.map((v) => (
          <div key={v.letter} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <span style={{ fontWeight: 500 }}>Version {v.letter}</span>
            <div style={{ position: "relative", height: 380, overflow: "hidden", borderRadius: "var(--radius-md)", background: "var(--color-bg)", backgroundImage: `repeating-linear-gradient(to bottom, color-mix(in srgb, var(--color-text) 5%, transparent) 0 1px, transparent 1px ${60 * scale}px)` }}>
              {fixed.map((b) => (
                <div key={`f${b.start}`} style={{ position: "absolute", left: 6, right: 6, top: (toMin(b.start) - lo) * scale, height: Math.max(14, (toMin(b.end) - toMin(b.start)) * scale - 2), padding: "3px 9px", borderRadius: 5, background: "color-mix(in srgb, var(--color-text) 7%, transparent)", color: "var(--color-neutral-500)", fontSize: 11, overflow: "hidden", whiteSpace: "nowrap" }}>
                  {b.title}
                </div>
              ))}
              {v.blocks.map((b) => {
                const s = skinOf("planned", b.area)
                return (
                  <div key={`${b.item_id}${b.start}`} style={{ position: "absolute", left: 6, right: 6, top: (toMin(b.start) - lo) * scale, height: Math.max(14, (toMin(b.end) - toMin(b.start)) * scale - 2), padding: "3px 7px 3px 9px", borderRadius: 5, background: s.bg, color: s.fg, fontSize: 11, overflow: "hidden", whiteSpace: "nowrap" }}>
                    <span style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: 3, background: s.stripe }} />
                    {b.title}{" "}
                    <span className="tnum" style={{ color: "var(--color-neutral-500)" }}>
                      {clock(b.start)}
                    </span>
                  </div>
                )
              })}
            </div>
            <button className="btn btn-secondary" onClick={() => answer({ id: q.id, answer: v.letter.toLowerCase() as "a" | "b" })}>
              Pick {v.letter}
            </button>
          </div>
        ))}
        <div style={{ display: "flex", flexDirection: "column", gap: 10, paddingTop: 26 }}>
          <span style={{ color: "var(--color-neutral-300)", textWrap: "pretty" }}>Both finish the same work, placed differently around your classes (grey). Pick the day you'd rather have.</span>
          <button className="btn btn-ghost" onClick={() => answer({ id: q.id, answer: "skip" })} style={{ alignSelf: "flex-start" }}>
            Skip
          </button>
        </div>
      </div>
    </Section>
  )
}

function LoadLegend() {
  return (
    <span style={{ display: "flex", gap: 12, fontSize: 11, color: "var(--color-neutral-500)" }}>
      <span style={{ display: "flex", gap: 6, alignItems: "center" }}>
        <span style={{ width: 14, height: 1, background: "var(--color-neutral-500)" }} />
        Capacity
      </span>
      <span style={{ display: "flex", gap: 6, alignItems: "center" }}>
        <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--fr-due)" }} />
        Deadline
      </span>
    </span>
  )
}

function Load() {
  const { setDialog } = useShell()
  const weeks = useLoad(8).data ?? []
  const top = Math.max(1, ...weeks.map((w) => Math.max(w.hours, w.capacity)))
  const over = weeks.find((w) => w.hours > w.capacity + 0.5)
  return (
    <>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(8, minmax(0,1fr))", gap: 10, alignItems: "end" }}>
        {weeks.map((w) => {
          const heavy = w.hours > w.capacity
          return (
            <div key={w.start} style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <div style={{ position: "relative", height: 140, borderRadius: 6, background: "var(--color-bg)" }}>
                <div style={{ position: "absolute", left: 0, right: 0, bottom: `${(w.capacity / top) * 100}%`, height: 1, background: "var(--color-neutral-500)" }} />
                <div style={{ position: "absolute", left: 6, right: 6, bottom: 0, height: `${(w.hours / top) * 100}%`, borderRadius: "4px 4px 0 0", background: heavy ? "var(--fr-warn)" : w.forecast ? "color-mix(in srgb, var(--color-accent) 45%, transparent)" : "var(--color-accent)" }} />
                {w.due.length > 0 && (
                  <span title={w.due.map((d) => d.title).join(", ")} style={{ position: "absolute", top: 6, left: 6, display: "flex", gap: 3 }}>
                    {w.due.slice(0, 5).map((d) => (
                      <span key={d.item_id} style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--fr-due)" }} />
                    ))}
                  </span>
                )}
              </div>
              <span className="tnum" style={{ fontSize: 11, color: heavy ? "var(--fr-warn)" : "var(--color-neutral-300)" }}>
                {weekday(w.start)} {Number(w.start.slice(8, 10))}
              </span>
              <span className="tnum" style={{ fontSize: 11, color: "var(--color-neutral-500)" }}>
                {w.hours.toFixed(0)} / {w.capacity.toFixed(0)} h
              </span>
            </div>
          )
        })}
      </div>
      {over && (
        <div style={{ display: "flex", gap: 14, alignItems: "center", padding: "12px 14px", borderRadius: "var(--radius-md)", background: "color-mix(in srgb, var(--fr-mark) 9%, var(--color-bg))" }}>
          <Icon name="warning" size={18} style={{ color: "var(--fr-warn)" }} />
          <span style={{ flex: 1, textWrap: "pretty" }}>
            The week of {weekday(over.start)} {Number(over.start.slice(8, 10))} holds {(over.hours - over.capacity).toFixed(1)} h more than you can do.
          </span>
          <button className="btn btn-secondary" onClick={() => setDialog("triage")}>
            See options
          </button>
        </div>
      )}
    </>
  )
}
