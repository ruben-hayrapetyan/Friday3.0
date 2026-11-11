// Integrations (v22, shown and explained, decision 134): Google Calendar and Gmail, connected with a button (Google's
// page opens in your browser; no terminal), one Google account or several, the AI's key and daily budget, course feeds, a syllabus upload, a backup,
// what was imported lately, and tokens for assistants. Controls work only for keys friday.toml doesn't set. Setup's
// last step reuses the Connect button, the feed box, the upload and Gmail's switch.

import { useQuery } from "@tanstack/react-query"
import { useEffect, useRef, useState } from "react"
import { useNavigate } from "react-router"
import { query, type Schemas } from "@/api/client"
import { H, Icon, Switch } from "@/components/fr/controls"
import { useCommand } from "@/hooks/useCommand"
import { useSettings, useStatus } from "@/hooks/queries"
import { spoken } from "@/lib/aiName"
import { when } from "@/lib/format"
import { addDays } from "@/lib/time"
import { useInbox } from "@/inbox/InboxPage"
import { useShell } from "@/shell/ShellContext"
import { Accounts, ACCOUNTS, inMacApp, PRIVACY } from "./MacAccounts"
import { Calendars, useCalendars, useMacCalendars } from "./Calendars"
import { AccountList, signInAgain } from "./GoogleAccounts"
import { APP_PASSWORDS, GmailAppForm } from "./GmailAppForm"
import { ConnectGoogle, GmailConnect, GmailSwitch, googleWay, offline, readable, useGoogleAccess, wantsSignIn } from "./GoogleConnect"
import { MailLog } from "./MailLog"
import { AiConnect, useAi } from "./AiConnect"
import { SectionHead } from "./SettingsPage"
import { CATALOG, type Entry, grouped, search } from "./gallery"
import { LinkIntegration, ViaMac } from "./LinkIntegration"
import { MailIntegration, useMailAccounts } from "./MailIntegration"
import { OutlookMail, TokenIntegration, useIntegrations } from "./TokenIntegration"

export function Integrations() {
  return (
    <>
      <SectionHead title="Integrations" note="Bring in your calendars, to-dos, deadlines and mail. Search, or open any box to connect it." />
      <Gallery />
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
      <p className="fr-kicker" style={{ paddingTop: 18 }}>
        Tokens for assistants and scripts are under <a href="#/settings/tokens">Tokens</a>.
      </p>
    </>
  )
}

/** The gallery (C96, your layout): a search box; what you've connected on top; then each category; a box opens its
 * panel over the gallery, with what it does and, once connected, its settings. */
function Gallery() {
  const [text, setText] = useState("")
  const [open, setOpen] = useState<Entry | null>(null)
  const status = useStatuses()
  const found = search(CATALOG, text)
  const { connected, sections } = grouped(found, new Set(CATALOG.filter((e) => status(e)?.[2]).map((e) => e.id)))
  const rows: [string, Entry[]][] = [...(connected.length ? [["Connected", connected] as [string, Entry[]]] : []), ...sections]
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      <input
        className="input"
        type="search"
        aria-label="Search integrations"
        placeholder="Search integrations: Todoist, Canvas, Gmail…"
        value={text}
        onChange={(e) => setText(e.target.value)}
        style={{ maxWidth: 420, padding: "7px 10px", minHeight: 0, fontSize: 13 }}
      />
      {rows.length === 0 && <span className="fr-kicker">Nothing called “{text}” yet.</span>}
      {rows.map(([title, list]) => (
        <section key={title} aria-label={title} style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <H size={13}>{title}</H>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(230px, 1fr))", gap: 10 }}>
            {list.map((e) => (
              <Box key={e.id} entry={e} status={status(e)} onOpen={() => setOpen(e)} />
            ))}
          </div>
        </section>
      ))}
      {open && <Panel entry={open} status={status(open)} onClose={() => setOpen(null)} onOpen={(id) => setOpen(CATALOG.find((e) => e.id === id) ?? null)} />}
    </div>
  )
}

type Status = [string, string, boolean] | null // what it says, its colour, connected

/** Each box's status, from what the cards themselves read. */
function useStatuses(): (e: Entry) => Status {
  const mac = useMacCalendars().data ?? []
  const sources = (useInbox().data?.sources ?? []) as { kind: string; enabled: boolean; last_error: string | null; service?: string | null }[]
  const ai = useAi()
  const integrations = useIntegrations().data ?? []
  const mailboxes = useMailAccounts().data ?? []
  const ok = "var(--color-accent-300)"
  const warn = "var(--fr-warn)"
  // `service`: only the links added from that box; null, only plain ones (the Calendar links box)
  const of = (kind: string, service?: string | null): Status => {
    const mine = sources.filter((x) => x.kind === kind && x.enabled && (service === undefined || (x.service ?? null) === service))
    if (!mine.length) return null
    return mine.some((x) => x.last_error) ? ["Needs a look", warn, true] : [mine.length > 1 ? `${mine.length} connected` : "Connected", ok, true]
  }
  return (e) => {
    if (e.id === "mac-calendars") return mac.some((c) => c.on) ? [`Reading ${mac.filter((c) => c.on).length}`, ok, true] : null
    if (e.id === "calendar-links") return of("ics", null)
    if (e.link) return of("ics", e.id)
    if (e.mail) {
      const mine = mailboxes.filter((a) => a.provider === e.mail!.provider)
      return mine.length ? [mine.length > 1 ? `${mine.length} connected` : "Connected", ok, true] : null
    }
    if (e.id === "google") return of("gcal")
    if (e.id === "gmail") return of("gmail")
    if (e.id === "ai") return ai.ready ? ["Ready", ok, true] : ["Not set up", warn, false]
    if (e.id === "outlook_mail") {
      const mine = mailboxes.filter((a) => a.provider === "outlook")
      return mine.length ? [mine.length > 1 ? `${mine.length} connected` : "Connected", ok, true] : null
    }
    if (e.token || e.onMac || e.signIn) {
      const mine = integrations.filter((c) => c.kind === e.id)
      if (!mine.length) return null
      return mine.some((c) => c.last_error) ? ["Needs a look", warn, true] : ["Connected", ok, true]
    }
    return null
  }
}

function Box({ entry, status, onOpen }: { entry: Entry; status: Status; onOpen: () => void }) {
  return (
    <button
      className="fr-plain"
      onClick={onOpen}
      aria-label={`${entry.name}${status ? `, ${status[0]}` : ""}`}
      style={{ textAlign: "left", display: "grid", gridTemplateColumns: "36px minmax(0,1fr)", gap: 12, alignItems: "start", padding: 14, borderRadius: "var(--radius-lg)", background: "var(--color-bg)", boxShadow: "inset 0 0 0 1px color-mix(in srgb, var(--color-text) 8%, transparent)" }}
    >
      <Tile entry={entry} />
      <span style={{ display: "flex", flexDirection: "column", gap: 3, minWidth: 0 }}>
        <span style={{ fontWeight: 500 }}>{entry.name}</span>
        <span className="fr-kicker" style={{ textWrap: "pretty", lineHeight: 1.35 }}>
          {entry.line}
        </span>
        {status && (
          <span style={{ display: "inline-flex", gap: 5, alignItems: "center", fontSize: 11, color: status[1] }}>
            <span style={{ width: 6, height: 6, borderRadius: "50%", background: status[1] }} />
            {status[0]}
          </span>
        )}
      </span>
    </button>
  )
}

function Tile({ entry }: { entry: Entry }) {
  return (
    <span aria-hidden="true" style={{ width: 36, height: 36, borderRadius: 10, display: "flex", alignItems: "center", justifyContent: "center", background: `color-mix(in srgb, ${entry.hue} 22%, var(--color-surface))`, color: entry.hue }}>
      <Icon name={entry.icon} size={18} />
    </span>
  )
}

/** A box's panel, over the gallery: Escape, the ×, or a click beside it closes it. */
function Panel({ entry, status, onClose, onOpen }: { entry: Entry; status: Status; onClose: () => void; onOpen: (id: string) => void }) {
  useEffect(() => {
    const key = (e: KeyboardEvent) => e.key === "Escape" && onClose()
    window.addEventListener("keydown", key)
    return () => window.removeEventListener("keydown", key)
  }, [onClose])
  return (
    <div role="presentation" onClick={onClose} style={{ position: "fixed", inset: 0, zIndex: 40, background: "color-mix(in srgb, black 35%, transparent)", display: "flex", justifyContent: "flex-end" }}>
      <aside
        role="dialog"
        aria-modal="true"
        aria-label={entry.name}
        onClick={(e) => e.stopPropagation()}
        style={{ width: "min(560px, 100vw)", height: "100%", overflowY: "auto", background: "var(--color-surface)", padding: 22, display: "flex", flexDirection: "column", gap: 16, boxSizing: "border-box" }}
      >
        <div style={{ display: "grid", gridTemplateColumns: "36px minmax(0,1fr) auto", gap: 12, alignItems: "center" }}>
          <Tile entry={entry} />
          <span style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            <H size={17}>{entry.name}</H>
            <span className="fr-kicker">{status ? `${entry.category} · ${status[0]}` : entry.category}</span>
          </span>
          <button className="fr-plain" aria-label="Close" onClick={onClose} style={{ padding: 6, borderRadius: 8 }}>
            <Icon name="x" size={16} />
          </button>
        </div>
        <span style={{ fontSize: 13, textWrap: "pretty" }}>{entry.line}.</span>
        <PanelBody entry={entry} onOpen={onOpen} />
      </aside>
    </div>
  )
}

/** What each box opens: the card it has always had, or, for one connected by token, its connect form and settings. */
function PanelBody({ entry, onOpen }: { entry: Entry; onOpen: (id: string) => void }) {
  if (entry.id === "outlook_mail") return <OutlookMail entry={entry} />
  if (entry.token || entry.onMac || entry.signIn) return <TokenIntegration entry={entry} />
  if (entry.link) return <LinkIntegration entry={entry} />
  if (entry.mail) return <MailIntegration entry={entry} />
  if (entry.viaMac) return <ViaMac entry={entry} onOpen={onOpen} />
  switch (entry.id) {
    case "mac-calendars":
      return <MacCalendars />
    case "calendar-links":
      return <Feeds />
    case "google":
      return <GoogleDirect />
    case "gmail":
      return <GmailApp />
    case "ai":
      return <Ai />
    case "ask-ai":
      return <AskClaude />
    case "syllabus":
      return (
        <Card icon="file-pdf" title="Syllabus upload" note="One syllabus (a PDF, or a page saved from Canvas or a course site) becomes class times, readings, assignments and exam prep, reviewed together in your Inbox." right={<Upload />}>
          <Documents />
        </Card>
      )
  }
  return null
}

/** The calendars on this Mac (8 Nov: users "can't connect google", and Setup was the only place this was): every
 * calendar the Mac's Calendar app has, Google's too once its account is added to the Mac, with no sign-in in Friday. */
function MacCalendars() {
  const navigate = useNavigate()
  const mac = useMacCalendars().data ?? []
  const onMac = inMacApp() || mac.length > 0
  const reading = mac.filter((c) => c.on)
  if (!onMac)
    return (
      <Card icon="calendar-dots" title="Your calendars" note="In Friday's Mac app, Friday reads every calendar on your Mac: iCloud, Google, Outlook, your school's, with nothing to connect. In a browser, paste a calendar's private link under Course feeds below.">
        <a className="fr-link" href="https://calendar.google.com/calendar/r/settings" target="_blank" rel="noreferrer" style={{ fontSize: 12 }}>
          Find your Google calendar's private link (“Secret address in iCal format”)
        </a>
      </Card>
    )
  return (
    <Card icon="calendar-dots" title="Calendars on this Mac" status={reading.length ? [`Reading ${reading.length}`, "var(--color-accent-300)"] : ["None yet", "var(--fr-warn)"]} note="Friday reads every calendar the Mac's Calendar app has. To bring in Google, iCloud or Outlook, add that account to the Mac: no sign-in in Friday.">
      {mac.length > 0 && <Accounts calendars={mac} />}
      <span style={{ display: "flex", gap: 14, flexWrap: "wrap", fontSize: 12 }}>
        <a className="fr-link" href={ACCOUNTS}>
          Add an account to this Mac…
        </a>
        <button className="fr-link" onClick={() => navigate("/settings/calendars")} style={{ fontSize: 12 }}>
          Choose which calendars count
        </button>
      </span>
      <span className="fr-kicker" style={{ textWrap: "pretty" }}>
        In System Settings choose Google (or another), sign in, and keep Calendars on: its calendars appear here within a few seconds.
        {mac.length === 0 && (
          <>
            {" "}
            Nothing here? Friday needs your permission to see them:{" "}
            <a className="fr-link" href={PRIVACY}>
              Privacy & Security → Calendars
            </a>
            .
          </>
        )}
      </span>
    </Card>
  )
}

/** Whether Google's own connection opens by itself: when it's in use; in your own Friday also while Gmail is on or there
 * are no Mac calendars. Not for Gmail by app password in a download, which switches Gmail on too (C81). */
export function advancedOpens(p: { direct: boolean; googleCalendar: boolean; gmailOn: boolean; macCalendars: boolean }): boolean {
  return p.googleCalendar || (p.direct && (p.gmailOn || !p.macCalendars))
}

/** Google's own connection and Gmail, under More when the Mac's calendars are the way in: open while either is in use. */
function GoogleDirect() {
  const access = useGoogleAccess()
  const gmail = usePart<{ enabled: boolean }>("gmail")
  const mac = useMacCalendars().data ?? []
  // Only your own Friday carries Google's client (C77); in a download this is for someone with a Google Cloud key of
  // their own, so it stays closed until used.
  const way = googleWay(!!access?.client_file)
  const direct = way.direct
  // Gmail by app password switches `gmail.enabled` on too, so in a download only Google's own connection opens it
  // (C81: a user who connected Gmail properly then saw the key-file card and took Google for calendar-only).
  const used = advancedOpens({ direct, googleCalendar: !!access?.calendar, gmailOn: !!gmail?.enabled, macCalendars: inMacApp() || mac.length > 0 })
  const [open, setOpen] = useState(used)
  useEffect(() => {
    if (used) setOpen(true)
  }, [used])
  return (
    <>
      <button className="fr-plain fr-hover" onClick={() => setOpen(!open)} aria-expanded={open} style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 10px", borderRadius: "var(--radius-md)", alignSelf: "flex-start", color: "var(--color-neutral-300)" }}>
        <Icon name={open ? "caret-down" : "caret-right"} size={13} />
        {way.settingsMore}
      </button>
      {open && (
        <>
          <Google />
          <Gmail />
        </>
      )}
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

const CONSENT = "https://console.cloud.google.com/auth/audience"

/** Ask Claude's one setting (27 Oct): whether a change to calendar events waits for your yes, as everything else does. */
function AskClaude() {
  const claude = usePart<{ events_without_asking: boolean }>("claude")
  const status = useStatus().data
  const save = useCommand("settings_set", { label: () => "Saved" })
  const on = !!claude?.events_without_asking
  const ai = useAi().name
  return (
    <Card icon="chat-circle-text" title={`Ask ${ai}`} note={`Say what you want in your own words (⌘J); ${spoken(ai)} proposes the changes as Friday's own, each to keep or not.`}>
      <label style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <Switch on={on} onToggle={() => save({ key: "claude", value: { ...claude, events_without_asking: !on } })} label="Change calendar events without asking" />
        <span style={{ display: "flex", flexDirection: "column", gap: 2 }}>
          <span>Change calendar events without asking</span>
          <span className="fr-kicker" style={{ textWrap: "pretty" }}>
            {on ? `Adding, moving, repeating or deleting events applies as soon as ${spoken(ai)} answers, with Undo.` : `Off: ${spoken(ai)} asks before every change.`} Tasks, rules and settings always ask.
            {(status?.config_keys ?? []).includes("claude") ? " Set in friday.toml." : ""}
          </span>
        </span>
      </label>
    </Card>
  )
}

function Google() {
  const { today } = useShell()
  const status = useStatus().data
  const access = useGoogleAccess()
  const gcal = usePart<{ read: string[]; trusted: string[]; publish: boolean }>("gcal")
  const owned = (status?.config_keys ?? []).includes("gcal")
  const save = useCommand("settings_set", { label: () => "Saved" })
  const sync = useCommand("sync_now", { label: (o) => o.result.message ?? "Syncing" })
  const calendars = useCalendars().data ?? []
  const accounts = access?.accounts ?? []
  const reading = calendars.filter((c) => c.on)
  const connected = !!access?.calendar
  const asking = !access?.justNow && accounts.some((a) => signInAgain(a, calendars)) // until the next sync, after a new sign-in
  const wanted = !!gcal && (calendars.length > 0 || gcal.read.length > 0 || gcal.publish)
  const state: [string, string] = !connected ? (wanted ? ["Not connected", "var(--fr-warn)"] : ["Off", "var(--color-neutral-500)"]) : asking ? ["Connect again", "var(--fr-warn)"] : reading.some((c) => c.error && !offline(c.error)) ? ["Trouble reading", "var(--fr-due)"] : reading.some((c) => offline(c.error)) ? ["Offline", "var(--fr-warn)"] : ["Connected", "var(--color-accent-300)"]
  const last = reading.map((c) => c.last_sync).filter(Boolean).sort().at(-1)
  const another = (
    <>
      For your school's or work's calendar too. Google's page asks which account; if it says access is blocked, add that address as a test user in{" "}
      <a className="fr-link" href={CONSENT} target="_blank" rel="noreferrer">
        Google Cloud
      </a>{" "}
      first, as you did for your own.
    </>
  )
  return (
    <Card icon="google-logo" title="Google Calendar" status={state} note="Events become fixed time. Friday plans around them.">
      {!access?.client_file && !connected && (
        <span className="fr-kicker" style={{ color: "var(--fr-warn)", textWrap: "pretty" }}>
          Most people don't need this: add your Google account to this Mac for its calendars (Calendars on this Mac, at the top), and connect Gmail with an app password (the Gmail card). This is only for someone with a Google Cloud project of their own.
        </span>
      )}
      {connected && <AccountList accounts={accounts} calendars={calendars} demo={!!status?.demo} />}
      {access && !status?.demo && <ConnectGoogle why={connected ? another : undefined} done="Switch on the calendars Friday should read below." />}
      {connected && <Calendars />}
      {connected && gcal && (
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <Switch on={gcal.publish} onToggle={() => !owned && save({ key: "gcal", value: { ...gcal, publish: !gcal.publish } })} label="Publish the plan" />
          <span style={{ display: "flex", flexDirection: "column" }}>
            <span>Publish your plan to a “Friday” calendar</span>
            <span className="fr-kicker">{owned ? "Set in friday.toml." : `One way only. Edit blocks in Friday, not in Google.${accounts.length > 1 ? ` It goes in ${accounts[0].email || "your first account"}.` : ""}`}</span>
          </span>
        </div>
      )}
      {connected && wanted && (
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
  const gmail = usePart<{ enabled: boolean }>("gmail")
  const access = useGoogleAccess()
  const granted = !!access?.gmail
  const allowed = (access?.accounts ?? []).filter((a) => a.gmail)
  const expired = !access?.justNow && allowed.some((a) => wantsSignIn(a.mail_error))
  const trouble = allowed.some((a) => a.mail_error && !offline(a.mail_error))
  const away = allowed.some((a) => offline(a.mail_error))
  const state: [string, string] = !gmail?.enabled ? ["Off", "var(--color-neutral-500)"] : !granted ? ["Needs Google's OK", "var(--fr-warn)"] : expired ? ["Connect again", "var(--fr-warn)"] : trouble ? ["Trouble reading", "var(--fr-due)"] : away ? ["Offline", "var(--fr-warn)"] : ["Reading", "var(--color-accent-300)"]
  return (
    <Card icon="envelope-simple" title="Gmail through Google's connection" status={state} note="Friday reads new mail and suggests assignments, due dates and events. It never sends or deletes. Only for accounts Google lets in: an app password (above) works for any Gmail.">
      <GmailSwitch />
      {gmail?.enabled && <GmailConnect done="Friday reads its new mail within the minute." />}
      {gmail?.enabled && granted && <MailFilters />}
    </Card>
  )
}

/** Which mail the AI reads, and what it read lately, however the mail comes in. */
function MailFilters() {
  const status = useStatus().data
  const gmail = usePart<{ enabled: boolean; query: string; sender_domains: string[]; keywords: string[] }>("gmail")
  const owned = status?.config_keys ?? []
  const save = useCommand("settings_set", { label: () => "Saved" })
  const { today } = useShell()
  const read = (useInbox().data?.sources ?? []).filter((s) => s.kind === "gmail" && s.enabled) // one for each account
  const last = read.map((s) => s.last_sync).filter(Boolean).sort().at(-1)
  const sync = useCommand("sync_now", { label: (o) => o.result.message ?? "Syncing" })
  if (!gmail) return null
  return (
        <>
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
            <span>{last ? `Last read ${when(last, today)}` : "Not read yet"}</span>
            <button className="btn btn-ghost" onClick={() => sync({})} style={{ fontSize: 12, padding: "2px 8px" }}>
              <Icon name="arrows-clockwise" />
              Sync now
            </button>
          </div>
        </>
  )
}

/** Gmail with an app password (8 Nov: users "can add their own gmails - right now it just errors out for them"): any
 * Gmail with 2-Step Verification on, no Google Cloud project. The password goes to secrets.toml and never comes back. */
function GmailApp() {
  const accounts = useQuery({ queryKey: ["gmail_app_accounts"], queryFn: () => query("gmail_app_accounts") })
  const ai = useAi()
  const gmail = usePart<{ enabled: boolean }>("gmail")
  const sources = (useInbox().data?.sources ?? []).filter((s) => s.kind === "gmail")
  const connect = useCommand("gmail_app_set", { label: (o) => o.result.message ?? "Connected" })
  const list = accounts.data ?? []
  // its source is named with its address once there are several, else it's the one "Gmail"
  const errorOf = (a: string) => (sources.find((s) => s.name.includes(a)) ?? (sources.length === 1 ? sources[0] : undefined))?.last_error
  const trouble = list.some((a) => errorOf(a))
  const state: [string, string] = !list.length ? ["Off", "var(--color-neutral-500)"] : !gmail?.enabled ? ["Paused", "var(--fr-warn)"] : trouble ? ["Trouble reading", "var(--fr-due)"] : ["Reading", "var(--color-accent-300)"]
  return (
    <Card icon="envelope-simple" title="Gmail" status={state} note="Friday reads new mail and suggests assignments, due dates and events to your Inbox. It never sends, moves or deletes, and nothing is marked read.">
      {list.map((a) => (
        <div key={a} style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <Icon name="google-logo" size={14} />
          <span style={{ flex: 1, display: "flex", flexDirection: "column" }}>
            <span>{a}</span>
            {errorOf(a) && <span className="fr-kicker" style={{ color: "var(--fr-due)", textWrap: "pretty" }}>{errorOf(a)}</span>}
          </span>
          <button className="btn btn-ghost" onClick={async () => (await connect({ address: a, password: "" })) && accounts.refetch()} style={{ fontSize: 12, color: "var(--fr-due)" }}>
            Remove
          </button>
        </div>
      ))}
      <span className="fr-kicker" style={{ textWrap: "pretty" }}>
        {list.length ? "Another Gmail: " : ""}Make an app password at{" "}
        <a className="fr-link" href={APP_PASSWORDS} target="_blank" rel="noreferrer">
          myaccount.google.com/apppasswords
        </a>{" "}
        (name it Friday; it needs 2-Step Verification on), then paste its 16 letters here. Your usual password won't work, and the app password can be revoked there any time.
      </span>
      <GmailAppForm />
      {!ai.ready && (
        // Mail is read by the AI: without one it waits, unread (9 Nov: what a new user lacks that you have)
        <span className="fr-kicker" style={{ color: "var(--fr-warn)", textWrap: "pretty" }}>
          Friday reads mail with an AI, and none is set up yet: choose one in the AI card below. Until then, mail waits unread.
        </span>
      )}
      {list.length > 0 && gmail?.enabled && <MailFilters />}
    </Card>
  )
}

/** The AI Friday reads with (28 Oct): which, its key and model, a check, and the day's limit. */
function Ai() {
  const ai = useAi()
  const llm = useInbox().data?.llm as { calls: number; daily_calls: number; tokens: number } | undefined
  const llmSettings = usePart<{ daily_calls: number }>("llm")
  const owned = (useStatus().data?.config_keys ?? []) as string[]
  const save = useCommand("settings_set", { label: () => "Saved" })
  return (
    <Card icon="sparkle" title="AI" status={ai.ready ? ["Ready", "var(--color-accent-300)"] : ["Not set up", "var(--fr-warn)"]} note="Reads syllabi and mail into your Inbox, rules Friday can't read itself, and what you ask it. Choose whose.">
      {owned.includes("llm") ? <span className="fr-kicker">Set in friday.toml: change it there.</span> : <AiConnect />}
      {llm && llmSettings && (
        <>
          <span className="fr-kicker" style={{ paddingTop: 6 }}>
            Daily limit
          </span>
          <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
            <input type="range" min={5} max={200} step={5} value={llmSettings.daily_calls} disabled={owned.includes("llm")} onChange={(e) => save({ key: "llm", value: { daily_calls: Number(e.target.value) } })} aria-label="Daily reads" style={{ flex: 1, maxWidth: 300, accentColor: "var(--color-accent)" }} />
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
  const sources = (useInbox().data?.sources ?? []).filter((s) => s.kind === "ics" && !s.service) // a service's own links are in its box (C96)
  const edit = useCommand("source_edit", { label: () => "Saved" })
  const remove = useCommand("source_remove", { label: () => "Removed" })
  return (
    <Card icon="rss" title="Course feeds" note="Calendar links from Canvas or your school. New dates go to your Inbox.">
      {sources.map((f) => (
        <div key={f.id} className="fr-row" style={{ display: "grid", gridTemplateColumns: "10px minmax(0,1fr) auto", gap: 12, alignItems: "center", padding: "10px 0" }}>
          <span style={{ width: 10, height: 10, borderRadius: 3, background: "var(--color-neutral-400)" }} />
          <span style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
            <span style={{ fontWeight: 500 }}>{f.name}</span>
            <span style={{ fontSize: 12, color: f.last_error ? (offline(f.last_error) ? "var(--fr-warn)" : "var(--fr-due)") : "var(--color-neutral-500)" }}>{f.last_error ? readable(f.last_error) : (f.last_sync ? `Read ${when(f.last_sync, today)}` : "Not read yet")}</span>
          </span>
          <span style={{ display: "flex", gap: 6 }}>
            {f.last_error && !offline(f.last_error) && (
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
      <div className="fr-row" style={{ paddingTop: 10 }}>
        <AddFeed />
      </div>
    </Card>
  )
}

/** A box to paste a calendar feed's link into, named after its site ("canvas"). */
/** A calendar link as Friday fetches it: a webcal:// link (Canvas's, Outlook's) is the same address over https. */
export function feedUrl(link: string): string {
  return link.trim().replace(/^webcal:\/\//i, "https://")
}

/** A feed's name from its link: Google's and Outlook's by name, else the site's ("canvas"). */
export function feedName(link: string): string {
  try {
    const host = new URL(feedUrl(link)).hostname.replace(/^www\./, "")
    if (host === "calendar.google.com") return "Google Calendar"
    if (/(^|\.)outlook\.(live|office365|office)\.com$/.test(host)) return "Outlook"
    return host.split(".")[0]
  } catch {
    return "Feed"
  }
}

/** A calendar link added; `trusted`, its events go straight on the calendar (your own calendar's), else they're
 * suggested in the Inbox first (a course feed's). */
export function AddFeed({ trusted = false }: { trusted?: boolean }) {
  const add = useCommand("source_add", { label: (o) => o.result.message ?? "Added" })
  const [url, setUrl] = useState("")
  return (
    <div style={{ display: "flex", gap: 6 }}>
      <input className="input" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="Paste a calendar link" aria-label="Calendar link" style={{ flex: 1, maxWidth: 380, padding: "5px 8px", minHeight: 0 }} />
      <button className="btn btn-secondary" disabled={!/^(https?|webcal):\/\//i.test(url.trim())} onClick={async () => (await add({ kind: "ics", name: feedName(url), url: feedUrl(url), trusted })) && setUrl("")} style={{ fontSize: 12 }}>
        Add feed
      </button>
    </div>
  )
}

/** Upload PDF: a syllabus or handout, read into the Inbox. */
export function Upload() {
  const add = useCommand("document_add", { label: (o) => o.result.message ?? "Reading it" })
  const file = useRef<HTMLInputElement>(null)
  const send = async (picked: File) => {
    const isText = picked.type.startsWith("text/") || picked.type === "" || /\.html?$/i.test(picked.name)
    const content = isText ? await picked.text() : toBase64(new Uint8Array(await picked.arrayBuffer()))
    // A web page goes as HTML: Friday reads it as the text a reader sees.
    await add({ name: picked.name, media_type: isText ? (picked.type === "text/html" || /\.html?$/i.test(picked.name) ? "text/html" : "text/plain") : picked.type, content })
  }
  return (
    <>
      <input ref={file} type="file" accept="application/pdf,image/png,image/jpeg,text/plain,text/html,.html,.htm" style={{ display: "none" }} onChange={(e) => e.target.files?.[0] && send(e.target.files[0])} />
      <button className="btn btn-secondary" onClick={() => file.current?.click()} style={{ fontSize: 12 }}>
        <Icon name="upload-simple" />
        Upload PDF or page
      </button>
    </>
  )
}

/** What an upload came to, in a line: being read, couldn't be read and why, or what it found and where that went
 * (some may be what you have already, or what's waiting from a calendar: 29 Oct, a syllabus whose five assignments
 * were all on the Mac's calendar looked as if it had failed). */
export function documentSays(d: Schemas["DocumentOut"]): string {
  if (d.status === "reading") return "being read…"
  if (d.status === "failed") return `couldn't be read: ${d.error ?? "unknown error"}`
  if (d.status === "skipped") return "skipped"
  if (!d.found) return "read; nothing to plan in it"
  const parts = [d.waiting && `${d.waiting} waiting in your Inbox`, d.accepted && `${d.accepted} added`, d.aside && `${d.aside} you have already`, d.elsewhere && `${d.elsewhere} in your Inbox from a calendar`].filter(Boolean)
  return `found ${d.found}${parts.length ? ` · ${parts.join(" · ")}` : ""}`
}

/** What you've uploaded: each syllabus read or not, what it found and what's still in the Inbox; one that failed can
 * be read again (a PDF's text is read out for the claude command now, so no API key is needed). `compact` for setup:
 * the lines only, no way off to the Inbox. */
export function Documents({ compact }: { compact?: boolean }) {
  const { today } = useShell()
  const navigate = useNavigate()
  const docs = useQuery({ queryKey: ["documents"], queryFn: () => query("documents"), refetchInterval: (q) => (q.state.data?.some((d) => d.status === "reading") ? 5000 : false) }).data ?? []
  const retry = useCommand("document_retry", { label: (o) => o.result.message ?? "Reading it again" })
  if (!docs.length) return null
  return (
    <div style={{ display: "flex", flexDirection: "column", paddingLeft: compact ? 0 : 50 }}>
      <span className="fr-kicker" style={{ paddingBottom: 4 }}>
        Uploaded ({docs.length})
      </span>
      {docs.map((d) => (
        <div key={d.id} className="fr-row" style={{ display: "grid", gridTemplateColumns: "18px minmax(0,1fr) auto", gap: 10, alignItems: "center", padding: "7px 0", fontSize: 12 }}>
          <Icon name={d.kind === "pdf" ? "file-pdf" : d.kind === "image" ? "image" : "file-text"} size={15} style={{ color: "var(--color-neutral-400)" }} />
          <span style={{ display: "flex", flexDirection: "column", gap: 1, minWidth: 0 }}>
            <span style={{ fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={d.name}>
              {d.name}
            </span>
            <span style={{ color: d.status === "failed" ? "var(--fr-warn)" : "var(--color-neutral-500)", textWrap: "pretty" }}>
              {when(d.received, today)} · {documentSays(d)}
            </span>
          </span>
          {d.status === "failed" ? (
            <button className="btn btn-secondary" onClick={() => retry({ id: d.id })} style={{ fontSize: 12, padding: "2px 10px" }}>
              Read again
            </button>
          ) : d.waiting && !compact ? (
            <button className="fr-link" onClick={() => navigate("/inbox")} style={{ fontSize: 12 }}>
              Review
            </button>
          ) : (
            <span />
          )}
        </div>
      ))}
    </div>
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
  const log = useQuery({ queryKey: ["log_list", "recent", 200], queryFn: () => query("log_list", { limit: 200 }) }).data ?? []
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
