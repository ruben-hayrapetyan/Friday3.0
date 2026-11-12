// An item's estimate, a tap away while you work on it (27 Oct: "I find myself wanting to do this after I start one"):
// how long it's expected to take and what's left, with −15m, +15m, +30m and +1h. Taps add up on the spot and are
// saved together when you stop, as the to-do's − and + are (todo/Pickers.tsx LengthStepper). The Now bar has it while
// you time something; a block's card has it in place of its Remaining line.

import { useItem } from "@/hooks/queries"
import { useCommand } from "@/hooks/useCommand"
import { useSteps } from "@/hooks/useSteps"
import { dur } from "@/lib/format"

const STEPS = [-15, 15, 30, 60]
const SAVE_AFTER_MS = 700

const said = (by: number) => (by < 0 ? `−${-by}m` : by % 60 ? `+${by}m` : `+${by / 60}h`)

export function EstimateNudge({ itemId, runningMin = 0 }: { itemId: number; runningMin?: number }) {
  const item = useItem(itemId).data?.item
  const edit = useCommand("edit", { label: (o) => `${o.result.item.title}: ${dur(o.result.item.duration_min ?? 0)} expected` })
  const { shown, set, changing } = useSteps(item?.duration_min ?? null, (to) => edit({ id: itemId, duration_min: to }), SAVE_AFTER_MS)
  if (!item || item.amount !== "fixed" || item.duration_min == null) return null
  const total = shown ?? item.duration_min
  const left = total - item.done_min - Math.floor(runningMin)
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6, flexWrap: "wrap", minWidth: 0 }}>
      {STEPS.map((by) => (
        <button
          key={by}
          type="button"
          className="btn btn-ghost tnum"
          disabled={by < 0 && total + by < 15}
          onClick={() => set(Math.max(15, total + by))}
          aria-label={by < 0 ? `${-by} minutes less` : `${by} minutes more`}
          style={{ padding: "1px 7px", minHeight: 0, fontSize: 11.5, boxShadow: "inset 0 0 0 1px color-mix(in srgb, var(--color-text) 12%, transparent)" }}
        >
          {said(by)}
        </button>
      ))}
      <span className="tnum" data-testid="estimate-text" title="How long it's expected to take, all told" style={{ color: changing ? "var(--color-accent-300)" : undefined, whiteSpace: "nowrap" }}>
        {dur(total)} expected · {left > 0 ? `${dur(left)} left` : left === 0 ? "none left" : `${dur(-left)} over`}
      </span>
    </span>
  )
}
