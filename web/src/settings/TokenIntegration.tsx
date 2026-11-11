// An integration connected by pasting a token (C96: Todoist, then Notion, Asana and the others): its steps and the
// token box until it's connected; then where it stands, how new to-dos arrive (the setting you asked to see once it's
// connected), Sync now, and Disconnect, which asks whether what it brought in stays. Apple Reminders (C100) is the same
// box without a token: Friday's Mac app reads it, once macOS lets it.

import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useEffect, useState } from "react"
import { useNavigate } from "react-router"
import { query, type Schemas } from "@/api/client"
import { Switch } from "@/components/fr/controls"
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

/** macOS's own page where Friday is allowed to see your reminders (C100), or to use Things (C108). */
export const REMINDERS_PRIVACY = "x-apple.systempreferences:com.apple.preference.security?Privacy_Reminders"
export const PRIVACY_PAGE: Record<string, [string, string]> = {
  reminders: [REMINDERS_PRIVACY, "Open Privacy & Security → Reminders"],
  things: ["x-apple.systempreferences:com.apple.preference.security?Privacy_Automation", "Open Privacy & Security → Automation"],
}

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

/** Outlook (C109): the mailboxes read by Microsoft's sign-in, each with Remove, and Sign in to add one. */
export function OutlookMail({ entry }: { entry: Entry }) {
  const [waiting, setWaiting] = useState(false)
  const boxes = useQuery({ queryKey: ["mail_app_accounts"], queryFn: () => query("mail_app_accounts"), refetchInterval: waiting ? 3000 : false })
  const forget = useCommand("mail_app_forget", { label: (o) => o.result.message })
  const mine = (boxes.data ?? []).filter((b) => b.provider === "outlook")
  const count = mine.length
  const [before, setBefore] = useState(count)
  useEffect(() => {
    if (waiting && count > before) setWaiting(false) // the new mailbox is here: stop asking
    if (!waiting) setBefore(count)
  }, [waiting, count, before])
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      {mine.map((b) => (
        <div key={b.address} style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ flex: 1, minWidth: 0, fontSize: 13 }}>Reading {b.address}</span>
          <button className="btn btn-secondary" onClick={() => forget({ address: b.address })} style={{ fontSize: 12 }}>
            Remove
          </button>
        </div>
      ))}
      <SignInConnect entry={entry} waiting={waiting} onWaiting={setWaiting} />
    </div>
  )
}

export function TokenIntegration({ entry }: { entry: Entry }) {
  const [waiting, setWaiting] = useState(false)
  // while a sign-in page is open in the browser, asked every few seconds: the box turns connected once you're back
  const all = useQuery({ queryKey: ["integrations"], queryFn: () => query("integrations") as Promise<Connected[]>, refetchInterval: waiting ? 3000 : false })
  const mine = (all.data ?? []).filter((c) => c.kind === entry.id)
  useEffect(() => {
    if (waiting && mine.length > 0) setWaiting(false) // connected: stop asking
  }, [waiting, mine.length])
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      {mine.map((c) => (
        <ConnectedRow key={c.id} c={c} />
      ))}
      {mine.length === 0 &&
        (entry.onMac ? <MacConnect entry={entry} /> : entry.signIn ? <SignInConnect entry={entry} waiting={waiting} onWaiting={setWaiting} /> : <ConnectForm entry={entry} />)}
    </div>
  )
}

function ConnectForm({ entry }: { entry: Entry }) {
  const [token, setToken] = useState("")
  const [fields, setFields] = useState<Record<string, string>>({})
  const connect = useCommand("integration_connect", { label: (o) => o.result.message })
  const token_ = entry.token!
  // Trello's page carries Friday's own app key, which the server has: asked for, not written here
  const asked = useQuery({ queryKey: ["integration_token_page", entry.id], queryFn: () => query("integration_token_page", { kind: entry.id }), enabled: !token_.page })
  const page = token_.page || asked.data?.url
  const unready = !token_.page && asked.data && !asked.data.url
  const missing = (token_.fields ?? []).some((f) => !(fields[f.key] ?? "").trim())
  const submit = async () => {
    if (!token.trim() || missing) return
    // A refused token is said in a toast, in the service's words; it stays in the box to correct.
    if (await connect({ kind: entry.id, token, fields })) setToken("")
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <ol style={{ margin: 0, paddingLeft: 20, listStyle: "decimal", display: "flex", flexDirection: "column", gap: 4, fontSize: 13 }}>
        {token_.steps.map((s) => (
          <li key={s}>{s}</li>
        ))}
      </ol>
      {unready ? (
        <span style={{ fontSize: 13, color: "var(--fr-warn)" }}>{entry.name} isn't ready in this copy of Friday yet: it comes with the next update.</span>
      ) : (
        <a className="fr-link" href={page ?? undefined} target="_blank" rel="noreferrer" style={{ fontSize: 12, alignSelf: "flex-start" }}>
          {token_.pageText ?? (token_.page ? `Open ${entry.name}'s token page` : `Open ${entry.name}'s Allow page`)}
        </a>
      )}
      {(token_.fields ?? []).map((f) => (
        <div key={f.key} style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <label className="fr-kicker" htmlFor={`field-${entry.id}-${f.key}`}>
            {f.label}
          </label>
          <input
            id={`field-${entry.id}-${f.key}`}
            className="input"
            type={f.type ?? "text"}
            autoComplete="off"
            spellCheck={false}
            value={fields[f.key] ?? ""}
            onChange={(e) => setFields((was) => ({ ...was, [f.key]: e.target.value }))}
            placeholder={f.placeholder}
            style={{ padding: "5px 8px", minHeight: 0, fontSize: 13 }}
          />
        </div>
      ))}
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
        <button className="btn btn-primary" onClick={submit} disabled={!token.trim() || missing || !!unready} style={{ fontSize: 12 }}>
          Connect
        </button>
      </div>
      {token_.note && <span className="fr-kicker">{token_.note}</span>}
      <span className="fr-kicker">The token stays on this Mac, in Friday's private settings file. Friday checks it with {entry.name} before keeping it.</span>
    </div>
  )
}

/** One connected by signing in on the service's own page (Microsoft, TickTick, Slack; C109): its steps and Sign in,
 * which opens the page in your browser; the page sends you back to Friday, and this box turns connected. */
export function SignInConnect({ entry, waiting, onWaiting }: { entry: Entry; waiting: boolean; onWaiting: (w: boolean) => void }) {
  const ready = useQuery({ queryKey: ["integration_token_page", entry.id], queryFn: () => query("integration_token_page", { kind: entry.id }) })
  const start = useCommand("integration_sign_in", { label: () => `${entry.name}'s page opened in your browser` })
  const [url, setUrl] = useState<string | null>(null)
  const sign = entry.signIn!
  const go = async () => {
    const out = await start({ kind: entry.id, origin: window.location.origin })
    if (!out) return
    setUrl(out.result.url)
    onWaiting(true)
    window.open(out.result.url, "_blank", "noopener")
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <ol style={{ margin: 0, paddingLeft: 20, listStyle: "decimal", display: "flex", flexDirection: "column", gap: 4, fontSize: 13 }}>
        {sign.steps.map((s) => (
          <li key={s}>{s}</li>
        ))}
      </ol>
      {ready.data && !ready.data.ready ? (
        <span style={{ fontSize: 13, color: "var(--fr-warn)" }}>{entry.name} isn't ready in this copy of Friday yet: it comes with the next update.</span>
      ) : (
        <button className="btn btn-primary" onClick={go} disabled={!ready.data} style={{ fontSize: 12, alignSelf: "flex-start" }}>
          Sign in with {entry.name.split(" ")[0]}
        </button>
      )}
      {waiting && url && (
        <span className="fr-kicker">
          Finish on {entry.name}'s page in your browser; this box turns connected when you're back.{" "}
          <a className="fr-link" href={url} target="_blank" rel="noreferrer">
            Open it again
          </a>
        </span>
      )}
      {sign.note && <span className="fr-kicker">{sign.note}</span>}
      <span className="fr-kicker">Friday keeps the sign-in on this Mac, in its private settings file; nothing is pasted.</span>
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

type TodoList = Schemas["TodoListOut"]

/** Which of its lists Friday reads (Notion's databases, C101): a switch each; a team's says only yours come in; one
 * switched off that brought to-dos in asks, as Disconnect does, whether they stay. */
function Lists({ c }: { c: Connected }) {
  const client = useQueryClient()
  const key = ["integration_lists", c.id]
  const found = useQuery({ queryKey: key, queryFn: () => query("integration_lists", { id: c.id }) as Promise<TodoList[]> })
  const set = useCommand("integration_list_set", { label: () => "Saved" })
  const [leaving, setLeaving] = useState<TodoList | null>(null)
  const flip = (t: TodoList, on: boolean, keep = true) => {
    client.setQueryData<TodoList[]>(key, (old) => old?.map((x) => (x.id === t.id ? { ...x, on } : x))) // at once
    setLeaving(null)
    return set({ id: c.id, list: t.id, on, keep })
  }
  const lists = found.data ?? []
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <span style={{ fontWeight: 500, fontSize: 13 }}>Lists Friday reads</span>
      {found.isLoading && <span className="fr-kicker">Asking {c.name} for your lists…</span>}
      {found.error && <span style={{ fontSize: 13, color: "var(--fr-warn)" }}>{String((found.error as Error).message ?? found.error)}</span>}
      {found.data && lists.length === 0 && <span className="fr-kicker">No to-do lists yet: a database with a Done checkbox or a Status is one.</span>}
      {lists.map((t) => (
        <div key={t.id} style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) auto", alignItems: "center", gap: 10, padding: "6px 0" }}>
          <span style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
            <span style={{ fontSize: 13 }}>{t.name}</span>
            <span className="fr-kicker">
              {[t.team ? "A team's list: only what's assigned to you" : null, t.made ? `${t.made} in your plan` : null].filter(Boolean).join(" · ") || (t.on ? "Read" : "Not read")}
            </span>
          </span>
          <Switch on={t.on} label={`Read ${t.name}`} onToggle={() => (t.on && t.made > 0 ? setLeaving(t) : flip(t, !t.on))} />
        </div>
      ))}
      {leaving && (
        <div role="alertdialog" aria-label={`Stop reading ${leaving.name}`} className="fr-well" style={{ display: "flex", flexDirection: "column", gap: 10, padding: 14, borderRadius: "var(--radius-md)" }}>
          <span style={{ fontSize: 13 }}>
            Keep {leaving.made === 1 ? "the to-do" : `the ${leaving.made} to-dos`} {leaving.name} brought in, or remove {leaving.made === 1 ? "it" : "them"} from Friday? Nothing changes in {c.name}.
          </span>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button className="btn btn-secondary" onClick={() => flip(leaving, false, true)} style={{ fontSize: 12 }}>
              Keep them
            </button>
            <button className="btn btn-secondary" onClick={() => flip(leaving, false, false)} style={{ fontSize: 12 }}>
              Remove them
            </button>
            <button className="fr-link" onClick={() => setLeaving(null)} style={{ fontSize: 12 }}>
              Cancel
            </button>
          </div>
        </div>
      )}
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
      {PRIVACY_PAGE[c.kind] && c.last_error?.includes("Privacy & Security") && (
        <a className="btn btn-secondary" href={PRIVACY_PAGE[c.kind][0]} style={{ fontSize: 12, alignSelf: "flex-start" }}>
          {PRIVACY_PAGE[c.kind][1]}
        </a>
      )}
      {(c.waiting ?? 0) > 0 && (
        <button className="fr-link" onClick={() => navigate("/inbox")} style={{ fontSize: 13, alignSelf: "flex-start" }}>
          {c.waiting} waiting in your Inbox to review
        </button>
      )}
      {c.lists && <Lists c={c} />}
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
