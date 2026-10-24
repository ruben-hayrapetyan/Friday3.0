// Tokens (M10d): what lets an assistant (MCP at /mcp, or `fridayd mcp` with FRIDAY_TOKEN) or a script into Friday.
// Every token is listed with what it may do, when it was made and last used; delete one, or all of them, and
// anything using it stops working at once. Each token is shown once, when it's made.

import { useQuery } from "@tanstack/react-query"
import { useState } from "react"
import { query } from "@/api/client"
import { Icon, Seg } from "@/components/fr/controls"
import { useCommand } from "@/hooks/useCommand"
import { when } from "@/lib/format"
import { useShell } from "@/shell/ShellContext"
import { Field, SectionHead } from "./SettingsPage"

export function Tokens() {
  const { today } = useShell()
  const tokens = useQuery({ queryKey: ["tokens"], queryFn: () => query("tokens") }).data ?? []
  const add = useCommand("token_add", { label: () => "Token made" })
  const remove = useCommand("token_remove", { label: (o) => o.result.message ?? "Deleted" })
  const [name, setName] = useState("")
  const [scope, setScope] = useState<"read" | "read-write">("read")
  const [made, setMade] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const [asking, setAsking] = useState<string | null>(null) // a token's name, or "*" for all of them
  const taken = tokens.some((t) => t.name === name.trim())
  const day = (local: string) => (local.startsWith(today) ? `today, ${when(local, today)}` : when(local, today))
  const drop = async (names: string[]) => {
    for (const n of names) await remove({ name: n })
    setAsking(null)
  }
  const confirm = (what: string, names: string[]) => (
    <span style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
      <span style={{ fontSize: 12, color: "var(--color-neutral-400)" }}>{what}</span>
      <button className="btn btn-ghost" onClick={() => drop(names)} style={{ fontSize: 12, color: "var(--fr-due)" }}>
        Delete
      </button>
      <button className="btn btn-ghost" onClick={() => setAsking(null)} style={{ fontSize: 12 }}>
        Keep
      </button>
    </span>
  )
  return (
    <>
      <SectionHead
        title="Tokens"
        note="Keys that let an assistant or a script into Friday. Delete one and whatever uses it stops at once."
        right={
          tokens.length > 1 &&
          (asking === "*" ? (
            confirm(`Delete all ${tokens.length}?`, tokens.map((t) => t.name))
          ) : (
            <button className="btn btn-ghost" onClick={() => setAsking("*")} style={{ fontSize: 12, color: "var(--fr-due)" }}>
              <Icon name="trash" />
              Delete all
            </button>
          ))
        }
      />
      <Field name="Your tokens" note={tokens.length ? `${tokens.length} in use` : undefined}>
        {tokens.length === 0 && <span className="fr-kicker">No tokens. Nothing outside this app can get in.</span>}
        {tokens.map((t) => (
          <div key={t.name} className="fr-row" style={{ display: "flex", flexWrap: "wrap", gap: "6px 14px", alignItems: "center", padding: "10px 0" }}>
            <Icon name="key" size={14} style={{ color: "var(--color-neutral-400)" }} />
            <span style={{ display: "flex", flexDirection: "column", gap: 1, flex: "1 1 180px", minWidth: 0 }}>
              <span style={{ fontWeight: 500 }}>{t.name}</span>
              <span className="fr-kicker tnum">
                {t.scope === "read-write" ? "Can read and make changes" : "Can only read"} · made {day(t.created)} · {t.last_used ? `last used ${day(t.last_used)}` : "never used"}
              </span>
            </span>
            {asking === t.name ? (
              confirm(`Delete ${t.name}?`, [t.name])
            ) : (
              <button className="btn btn-ghost" onClick={() => setAsking(t.name)} aria-label={`Delete ${t.name}`} style={{ fontSize: 12, color: "var(--color-neutral-400)" }}>
                <Icon name="trash" />
                Delete
              </button>
            )}
          </div>
        ))}
      </Field>
      <Field name="Make a token" note="For Claude or another assistant over MCP, or a script. It's shown once.">
        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="Name, e.g. claude" aria-label="Token name" style={{ width: 180, padding: "5px 8px", minHeight: 0 }} />
          <Seg options={[{ value: "read" as const, label: "Read only" }, { value: "read-write" as const, label: "Read and change" }]} value={scope} onPick={setScope} label="What it may do" />
          <button
            className="btn btn-secondary"
            disabled={!name.trim() || taken}
            onClick={async () => {
              const out = await add({ name: name.trim(), scope })
              if (out) {
                setMade(out.result.token)
                setCopied(false)
                setName("")
              }
            }}
            style={{ fontSize: 12 }}
          >
            <Icon name="plus" />
            Make token
          </button>
        </div>
        {taken && <span style={{ fontSize: 12, color: "var(--fr-due)" }}>There's already a token called {name.trim()}.</span>}
        {made && (
          <div className="fr-well" style={{ display: "flex", flexDirection: "column", gap: 6, padding: "10px 12px" }}>
            <code style={{ wordBreak: "break-all", fontSize: 12 }}>{made}</code>
            <span style={{ display: "flex", gap: 10, alignItems: "center" }}>
              <button className="btn btn-secondary" onClick={() => navigator.clipboard?.writeText(made).then(() => setCopied(true))} style={{ fontSize: 12 }}>
                <Icon name={copied ? "check" : "copy"} />
                {copied ? "Copied" : "Copy"}
              </button>
              <span className="fr-kicker">Copy it now; it isn’t shown again.</span>
            </span>
          </div>
        )}
      </Field>
    </>
  )
}
