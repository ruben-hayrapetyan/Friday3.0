// Insights (v22): the last few weeks in three numbers, how long things really take by kind (and whether Friday
// adjusts estimates for you), when you get things done, your sleep (when you track it), what Friday learned for you
// to approve, one comparison question, and the load ahead against what you can do.

import { useQuery } from "@tanstack/react-query"
import { useState } from "react"
import { query } from "@/api/client"
import { H, Icon, Seg, Switch } from "@/components/fr/controls"
import { useCommand } from "@/hooks/useCommand"
import { useLoad } from "@/hooks/queries"
import { ampm, weekday } from "@/lib/format"
import { useShell } from "@/shell/ShellContext"
import { Comparison } from "./Comparison"
import { Learned } from "./Learned"
import { Section } from "./Section"
import { SleepSection } from "./Sleep"

export { Section }

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
            <SleepSection />
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
          {ampm(`${h}:00`).replace(/[ap]m$/, (s) => s[0])}
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
          title={`${day} ${ampm(`${HOURS[h]}:00`)}, ${m} min`}
          style={{ height: 22, borderRadius: 4, background: m ? `color-mix(in srgb, var(--color-accent) ${Math.round(8 + (m / top) * 92)}%, transparent)` : "color-mix(in srgb, var(--color-text) 4%, transparent)" }}
        />
      ))}
    </>
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
      {/* One column a week, however many come back (this week and the eight after): they share the width, and on a
          phone the row scrolls sideways inside the section rather than wrapping. */}
      <div style={{ overflowX: "auto", margin: "0 -2px", padding: "0 2px" }}>
        <div style={{ display: "grid", gridTemplateColumns: `repeat(${Math.max(1, weeks.length)}, minmax(52px, 1fr))`, gap: 8, alignItems: "end" }}>
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
                <span className="tnum" style={{ fontSize: 11, whiteSpace: "nowrap", color: heavy ? "var(--fr-warn)" : "var(--color-neutral-300)" }}>
                  {weekday(w.start)} {Number(w.start.slice(8, 10))}
                </span>
                <span className="tnum" style={{ fontSize: 11, whiteSpace: "nowrap", color: "var(--color-neutral-500)" }}>
                  {w.hours.toFixed(0)} / {w.capacity.toFixed(0)} h
                </span>
              </div>
            )
          })}
        </div>
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
