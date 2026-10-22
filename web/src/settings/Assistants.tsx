// Tokens for assistants and scripts (M10d, kept in v22's Integrations): MCP at /mcp, or `fridayd mcp` with
// FRIDAY_TOKEN; each token is shown once.

import { useQuery } from "@tanstack/react-query"
import { useState } from "react"
import { query } from "@/api/client"
import { H, Icon, Switch } from "@/components/fr/controls"
import { useCommand } from "@/hooks/useCommand"
import { useShell } from "@/shell/ShellContext"
import { when } from "@/lib/format"

export function Assistants() {
  const { today } = useShell()
  const tokens = useQuery({ queryKey: ["tokens"], queryFn: () => query("tokens") }).data ?? []
  const add = useCommand("token_add", { label: () => "Token made" })
  const remove = useCommand("token_remove", { label: (o) => o.result.message ?? "Revoked" })
  const [name, setName] = useState("")
  const [writes, setWrites] = useState(false)
  const [made, setMade] = useState<string | null>(null)
  return (
    <div style={{ display: "flex", flexDirection: "column", paddingTop: 26 }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 10, paddingBottom: 8 }}>
        <H size={20}>Assistants and scripts</H>
        <span className="fr-kicker">Tokens for MCP at /mcp, or `fridayd mcp` with FRIDAY_TOKEN</span>
      </div>
      {tokens.map((t) => (
        <div key={t.name} className="fr-row" style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) auto auto", gap: 12, alignItems: "center", padding: "10px 0" }}>
          <span style={{ display: "flex", flexDirection: "column", gap: 1 }}>
            <span style={{ fontWeight: 500 }}>{t.name}</span>
            <span className="fr-kicker">{t.scope === "read-write" ? "May make changes" : "Reads only"}</span>
          </span>
          <span className="tnum fr-kicker">{t.last_used ? `used ${when(t.last_used, today)}` : "not used yet"}</span>
          <button className="btn btn-ghost" onClick={() => remove({ name: t.name })} style={{ fontSize: 12, color: "var(--color-neutral-400)" }}>
            Revoke
          </button>
        </div>
      ))}
      {made && (
        <div className="fr-well" style={{ display: "flex", flexDirection: "column", gap: 4, padding: "10px 12px", margin: "8px 0" }}>
          <code style={{ wordBreak: "break-all", fontSize: 12 }}>{made}</code>
          <span className="fr-kicker">Copy it now; it isn’t shown again.</span>
        </div>
      )}
      <div className="fr-row" style={{ display: "flex", gap: 10, alignItems: "center", paddingTop: 10, flexWrap: "wrap" }}>
        <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="Name, e.g. claude" style={{ width: 180, padding: "5px 8px", minHeight: 0 }} />
        <Switch on={writes} onToggle={() => setWrites(!writes)} label="May make changes" />
        <span className="fr-kicker">May make changes</span>
        <button
          className="btn btn-secondary"
          disabled={!name.trim()}
          onClick={async () => {
            const out = await add({ name: name.trim(), scope: writes ? "read-write" : "read" })
            if (out) {
              setMade(out.result.token)
              setName("")
            }
          }}
          style={{ fontSize: 12 }}
        >
          <Icon name="key" />
          Make token
        </button>
      </div>
    </div>
  )
}
