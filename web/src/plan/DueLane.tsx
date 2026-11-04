// A day's deadlines as a to-do lane down the side of its column (personal's day lists, COMBINED.md 15): a strip a
// shade darker than the page, its list pinned below the day headers as you scroll, ticked off like the to-do list.
// Week view's narrow lanes keep to the checkbox and title; the pointer shows the whole title.

import { dueBlock } from "./DueCount"
import { useQueryClient } from "@tanstack/react-query"
import type { Schemas } from "@/api/client"
import { useToast } from "@/components/Toasts"
import { runCommand } from "@/hooks/useCommand"
import { clock } from "@/lib/format"
import { useShell } from "@/shell/ShellContext"

export function DueLane({ dues, stickyTop, narrow }: { dues: Schemas["DueMarker"][]; stickyTop: number; narrow: boolean }) {
  const { select } = useShell()
  const client = useQueryClient()
  const toast = useToast()
  const sorted = [...dues].sort((a, b) => a.due.localeCompare(b.due))
  return (
    <div
      aria-label="Due this day"
      style={{
        position: "absolute",
        top: 0,
        bottom: 0,
        right: 0,
        width: "var(--lane)",
        zIndex: 2,
        background: "color-mix(in srgb, var(--color-text) 3.5%, var(--color-surface))",
        boxShadow: "inset 1px 0 0 var(--fr-hairline)",
      }}
    >
      <div style={{ position: "sticky", top: stickyTop, display: "flex", flexDirection: "column", gap: 1, padding: "6px 4px" }}>
        <span className="fr-eyebrow" style={{ padding: "0 4px 4px" }}>
          Due
        </span>
        {sorted.map((d) => (
          <div key={d.item_id} title={`${d.title}, due ${clock(d.due)}`} style={{ display: "flex", alignItems: narrow ? "flex-start" : "center", gap: 6, padding: "3px 4px", borderRadius: "var(--radius-sm)", minWidth: 0 }} className="fr-hover">
            <button
              className="fr-check"
              role="checkbox"
              aria-checked="false"
              aria-label={`Mark ${d.title} done`}
              onClick={() => runCommand(client, toast, "done", { id: d.item_id })}
              style={{ width: 15, height: 15 }}
            />
            <button className="fr-plain" onClick={() => select(dueBlock(d))} style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", fontSize: 12, lineHeight: 1.25 }}>
              <span style={narrow ? { display: "-webkit-box", WebkitLineClamp: 3, WebkitBoxOrient: "vertical", overflow: "hidden", fontSize: 11, overflowWrap: "anywhere" } : { whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                {d.title}
              </span>
              {!narrow && !d.due.endsWith("T23:59") && (
                <span className="tnum" style={{ fontSize: 11.5, color: "var(--color-neutral-500)" }}>
                  {clock(d.due)}
                </span>
              )}
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}

