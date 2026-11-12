// An integration connected by pasting a token (C96: Todoist, then Notion, Asana and the others): its steps and the
// token box until it's connected; then where it stands, how new to-dos arrive (the setting you asked to see once it's
// connected), Sync now, and Disconnect, which asks whether what it brought in stays. Apple Reminders (C100) is the same
// box without a token: Friday's Mac app reads it, once macOS lets it.

import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useEffect, useMemo, useRef, useState } from "react"
import { useNavigate } from "react-router"
import { query, type Schemas } from "@/api/client"
import { Icon, Switch } from "@/components/fr/controls"
import { useCommand } from "@/hooks/useCommand"
import { when } from "@/lib/format"
import { useShell } from "@/shell/ShellContext"
import type { Entry } from "./gallery"
import { SCRIPT_LINK, scriptKey, scriptToken, tasksScript } from "./tasksScript"
import { inMacApp } from "./MacAccounts"
import { useOnce } from "./Held"

export type Connected = Schemas["Connected"]
type Arrival = Connected["arrival"]

export const ARRIVALS: { value: Arrival; label: string; note: string }[] = [
  { value: "inbox_first", label: "Review the first, then straight in", note: "The first batch waits in your Inbox; later ones go straight into your plan." },
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
        (entry.onMac ? (
          <MacConnect entry={entry} />
        ) : entry.script ? (
          <ScriptConnect entry={entry} />
        ) : entry.signIn ? (
          <SignInConnect entry={entry} waiting={waiting} onWaiting={setWaiting} />
        ) : (
          <ConnectForm entry={entry} />
        ))}
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
  const [busy, once] = useOnce() // pressed twice, a second account of the same: connected once
  const submit = () =>
    once(async () => {
      if (!token.trim() || missing) return
      // A refused token is said in a toast, in the service's words; it stays in the box to correct.
      if (await connect({ kind: entry.id, token, fields })) setToken("")
    })
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
        <button className="btn btn-primary" onClick={submit} disabled={!token.trim() || missing || !!unready || busy} style={{ fontSize: 12 }}>
          Connect
        </button>
      </div>
      {token_.note && <span className="fr-kicker">{token_.note}</span>}
      <span className="fr-kicker">Your token stays on this Mac. Friday checks it with {entry.name} first.</span>
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
      <span className="fr-kicker">Your sign-in stays on this Mac.</span>
    </div>
  )
}

/** Google Tasks through a script in your own Google account (C130): the script with this Friday's key to copy, the
 * steps to deploy it, Google's "hasn't verified this app" warning said before you meet it with what to press, and the
 * Web app link to paste. */
function ScriptConnect({ entry }: { entry: Entry }) {
  const s = entry.script!
  const [key] = useState(() => scriptKey())
  const script = useMemo(() => tasksScript(key), [key])
  const [copied, setCopied] = useState(false)
  const [showing, setShowing] = useState(false)
  const [link, setLink] = useState("")
  const area = useRef<HTMLTextAreaElement>(null)
  const connect = useCommand("integration_connect", { label: (o) => o.result.message })
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(script)
      setCopied(true)
    } catch {
      // no clipboard here: the script shows, selected, to copy with ⌘C
      setShowing(true)
      requestAnimationFrame(() => area.current?.select())
    }
  }
  const good = SCRIPT_LINK.test(link.trim())
  const [busy, once] = useOnce()
  const submit = () =>
    once(async () => {
      if (!good) return
      // A refusal is said in a toast with what to do; the link stays in the box to try again.
      if (await connect({ kind: entry.id, token: scriptToken(link, key), fields: {} })) setLink("")
    })
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <ol style={{ margin: 0, paddingLeft: 20, listStyle: "decimal", display: "flex", flexDirection: "column", gap: 5, fontSize: 13 }}>
        {s.steps.map((step) => (
          <li key={step} style={{ textWrap: "pretty" }}>
            {step}
          </li>
        ))}
      </ol>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        <button className="btn btn-primary" onClick={copy} style={{ fontSize: 12 }}>
          <Icon name={copied ? "check" : "copy"} />
          {copied ? "Copied" : "Copy script"}
        </button>
        <a className="btn btn-secondary" href={s.open} target="_blank" rel="noreferrer" style={{ fontSize: 12 }}>
          <Icon name="arrow-square-out" />
          Open Google Apps Script
        </a>
        <button className="fr-link" onClick={() => setShowing((v) => !v)} style={{ fontSize: 12 }}>
          {showing ? "Hide the script" : "Read the script"}
        </button>
      </div>
      {showing && (
        <textarea
          ref={area}
          readOnly
          value={script}
          aria-label="Friday's Google Tasks script"
          spellCheck={false}
          style={{ width: "100%", height: 180, fontFamily: "var(--fr-mono, ui-monospace, monospace)", fontSize: 11, lineHeight: 1.4, padding: 8, borderRadius: "var(--radius-md)", background: "var(--color-bg)", color: "var(--color-text)", border: "1px solid color-mix(in srgb, var(--color-text) 12%, transparent)", resize: "vertical" }}
        />
      )}
      <div role="note" style={{ display: "flex", flexDirection: "column", gap: 6, padding: 12, borderRadius: "var(--radius-md)", background: "color-mix(in srgb, var(--fr-warn) 10%, var(--color-surface))", boxShadow: "inset 0 0 0 1px color-mix(in srgb, var(--fr-warn) 45%, transparent)", fontSize: 13 }}>
        <span style={{ display: "flex", gap: 8, alignItems: "center", fontWeight: 600 }}>
          <Icon name="warning" size={16} style={{ color: "var(--fr-warn)" }} />
          {s.warning.before}
        </span>
        <span>
          It says <strong>“{s.warning.says}”</strong>. {s.warning.why}
        </span>
        <span style={{ fontWeight: 500 }}>To go on:</span>
        <ol style={{ margin: 0, paddingLeft: 20, listStyle: "decimal", display: "flex", flexDirection: "column", gap: 3 }}>
          {s.warning.then.map((step) => (
            <li key={step}>{step}</li>
          ))}
        </ol>
      </div>
      <label className="fr-kicker" htmlFor={`script-${entry.id}`}>
        The script's Web app URL
      </label>
      <div style={{ display: "flex", gap: 8 }}>
        <input
          id={`script-${entry.id}`}
          className="input"
          autoComplete="off"
          spellCheck={false}
          value={link}
          onChange={(e) => setLink(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
          placeholder="https://script.google.com/macros/s/…/exec"
          style={{ flex: 1, minWidth: 0, padding: "5px 8px", minHeight: 0, fontSize: 13 }}
        />
        <button className="btn btn-primary" onClick={submit} disabled={!good || busy} style={{ fontSize: 12 }}>
          Connect
        </button>
      </div>
      {link.trim() && !good && (
        <span style={{ fontSize: 12, color: "var(--fr-warn)" }}>
          {/\/dev(\?|$)/.test(link.trim()) ? "That's the test link: use the Web app URL, the one ending in /exec." : "That isn't the Web app URL yet: it starts https://script.google.com/ and ends in /exec."}
        </span>
      )}
      {s.note && <span className="fr-kicker" style={{ textWrap: "pretty" }}>{s.note}</span>}
      <span className="fr-kicker">The link and key stay on this Mac. Friday checks them with your script first.</span>
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
          ? `Friday's Mac app reads ${entry.name} while it's open; nothing leaves this Mac.`
          : `Open Friday on your Mac to connect ${entry.name}.`}
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
  const flip = async (t: TodoList, on: boolean, keep = true) => {
    client.setQueryData<TodoList[]>(key, (old) => old?.map((x) => (x.id === t.id ? { ...x, on } : x))) // at once
    setLeaving(null)
    const out = await set({ id: c.id, list: t.id, on, keep })
    // refused: back as it was (audit, 12 Nov: the switch stayed flipped, this query isn't one a command takes back)
    if (!out) client.setQueryData<TodoList[]>(key, (old) => old?.map((x) => (x.id === t.id ? { ...x, on: t.on } : x)))
    return out
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
