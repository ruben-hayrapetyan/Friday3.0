// A due date that counts down within its day and counts up, in red, once past (personal's, COMBINED.md 21). A
// routine's "due" is only the end of its window (lunch by 2:30pm): past it, it isn't late work, so it says it wasn't
// recorded, quietly, rather than hours "over" in red (27 Oct: lunch and dinner were always overtime).

import { useClock } from "@/hooks/useClock"
import { ampm, dueLabel } from "@/lib/format"
import { useShell } from "@/shell/ShellContext"

export function DueLabel({ due, prefix = "Due ", routine = false }: { due: string; prefix?: string; routine?: boolean }) {
  const now = useClock()
  const { today } = useShell()
  const { text, tone } = dueLabel(due, now, today)
  if (routine && tone !== "plain")
    return (
      <span className="tnum" style={{ color: "var(--color-neutral-500)" }} title="Tick it off, or log it in Sleep & meals when it's a meal">
        {tone === "over" ? "not recorded" : `until ${ampm(due.slice(11, 16))}`}
      </span>
    )
  const color = tone === "over" ? "var(--fr-due)" : tone === "soon" ? "var(--fr-warn)" : undefined
  return (
    <span className="tnum" style={{ color }} title={`Due ${due.replace("T", " ")}`}>
      {tone === "plain" ? `${prefix}${text}` : text}
    </span>
  )
}
