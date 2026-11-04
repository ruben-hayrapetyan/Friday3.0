// Late on paper, on time in practice (3 Nov): the work your plans showed late that you finished by its due, how you
// did it, and what Friday learned from it. The questions it leads to wait in the Inbox (commands/beat_plan.py).

import { useQuery } from "@tanstack/react-query"
import { NavLink } from "react-router"
import { query } from "@/api/client"
import { headline, ways } from "./latePlans"
import { Section } from "./Section"

export function BeatPlan() {
  const data = useQuery({ queryKey: ["beat_plan"], queryFn: () => query("beat_plan") }).data
  if (!data || data.on_time + data.late === 0) return null
  return (
    <Section title="Late on paper, on time in practice" note="Work a plan showed late that you finished by its due, and how">
      <span style={{ textWrap: "pretty" }}>{headline(data.on_time, data.late)}</span>
      {ways(data.counts).length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          {ways(data.counts).map((w) => (
            <span key={w.way} className="fr-chip" style={{ display: "inline-flex", gap: 6, alignItems: "baseline", padding: "3px 10px", borderRadius: 999, background: "color-mix(in srgb, var(--color-text) 6%, transparent)", fontSize: 12.5 }}>
              {w.said}
              <span className="tnum" style={{ color: "var(--color-neutral-400)" }}>{w.n}</span>
            </span>
          ))}
        </div>
      )}
      {/* `said` repeats the headline and the chips in sentences (seen 3 Nov): left out, as ink without news */}
      {data.asking.length > 0 && (
        <NavLink to="/inbox" className="fr-link" style={{ fontSize: 13, alignSelf: "flex-start" }}>
          {data.asking.length === 1 ? "A question about it is waiting in the Inbox" : `${data.asking.length} questions about it are waiting in the Inbox`}
        </NavLink>
      )}
    </Section>
  )
}
