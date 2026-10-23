// Integrations (v22, shown and explained, decision 134): Google Calendar and Gmail as friday.toml and the login
// command set them up, the AI's key and daily budget, course feeds, a syllabus upload, a backup, what was imported
// lately, and tokens for assistants. Controls work only for keys friday.toml doesn't set.

import { useQuery } from "@tanstack/react-query"
import { useEffect, useRef, useState } from "react"
import { query, type Schemas } from "@/api/client"
import { H, Icon, Switch } from "@/components/fr/controls"
import { useCommand } from "@/hooks/useCommand"
import { useSettings, useStatus } from "@/hooks/queries"
import { when } from "@/lib/format"
import { addDays } from "@/lib/time"
import { useInbox } from "@/inbox/InboxPage"
import { useShell } from "@/shell/ShellContext"
import { Assistants } from "./Assistants"
import { Calendars, useCalendars } from "./Calendars"
import { MailLog } from "./MailLog"
import { SectionHead } from "./SettingsPage"

/** The one-time import from the apps Friday replaces (COMBINED.md 24). */
function ImportPersonal() {
  const run = useCommand("import_personal", { label: (o) => o.result.message })
  return (
    <button className="btn btn-secondary" onClick={() => run({})} style={{ fontSize: 12 }}>
      Import
    </button>
  )
}

export function Integrations() {
  return (
    <>
      <SectionHead title="Integrations" note="Bring in fixed events and deadlines. Anything Friday reads from mail or files goes to your Inbox first." />
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <Google />
        <Gmail />
        <Feeds />
        <Card icon="file-pdf" title="Syllabus upload" note="One PDF becomes class times, readings, assignments and exam prep, reviewed together in your Inbox." right={<Upload />} />
        <Card
          icon="arrow-square-in"
          title="Todo List and Chroma"
          note="Bring in Todo List's open tasks (with their due dates, and long-term ones on the Long term list) and Chroma's categories, from their files on this Mac. Each task comes in once, however often you press it."
          right={<ImportPersonal />}
        />
      </div>
      <div className="fr-well" style={{ display: "flex", alignItems: "center", gap: 14, marginTop: 12, padding: "14px 18px", borderRadius: "var(--radius-lg)", boxShadow: "none" }}>
        <Icon name="download-simple" size={18} />
        <span style={{ flex: 1, display: "flex", flexDirection: "column", gap: 2 }}>
          <span style={{ fontWeight: 500 }}>Back up</span>
          <span className="fr-kicker">Download your tasks, tags, rules and history as one file (the whole database; copy it into the data folder to restore).</span>
        </span>
        <a className="btn btn-secondary" href="/api/backup" download style={{ fontSize: 12, color: "var(--color-text)" }}>
          Download
        </a>
      </div>
      <Imported />
      <Assistants />
    </>
  )
}

function Card(props: { icon: string; title: string; status?: [string, string]; note: string; right?: React.ReactNode; children?: React.ReactNode }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14, padding: 18, borderRadius: "var(--radius-lg)", background: "var(--color-bg)" }}>
      <div style={{ display: "grid", gridTemplateColumns: "36px minmax(0,1fr) auto", gap: 14, alignItems: "center" }}>
        <span style={{ width: 36, height: 36, borderRadius: 10, display: "flex", alignItems: "center", justifyContent: "center", background: "var(--color-surface)" }}>
          <Icon name={props.icon} size={18} />
        </span>
        <span style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
          <span style={{ display: "flex", gap: 8, alignItems: "center", fontWeight: 500 }}>
            {props.title}
            {props.status && (
              <span style={{ display: "inline-flex", gap: 5, alignItems: "center", fontSize: 11, fontWeight: 400, color: props.status[1] }}>
                <span style={{ width: 6, height: 6, borderRadius: "50%", background: props.status[1] }} />
                {props.status[0]}
              </span>
            )}
          </span>
          <span className="fr-kicker" style={{ textWrap: "pretty" }}>
            {props.note}
          </span>
        </span>
        {props.right ?? <span />}
      </div>
      {props.children && <div style={{ display: "flex", flexDirection: "column", gap: 8, paddingLeft: 50 }}>{props.children}</div>}
    </div>
  )
}

function Command({ text }: { text: string }) {
  return <code style={{ padding: "2px 6px", borderRadius: 4, background: "var(--color-surface)", fontSize: 12 }}>{text}</code>
}

const usePart = <T,>(key: string) => (useSettings().data as Record<string, unknown> | undefined)?.[key] as T | undefined

function Google() {
  const { today } = useShell()
  const status = useStatus().data
  const gcal = usePart<{ read: string[]; trusted: string[]; publish: boolean }>("gcal")
  const owned = (status?.config_keys ?? []).includes("gcal")
  const save = useCommand("settings_set", { label: () => "Saved" })
  const sync = useCommand("sync_now", { label: (o) => o.result.message ?? "Syncing" })
  const calendars = useCalendars().data ?? []
  const reading = calendars.filter((c) => c.on)
  const unconnected = (status?.problems ?? []).some((p) => p.startsWith("Google isn"))
  const wanted = !!gcal && (calendars.length > 0 || gcal.read.length > 0 || gcal.publish)
  const state: [string, string] = !wanted ? ["Off", "var(--color-neutral-500)"] : unconnected ? ["Not connected", "var(--fr-warn)"] : reading.some((c) => c.error) ? ["Trouble reading", "var(--fr-due)"] : ["Connected", "var(--color-accent-300)"]
  const last = reading.map((c) => c.last_sync).filter(Boolean).sort().at(-1)
  return (
    <Card icon="google-logo" title="Google Calendar" status={state} note="Events become fixed time. Friday plans around them.">
      {(!wanted || unconnected) && (
        <span style={{ fontSize: 12, color: "var(--color-neutral-300)", textWrap: "pretty" }}>
          To connect, run <Command text="uv run fridayd google-login" /> in a terminal on the computer running Friday. It opens Google once; your calendars then list here after a sync.
        </span>
      )}
      {!unconnected && <Calendars />}
      {gcal && (
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <Switch on={gcal.publish} onToggle={() => !owned && save({ key: "gcal", value: { ...gcal, publish: !gcal.publish } })} label="Publish the plan" />
          <span style={{ display: "flex", flexDirection: "column" }}>
            <span>Publish your plan to a “Friday” calendar</span>
            <span className="fr-kicker">{owned ? "Set in friday.toml." : "One way only. Edit blocks in Friday, not in Google."}</span>
          </span>
        </div>
      )}
      {wanted && (
        <div style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 12, color: "var(--color-neutral-500)" }}>
          <span>{last ? `Last read ${when(last, today)}` : "Not read yet"}</span>
          <button className="btn btn-ghost" onClick={() => sync({})} style={{ fontSize: 12, padding: "2px 8px" }}>
            <Icon name="arrows-clockwise" />
            Sync now
          </button>
        </div>
      )}
    </Card>
  )
}

function Gmail() {
  const status = useStatus().data
  const gmail = usePart<{ enabled: boolean; query: string; sender_domains: string[]; keywords: string[] }>("gmail")
  const llmSettings = usePart<{ model: string; daily_calls: number; daily_tokens: number }>("llm")
  const owned = status?.config_keys ?? []
  const save = useCommand("settings_set", { label: () => "Saved" })
  const llm = useInbox().data?.llm as { key: boolean; calls: number; daily_calls: number; tokens: number; daily_tokens: number; model: string } | undefined
  const granted = !(status?.problems ?? []).some((p) => p.startsWith("Gmail isn") || p.startsWith("Google isn"))
  const { today } = useShell()
  const source = (useInbox().data?.sources ?? []).find((s) => s.kind === "gmail")
  const trouble = source?.last_error
  const sync = useCommand("sync_now", { label: (o) => o.result.message ?? "Syncing" })
  const state: [string, string] = !gmail?.enabled ? ["Off", "var(--color-neutral-500)"] : !granted ? ["Needs the Google login again", "var(--fr-warn)"] : trouble ? ["Trouble reading", "var(--fr-due)"] : ["Reading", "var(--color-accent-300)"]
  return (
    <Card icon="envelope-simple" title="Gmail" status={state} note="Friday reads new mail and suggests assignments, due dates and events. It never sends or deletes.">
      {gmail && !gmail.enabled && (
        <span style={{ fontSize: 12, color: "var(--color-neutral-300)" }}>
          Set <Command text="enabled = true" /> under [gmail] in friday.toml, then run <Command text="uv run fridayd google-login" /> so Google allows reading mail.
        </span>
      )}
      {gmail?.enabled && (
        <>
          {trouble && <span style={{ fontSize: 12, color: "var(--fr-due)", textWrap: "pretty" }}>{trouble}</span>}
          <span className="fr-kicker">Mail it looks at</span>
          <span style={{ fontSize: 12 }}>
            <Command text={gmail.query} />
          </span>
          <span className="fr-kicker" style={{ textWrap: "pretty" }}>
            The AI reads mail with one of these words, mail from these senders, and mail from a person asking for something by a day. Newsletters and other bulk mail only when the subject has one of the words.
          </span>
          <ListField label="Words" value={gmail.keywords} locked={owned.includes("gmail")} onSave={(keywords) => save({ key: "gmail", value: { ...gmail, keywords } })} />
          <ListField label="Always read mail from" placeholder="e.g. cornell.edu" value={gmail.sender_domains} locked={owned.includes("gmail")} onSave={(sender_domains) => save({ key: "gmail", value: { ...gmail, sender_domains } })} />
          <MailLog />
          <div style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 12, color: "var(--color-neutral-500)" }}>
            <span>{source?.last_sync ? `Last read ${when(source.last_sync, today)}` : "Not read yet"}</span>
            <button className="btn btn-ghost" onClick={() => sync({})} style={{ fontSize: 12, padding: "2px 8px" }}>
              <Icon name="arrows-clockwise" />
              Sync now
            </button>
          </div>
        </>
      )}
      <span className="fr-kicker" style={{ paddingTop: 6 }}>
        Anthropic API key
      </span>
      <span style={{ fontSize: 12, color: llm?.key ? "var(--color-accent-300)" : "var(--fr-warn)" }}>
        {status?.demo ? "The demo uses a stand-in AI; no key is read." : llm?.key ? "Set in secrets.toml." : <>No key yet: add <Command text="[anthropic] api_key = …" /> to secrets.toml beside friday.toml, or set ANTHROPIC_API_KEY.</>}
      </span>
      <AiCheck />
      {llm && llmSettings && (
        <>
          <span className="fr-kicker" style={{ paddingTop: 6 }}>
            Daily limit
          </span>
          <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
            <input type="range" min={5} max={200} step={5} value={llmSettings.daily_calls} disabled={owned.includes("llm")} onChange={(e) => save({ key: "llm", value: { ...llmSettings, daily_calls: Number(e.target.value) } })} aria-label="Daily reads" style={{ flex: 1, maxWidth: 300, accentColor: "var(--color-accent)" }} />
            <span className="fr-h tnum" style={{ fontSize: 20 }}>
              {llmSettings.daily_calls} reads
            </span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 10, maxWidth: 420 }}>
            <div style={{ flex: 1, height: 6, borderRadius: 3, background: "color-mix(in srgb, var(--color-text) 8%, transparent)", overflow: "hidden" }}>
              <div style={{ height: "100%", width: `${Math.min(100, (llm.calls / Math.max(1, llm.daily_calls)) * 100)}%`, background: "var(--color-accent)" }} />
            </div>
            <span className="tnum" style={{ fontSize: 12, color: "var(--color-neutral-400)", whiteSpace: "nowrap" }}>
              {llm.calls} used today, {Math.round(llm.tokens / 1000)}k tokens
            </span>
          </div>
          <span className="fr-kicker">When the limit is reached, Friday stops reading until tomorrow and tells you.</span>
        </>
      )}
    </Card>
  )
}

function Feeds() {
  const { today } = useShell()
  const sources = (useInbox().data?.sources ?? []).filter((s) => s.kind === "ics")
  const add = useCommand("source_add", { label: (o) => o.result.message ?? "Added" })
  const edit = useCommand("source_edit", { label: () => "Saved" })
  const remove = useCommand("source_remove", { label: () => "Removed" })
  const [url, setUrl] = useState("")
  const name = (u: string) => {
    try {
      return new URL(u).hostname.replace(/^www\./, "").split(".")[0]
    } catch {
      return "Feed"
    }
  }
  return (
    <Card icon="rss" title="Course feeds" note="Calendar links from Canvas or your school. New dates go to your Inbox.">
      {sources.map((f) => (
        <div key={f.id} className="fr-row" style={{ display: "grid", gridTemplateColumns: "10px minmax(0,1fr) auto", gap: 12, alignItems: "center", padding: "10px 0" }}>
          <span style={{ width: 10, height: 10, borderRadius: 3, background: "var(--color-neutral-400)" }} />
          <span style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
            <span style={{ fontWeight: 500 }}>{f.name}</span>
            <span style={{ fontSize: 12, color: f.last_error ? "var(--fr-due)" : "var(--color-neutral-500)" }}>{f.last_error ?? (f.last_sync ? `Read ${when(f.last_sync, today)}` : "Not read yet")}</span>
          </span>
          <span style={{ display: "flex", gap: 6 }}>
            {f.last_error && (
              <button className="btn btn-secondary" onClick={() => { const next = window.prompt("New calendar link"); if (next) edit({ id: f.id, url: next }) }} style={{ fontSize: 12 }}>
                Paste new link
              </button>
            )}
            <button className="btn btn-ghost" onClick={() => remove({ id: f.id, forget: true })} style={{ fontSize: 12, color: "var(--color-neutral-400)" }}>
              Remove
            </button>
          </span>
        </div>
      ))}
      <div className="fr-row" style={{ display: "flex", gap: 6, paddingTop: 10 }}>
        <input className="input" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="Paste a calendar link (.ics)" style={{ flex: 1, maxWidth: 380, padding: "5px 8px", minHeight: 0 }} />
        <button className="btn btn-secondary" disabled={!/^https?:\/\//.test(url.trim())} onClick={async () => (await add({ kind: "ics", name: name(url), url: url.trim(), trusted: false })) && setUrl("")} style={{ fontSize: 12 }}>
          Add feed
        </button>
      </div>
    </Card>
  )
}

function Upload() {
  const add = useCommand("document_add", { label: (o) => o.result.message ?? "Reading it" })
  const file = useRef<HTMLInputElement>(null)
  const send = async (picked: File) => {
    const isText = picked.type.startsWith("text/") || picked.type === ""
    const content = isText ? await picked.text() : toBase64(new Uint8Array(await picked.arrayBuffer()))
    await add({ name: picked.name, media_type: isText ? "text/plain" : picked.type, content })
  }
  return (
    <>
      <input ref={file} type="file" accept="application/pdf,image/png,image/jpeg,text/plain" style={{ display: "none" }} onChange={(e) => e.target.files?.[0] && send(e.target.files[0])} />
      <button className="btn btn-secondary" onClick={() => file.current?.click()} style={{ fontSize: 12 }}>
        <Icon name="upload-simple" />
        Upload PDF
      </button>
    </>
  )
}

function toBase64(bytes: Uint8Array): string {
  let binary = ""
  for (let i = 0; i < bytes.length; i += 32_768) binary += String.fromCharCode(...bytes.subarray(i, i + 32_768))
  return btoa(binary)
}

/** The last week's imports: what came in from a source and what you accepted, each undoable. */
function Imported() {
  const { today } = useShell()
  const log = useQuery({ queryKey: ["log_list", 200], queryFn: () => query("log_list", { limit: 200 }) }).data ?? []
  const undo = useCommand("undo", { label: () => "Import undone" })
  const weekAgo = addDays(today, -7)
  const imports = log.filter((l) => (l.actor.startsWith("sync:") || l.command === "batch_accept" || l.command === "suggestion_accept") && l.at.slice(0, 10) >= weekAgo)
  return (
    <div style={{ display: "flex", flexDirection: "column", paddingTop: 26 }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 10, paddingBottom: 8 }}>
        <H size={20}>What was imported</H>
        <span className="fr-kicker">Last 7 days</span>
      </div>
      {imports.map((l) => (
        <div key={l.id} className="fr-row" style={{ display: "grid", gridTemplateColumns: "96px 20px minmax(0,1fr) auto", gap: 12, alignItems: "center", padding: "9px 0", opacity: l.undone_by ? 0.5 : 1 }}>
          <span className="tnum fr-kicker">{when(l.at, today)}</span>
          <Icon name={l.actor.startsWith("sync:") ? "arrows-clockwise" : "tray"} size={15} style={{ color: "var(--color-neutral-400)" }} />
          <span style={{ display: "flex", flexDirection: "column", gap: 1, minWidth: 0 }}>
            <span style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{l.command === "batch_accept" ? `A batch: ${String(l.input.batch ?? "")}` : "An item from your Inbox"}</span>
            <span className="fr-kicker">{l.actor.startsWith("sync:") ? `Straight in from ${l.actor.slice(5)}` : "Accepted by you"}</span>
          </span>
          {l.undone_by ? (
            <span className="fr-kicker">Undone</span>
          ) : (
            <button className="fr-link" onClick={() => undo({ command_id: l.id })} style={{ fontSize: 12 }}>
              Undo import
            </button>
          )}
        </div>
      ))}
      {!imports.length && <span className="fr-row fr-kicker" style={{ padding: "12px 0" }}>Nothing imported this week.</span>}
    </div>
  )
}

/** One tiny call to each model, the way Friday asks, and what came back. */
function AiCheck() {
  const [checks, setChecks] = useState<Schemas["ModelCheck"][] | null>(null)
  const [busy, setBusy] = useState(false)
  const run = async () => {
    setBusy(true)
    setChecks(await query("ai_check").catch((e) => [{ model: "", job: "", ok: false, said: String(e) }]))
    setBusy(false)
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      {checks?.map((c) => (
        <span key={c.model + c.job} style={{ display: "flex", gap: 8, fontSize: 12, alignItems: "baseline" }}>
          <Icon name={c.ok ? "check-circle" : "x-circle"} size={14} style={{ color: c.ok ? "var(--color-accent-300)" : "var(--fr-due)", flex: "none" }} />
          <span>
            <b style={{ fontWeight: 500 }}>{c.model}</b> <span className="fr-kicker">({c.job.toLowerCase()})</span>: {c.ok ? "works" : c.said}
          </span>
        </span>
      ))}
      <button className="btn btn-secondary" onClick={run} disabled={busy} style={{ alignSelf: "flex-start", fontSize: 12 }}>
        <Icon name="plugs-connected" />
        {busy ? "Asking…" : "Test the AI"}
      </button>
    </div>
  )
}


/** A comma-separated list, saved when you leave the field. */
function ListField(props: { label: string; value: string[]; placeholder?: string; locked: boolean; onSave: (v: string[]) => void }) {
  const shown = props.value.join(", ")
  const [text, setText] = useState(shown)
  useEffect(() => setText(shown), [shown])
  const commit = () => {
    const next = text.split(",").map((w) => w.trim()).filter(Boolean)
    if (next.join(", ") !== shown) props.onSave(next)
  }
  return (
    <label style={{ display: "grid", gridTemplateColumns: "140px minmax(0,1fr)", gap: 10, alignItems: "center", fontSize: 12 }}>
      <span style={{ color: "var(--color-neutral-400)" }}>{props.label}</span>
      <input className="input" value={text} disabled={props.locked} placeholder={props.placeholder} onChange={(e) => setText(e.target.value)} onBlur={commit} onKeyDown={(e) => e.key === "Enter" && commit()} style={{ padding: "5px 8px", minHeight: 0, fontSize: 12 }} />
    </label>
  )
}
