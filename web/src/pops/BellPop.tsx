// Notifications (v22): the latest ones, with what you can do from each, and a link to their settings.

import { useQuery } from "@tanstack/react-query"
import { useNavigate } from "react-router"
import { query } from "@/api/client"
import { Icon } from "@/components/fr/controls"
import { useCommand } from "@/hooks/useCommand"
import { when } from "@/lib/format"
import { useShell } from "@/shell/ShellContext"

interface Note {
  id: number
  key: string
  kind: string
  item_id: number | null
  title: string
  body: string
  sent: string | null
  acted: boolean | null
}

const ICONS: Record<string, [string, string]> = {
  morning_brief: ["sun-horizon", "var(--color-accent-300)"],
  block_start: ["play-circle", "var(--color-accent-300)"],
  slack_low: ["warning", "var(--fr-warn)"],
  overload: ["warning", "var(--fr-warn)"],
  conflict: ["lock-simple", "var(--fr-warn)"],
  check: ["question", "var(--color-accent-300)"],
  evening_review: ["cards", "var(--color-accent-300)"],
  weekly_review: ["calendar-check", "var(--color-accent-300)"],
}

export const useNotes = () => useQuery({ queryKey: ["notifications"], queryFn: async () => (await query("notifications")) as unknown as Note[] })

export function BellPop() {
  const { today, setPop, setDialog } = useShell()
  const navigate = useNavigate()
  const notes = useNotes().data ?? []
  const start = useCommand("start", { label: () => "Started" })
  const done = useCommand("done", { label: () => "Done" })
  const settle = useCommand("settle", { label: () => "Friday plans it again" })
  const go = (f: () => void) => () => (f(), setPop(null))
  const actions = (n: Note): [string, () => void][] => {
    // "Did you finish it?" after a hard item's last block (decision 105), answerable here as on the phone.
    if (n.kind === "check" && n.acted === null && n.item_id) {
      return [
        ["Yes, done", go(() => done({ id: n.item_id as number }))],
        ["Not yet", go(() => settle({ block_key: n.key.replace(/^check:/, ""), status: "not_done" }))],
      ]
    }
    if ((n.kind === "block_start" || n.kind === "slack_low") && n.item_id) return [["Start now", go(() => start({ id: n.item_id as number }))]]
    if (n.kind === "overload") return [["See options", go(() => setDialog("triage"))]]
    if (n.kind === "conflict") return [["Decide", go(() => setDialog("conflicts"))]]
    if (n.kind === "evening_review" || n.kind === "weekly_review") return [["Review", go(() => navigate("/review"))]]
    if (n.kind === "morning_brief") return [["Open brief", go(() => setDialog("brief"))]]
    return []
  }
  return (
    <div className="fr-float" style={{ position: "absolute", right: 150, top: 56, width: 360, maxHeight: "calc(100% - 72px)", overflowY: "auto", zIndex: 10, padding: 8, display: "flex", flexDirection: "column" }}>
      <div style={{ display: "flex", alignItems: "center", padding: "6px 8px 8px" }}>
        <span style={{ flex: 1, fontWeight: 500 }}>Notifications</span>
        <button className="fr-link" style={{ fontSize: 12 }} onClick={go(() => navigate("/settings/notifications"))}>
          Settings
        </button>
      </div>
      {notes.map((n) => {
        const [icon, ic] = ICONS[n.kind] ?? ["bell", "var(--color-neutral-400)"]
        return (
          <div key={n.id} style={{ display: "grid", gridTemplateColumns: "18px minmax(0,1fr)", gap: 10, padding: "10px 8px", borderRadius: "var(--radius-md)", background: n.acted === null ? "color-mix(in srgb, var(--color-accent) 6%, transparent)" : undefined }}>
            <Icon name={icon} size={16} style={{ color: ic, marginTop: 1 }} />
            <span style={{ display: "flex", flexDirection: "column", gap: 6, minWidth: 0 }}>
              <span style={{ display: "flex", gap: 8, alignItems: "baseline" }}>
                <span style={{ flex: 1, fontWeight: 500 }}>{n.title}</span>
                <span className="tnum" style={{ fontSize: 11, color: "var(--color-neutral-500)" }}>
                  {n.sent ? when(n.sent, today) : ""}
                </span>
              </span>
              <span style={{ fontSize: 12, color: "var(--color-neutral-400)" }}>{n.body}</span>
              <span style={{ display: "flex", gap: 6 }}>
                {actions(n).map(([label, run]) => (
                  <button key={label} className="btn btn-secondary" onClick={run} style={{ padding: "3px 9px", fontSize: 11, boxShadow: "none", background: "var(--fr-chip-bg)" }}>
                    {label}
                  </button>
                ))}
              </span>
            </span>
          </div>
        )
      })}
      {!notes.length && <div style={{ padding: "14px 8px", color: "var(--color-neutral-500)" }}>Nothing yet.</div>}
    </div>
  )
}
