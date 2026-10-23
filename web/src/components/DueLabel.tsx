// A due date that counts down within its day and counts up, in red, once past (personal's, COMBINED.md 21).

import { useClock } from "@/hooks/useClock"
import { dueLabel } from "@/lib/format"
import { useShell } from "@/shell/ShellContext"

export function DueLabel({ due, prefix = "Due " }: { due: string; prefix?: string }) {
  const now = useClock()
  const { today } = useShell()
  const { text, tone } = dueLabel(due, now, today)
  const color = tone === "over" ? "var(--fr-due)" : tone === "soon" ? "var(--fr-warn)" : undefined
  return (
    <span className="tnum" style={{ color }} title={`Due ${due.replace("T", " ")}`}>
      {tone === "plain" ? `${prefix}${text}` : text}
    </span>
  )
}
