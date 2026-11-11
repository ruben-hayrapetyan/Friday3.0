// An integration connected by pasting a token (C96: Todoist, then Notion, Asana and the others): its steps and the
// token box until it's connected; then where it stands, how new to-dos arrive (the setting you asked to see once it's
// connected), Sync now, and Disconnect, which asks whether what it brought in stays. Apple Reminders (C100) is the same
// box without a token: Friday's Mac app reads it, once macOS lets it.

import { useQuery } from "@tanstack/react-query"
import { useState } from "react"
import { useNavigate } from "react-router"
import { query, type Schemas } from "@/api/client"
import { useCommand } from "@/hooks/useCommand"
import { when } from "@/lib/format"
import { useShell } from "@/shell/ShellContext"
import type { Entry } from "./gallery"
import { inMacApp } from "./MacAccounts"

export type Connected = Schemas["Connected"]
type Arrival = Connected["arrival"]

export const ARRIVALS: { value: Arrival; label: string; note: string }[] = [
  { value: "inbox_first", label: "Review the first, then straight in", note: "Its first to-dos wait in your Inbox to review together; new ones after that go straight into your plan." },
  { value: "straight", label: "Always straight in", note: "Every to-do goes straight into your plan." },
  { value: "inbox", label: "Always in the Inbox", note: "Every new to-do waits in your Inbox for you to accept." },
]

/** macOS's own page where Friday is allowed to see your reminders (C100). */
export const REMINDERS_PRIVACY = "x-apple.systempreferences:com.apple.preference.security?Privacy_Reminders"

/** How new to-dos arrive: each choice with what it means, stacked, so none is cut short (10 Nov: a row of three was
 * "poorly formatted"). */
export function Arrivals({ value, onPick }: { value: Arrival; onPick: (value: Arrival) => void }) {
  return (
    <div role="radiogroup" aria-label="How new to-dos arrive" style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      {ARRIVALS.map((a) => {
        const on = a.value === value
        return (
          <button
            key={a.value}
            role="radio"
            aria-checked={on}
            className="fr-plain"
            onClick={() => onPick(a.value)}
            style={{
              textAlign: "left",
              display: "grid",
              gridTemplateColumns: "16px minmax(0,1fr)",
              columnGap: 10,
              rowGap: 2,
              alignItems: "start",
              padding: "9px 12px",
              borderRadius: "var(--radius-md)",
              background: on ? "color-mix(in srgb, var(--color-accent) 14%, var(--color-surface))" : "var(--color-surface)",
              boxShadow: on ? "inset 0 0 0 1.5px var(--color-accent)" : "inset 0 0 0 1px color-mix(in srgb, var(--color-text) 8%, transparent)",
            }}
          >
            <span aria-hidden="true" style={{ width: 14, height: 14, marginTop: 2, borderRadius: "50%", boxSizing: "border-box", border: on ? "4px solid var(--color-accent)" : "1.5px solid color-mix(in srgb, var(--color-text) 35%, transparent)" }} />
            <span style={{ fontWeight: 500, fontSize: 13 }}>{a.label}</span>
            <span className="fr-kicker" style={{ gridColumn: 2, textWrap: "pretty", lineHeight: 1.35 }}>
              {a.note}
            </span>
          </button>
        )
      })}
    </div>
  )
}

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
      {mine.length === 0 && (entry.onMac ? <MacConnect entry={entry} /> : <ConnectForm entry={entry} />)}
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

/** One read by the Mac app itself (Apple Reminders): its steps and Connect; macOS asks the rest. */
function MacConnect({ entry }: { entry: Entry }) {
  const connect = useCommand("integration_connect", { label: (o) => o.result.message })
  const here = inMacApp()
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <ol style={{ margin: 0, paddingLeft: 20, listStyle: "decimal", display: "flex", flexDirection: "column", gap: 4, fontSize: 13 }}>
        {entry.onMac!.steps.map((s) => (
          <li key={s}>{s}</li>
        ))}
      </ol>
      <button className="btn btn-primary" onClick={() => connect({ kind: entry.id, token: "" })} disabled={!here} style={{ fontSize: 12, alignSelf: "flex-start" }}>
        Connect
      </button>
      <span className="fr-kicker">
        {here
          ? `${entry.name} stays on this Mac: Friday's Mac app reads it while it's open, and nothing goes over the internet.`
          : `${entry.name} is read by Friday's Mac app: open Friday on your Mac to connect it.`}
      </span>
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
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <span style={{ fontSize: 13, color: c.last_error ? "var(--fr-warn)" : undefined }}>
        {c.last_error ?? (c.last_sync ? `Read ${when(c.last_sync, today)}: ${c.made} open to-do${c.made === 1 ? "" : "s"} from it in your plan.` : "Connected: reading it within the minute.")}
      </span>
      {c.kind === "reminders" && c.last_error?.includes("Privacy & Security") && (
        <a className="btn btn-secondary" href={REMINDERS_PRIVACY} style={{ fontSize: 12, alignSelf: "flex-start" }}>
          Open Privacy & Security → Reminders
        </a>
      )}
      {(c.waiting ?? 0) > 0 && (
        <button className="fr-link" onClick={() => navigate("/inbox")} style={{ fontSize: 13, alignSelf: "flex-start" }}>
          {c.waiting} waiting in your Inbox to review
        </button>
      )}
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        <span style={{ fontWeight: 500, fontSize: 13 }}>New to-dos</span>
        <Arrivals value={c.arrival} onPick={(value) => set({ id: c.id, arrival: value })} />
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
