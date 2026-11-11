// An integration connected by pasting a token (C96: Todoist, then Notion, Asana and the others): its steps and the
// token box until it's connected; then where it stands, how new to-dos arrive (the setting you asked to see once it's
// connected), Sync now, and Disconnect, which asks whether what it brought in stays.

import { useQuery } from "@tanstack/react-query"
import { useState } from "react"
import { useNavigate } from "react-router"
import { query, type Schemas } from "@/api/client"
import { Seg } from "@/components/fr/controls"
import { useCommand } from "@/hooks/useCommand"
import { when } from "@/lib/format"
import { useShell } from "@/shell/ShellContext"
import type { Entry } from "./gallery"

export type Connected = Schemas["Connected"]
type Arrival = Connected["arrival"]

export const ARRIVALS: { value: Arrival; label: string; note: string }[] = [
  { value: "inbox_first", label: "Review the first, then straight in", note: "Its first to-dos wait in your Inbox to review together; new ones after that go straight into your plan." },
  { value: "straight", label: "Always straight in", note: "Every to-do goes straight into your plan." },
  { value: "inbox", label: "Always in the Inbox", note: "Every new to-do waits in your Inbox for you to accept." },
]

/** What's connected now, by integration kind (several accounts of one service each have a row). */
export function useIntegrations() {
  return useQuery({ queryKey: ["integrations"], queryFn: () => query("integrations") as Promise<Connected[]> })
}

export function TokenIntegration({ entry }: { entry: Entry }) {
  const mine = (useIntegrations().data ?? []).filter((c) => c.kind === entry.id)
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      {mine.map((c) => (
        <ConnectedRow key={c.id} c={c} />
      ))}
      {mine.length === 0 && <ConnectForm entry={entry} />}
    </div>
  )
}

function ConnectForm({ entry }: { entry: Entry }) {
  const [token, setToken] = useState("")
  const connect = useCommand("integration_connect", { label: (o) => o.result.message })
  const token_ = entry.token!
  const submit = async () => {
    if (!token.trim()) return
    // A refused token is said in a toast, in the service's words; it stays in the box to correct.
    if (await connect({ kind: entry.id, token })) setToken("")
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <ol style={{ margin: 0, paddingLeft: 20, listStyle: "decimal", display: "flex", flexDirection: "column", gap: 4, fontSize: 13 }}>
        {token_.steps.map((s) => (
          <li key={s}>{s}</li>
        ))}
      </ol>
      <a className="fr-link" href={token_.page} target="_blank" rel="noreferrer" style={{ fontSize: 12, alignSelf: "flex-start" }}>
        Open {entry.name}'s token page
      </a>
      <label className="fr-kicker" htmlFor={`token-${entry.id}`}>
        {token_.label}
      </label>
      <div style={{ display: "flex", gap: 8 }}>
        <input
          id={`token-${entry.id}`}
          className="input"
          type="password"
          autoComplete="off"
          spellCheck={false}
          value={token}
          onChange={(e) => setToken(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
          placeholder="Paste the token"
          style={{ flex: 1, minWidth: 0, padding: "5px 8px", minHeight: 0, fontSize: 13 }}
        />
        <button className="btn btn-primary" onClick={submit} disabled={!token.trim()} style={{ fontSize: 12 }}>
          Connect
        </button>
      </div>
      <span className="fr-kicker">The token stays on this Mac, in Friday's private settings file. Friday checks it with {entry.name} before keeping it.</span>
    </div>
  )
}

function ConnectedRow({ c }: { c: Connected }) {
  const { today } = useShell()
  const navigate = useNavigate()
  const set = useCommand("integration_set", { label: () => "Saved" })
  const syncNow = useCommand("sync_now", { label: (o) => o.result.message })
  const disconnect = useCommand("integration_disconnect", { label: () => `${c.name} disconnected` })
  const [leaving, setLeaving] = useState(false)
  const arrival = ARRIVALS.find((a) => a.value === c.arrival) ?? ARRIVALS[0]
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <span style={{ fontSize: 13, color: c.last_error ? "var(--fr-warn)" : undefined }}>
        {c.last_error ?? (c.last_sync ? `Read ${when(c.last_sync, today)}: ${c.made} open to-do${c.made === 1 ? "" : "s"} from it in your plan.` : "Connected: reading it within the minute.")}
      </span>
      {(c.waiting ?? 0) > 0 && (
        <button className="fr-link" onClick={() => navigate("/inbox")} style={{ fontSize: 13, alignSelf: "flex-start" }}>
          {c.waiting} waiting in your Inbox to review
        </button>
      )}
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        <span style={{ fontWeight: 500, fontSize: 13 }}>New to-dos</span>
        <Seg label="How new to-dos arrive" size="small" value={c.arrival} options={ARRIVALS.map(({ value, label }) => ({ value, label }))} onPick={(value) => set({ id: c.id, arrival: value })} />
        <span className="fr-kicker">{arrival.note}</span>
      </div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <button className="btn btn-secondary" onClick={() => syncNow({})} style={{ fontSize: 12 }}>
          Sync now
        </button>
        <button className="btn btn-secondary" onClick={() => setLeaving(true)} style={{ fontSize: 12 }}>
          Disconnect
        </button>
      </div>
      {leaving && (
        <div role="alertdialog" aria-label={`Disconnect ${c.name}`} className="fr-well" style={{ display: "flex", flexDirection: "column", gap: 10, padding: 14, borderRadius: "var(--radius-md)" }}>
          <span style={{ fontSize: 13 }}>
            Keep {c.made === 1 ? "the to-do" : `the ${c.made} to-dos`} {c.name} brought in, or remove {c.made === 1 ? "it" : "them"} from Friday? Nothing changes in {c.name}.
          </span>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button className="btn btn-secondary" onClick={() => disconnect({ id: c.id, keep: true }).then(() => setLeaving(false))} style={{ fontSize: 12 }}>
              Keep them
            </button>
            <button className="btn btn-secondary" onClick={() => disconnect({ id: c.id, keep: false }).then(() => setLeaving(false))} style={{ fontSize: 12 }}>
              Remove them
            </button>
            <button className="fr-link" onClick={() => setLeaving(false)} style={{ fontSize: 12 }}>
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
