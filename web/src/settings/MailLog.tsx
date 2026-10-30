// What Gmail brought in (M12b): each message read, skipped by the pre-filter, failed or waiting, and why, with
// "Read it anyway" for the skipped and failed ones.

import { useQuery } from "@tanstack/react-query"
import { useState } from "react"
import { query } from "@/api/client"
import { useCommand } from "@/hooks/useCommand"
import { when } from "@/lib/format"
import { useShell } from "@/shell/ShellContext"

const SAID = { read: "Read", skipped: "Skipped", failed: "Failed", waiting: "Waiting" } as const
const SHOWN = 8

export function MailLog() {
  const { today } = useShell()
  const mail = useQuery({ queryKey: ["mail_log"], queryFn: () => query("mail_log", { limit: 60 }) }).data ?? []
  const retry = useCommand("mail_retry", { label: (o) => o.result.message ?? "Queued" })
  const [all, setAll] = useState(false)
  if (!mail.length) return null
  const counts = Object.entries(SAID).map(([k, v]) => [v, mail.filter((m) => m.status === k).length] as const).filter(([, n]) => n)
  return (
    <div style={{ display: "flex", flexDirection: "column" }}>
      <span className="fr-kicker" style={{ paddingBottom: 4 }}>
        Recent mail · {counts.map(([label, n]) => `${n} ${label.toLowerCase()}`).join(", ")}
      </span>
      {mail.slice(0, all ? mail.length : SHOWN).map((m) => (
        <div key={m.id} className="fr-row" style={{ display: "grid", gridTemplateColumns: "64px minmax(0,1fr) auto", gap: 12, alignItems: "center", padding: "7px 0" }}>
          <span style={{ fontSize: 12, color: m.status === "failed" ? "var(--fr-due)" : m.status === "read" ? "var(--color-accent-300)" : "var(--color-neutral-500)" }}>{SAID[m.status]}</span>
          <span style={{ display: "flex", flexDirection: "column", gap: 1, minWidth: 0 }}>
            <span style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{m.subject}</span>
            <span className="fr-kicker" style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
              {m.sender} · {when(m.received, today)}
              {m.status === "read" && ` · ${m.found ? `${m.found} suggested` : "nothing to plan"}`}
            </span>
            {m.status !== "read" && m.why && <span style={{ fontSize: 12, color: m.status === "failed" ? "var(--fr-due)" : "var(--color-neutral-400)", textWrap: "pretty" }}>{m.why}</span>}
          </span>
          {m.status === "skipped" || m.status === "failed" || (m.status === "read" && !m.found) ? (
            <button className="fr-link" onClick={() => retry({ id: m.id })} style={{ fontSize: 12, whiteSpace: "nowrap" }}>
              {m.status === "read" ? "Read it again" : "Read it anyway"}
            </button>
          ) : (
            <span />
          )}
        </div>
      ))}
      {mail.length > SHOWN && (
        <button className="fr-link" onClick={() => setAll(!all)} style={{ fontSize: 12, alignSelf: "flex-start", paddingTop: 6 }}>
          {all ? "Show fewer" : `Show all ${mail.length}`}
        </button>
      )}
    </div>
  )
}
