// Connecting Google from Friday itself, or from Terminal if you'd rather: Connect opens Google's page in your browser
// (the server runs on this Mac) and the button waits, spinning, until you've allowed Friday there. Before the first
// time, it says what the key file from Google Cloud is and takes it. Gmail's switch is here too. The Google Calendar
// and Gmail cards and setup's last step share these.

import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useEffect, useRef, useState } from "react"
import { ApiError, command, query, type Schemas } from "@/api/client"
import { Icon, Switch } from "@/components/fr/controls"
import { useSettings, useStatus } from "@/hooks/queries"
import { useCommand } from "@/hooks/useCommand"

export type GoogleAccess = Schemas["GoogleConnectOut"]
type Need = "calendar" | "gmail"

const KEY = ["google_connect_status"]
const AFTER = ["status", "google_calendars", "inbox", "settings"] // what a finished sign-in changes

/** What Google lets Friday do and how a sign-in is going, asked every second and a half while Google's page is open.
 * `justNow`: a sign-in this page was watching has just finished. */
export function useGoogleAccess(): (GoogleAccess & { justNow: boolean }) | undefined {
  const client = useQueryClient()
  const access = useQuery({ queryKey: KEY, queryFn: () => query("google_connect_status"), refetchInterval: (q) => (q.state.data?.state === "waiting" ? 1500 : false) }).data
  const [justNow, setJustNow] = useState(false)
  const was = useRef(access?.state)
  useEffect(() => {
    if (was.current === "waiting" && access?.state === "connected") {
      setJustNow(true)
      client.invalidateQueries({ predicate: (q) => AFTER.includes(String(q.queryKey[0])) })
    }
    was.current = access?.state
  }, [access?.state, client])
  return access && { ...access, justNow }
}

/** The button's words: what pressing it does now. */
export function connectLabel(access: GoogleAccess, need: Need, again: boolean): string {
  if (access.state === "waiting") return "Waiting for Google…"
  if (again) return "Connect again"
  return need === "gmail" && access.calendar ? "Allow Gmail" : "Connect Google"
}

/** A reading error that means Google wants you to sign in again (the token expired, was removed, or is short of a
 * permission), rather than Google being down. */
export function wantsSignIn(error: string | null | undefined): boolean {
  return /RefreshError|invalid_grant|insufficient authentication/i.test(error ?? "")
}

/** A refusal as a sentence: "file: file: that isn't Google's key file" (the field named by the server and again by
 * the client) reads "That isn't Google's key file." */
export function sentence(message: string): string {
  const text = message.replace(/^((file|google): )+/, "")
  const said = text.charAt(0).toUpperCase() + text.slice(1)
  return /[.!?]$/.test(said) ? said : `${said}.`
}

const said = (error: unknown) => sentence(error instanceof ApiError ? error.message : String(error))

/** Connect, and what it says while Google's page is open, if it failed, and once it worked (`done` adds what's next).
 * `again` asks for a new sign-in though one is saved; `why` says what it's for. */
export function ConnectGoogle({ need = "calendar", again = false, why, done }: { need?: Need; again?: boolean; why?: string; done?: string }) {
  const access = useGoogleAccess()
  const client = useQueryClient()
  const [pressed, setPressed] = useState(false)
  const [problem, setProblem] = useState<string | null>(null)
  if (!access) return null
  if ((need === "gmail" ? access.gmail : access.calendar) && !again)
    return (
      <span style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 12, color: "var(--color-accent-300)" }}>
        <Icon name="check-circle" size={15} fill />
        {access.justNow && done ? `Connected. ${done}` : "Connected"}
      </span>
    )
  if (!access.client_file)
    return (
      <>
        <KeyFile />
        <TerminalWay />
      </>
    )
  const waiting = access.state === "waiting"
  const start = async () => {
    setPressed(true)
    setProblem(null)
    try {
      client.setQueryData(KEY, (await command("google_connect", {})).result)
    } catch (error) {
      setProblem(said(error))
    }
    setPressed(false)
  }
  const failed = problem ?? (access.state === "failed" ? access.message : null)
  const note = failed ?? (waiting ? "Google's page is open in your browser: choose your account and click Allow (if it says the app isn't verified, click Advanced, then Go to Friday). This updates by itself." : (why ?? "Opens Google's page in your browser. Allow Friday there, then come back."))
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6, alignItems: "flex-start" }}>
      <span style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <button className="btn btn-primary" onClick={start} disabled={waiting || pressed} aria-busy={waiting || pressed} style={{ fontSize: 12 }}>
          {waiting || pressed ? <span className="fr-spinner" /> : <Icon name="google-logo" />}
          {pressed && !waiting ? "Opening Google…" : connectLabel(access, need, again)}
        </button>
        {waiting && access.url && (
          <a className="fr-link" href={access.url} target="_blank" rel="noreferrer" style={{ fontSize: 12 }}>
            Didn't see it? Open Google's page
          </a>
        )}
      </span>
      <span style={{ fontSize: 12, color: failed ? "var(--fr-due)" : "var(--color-neutral-300)", textWrap: "pretty" }}>{note}</span>
      <TerminalWay />
    </div>
  )
}

export const TERMINAL = "fridayd google-login --client-file ~/Downloads/client_secret.json"

/** The same sign-in from Terminal, for those who'd rather: the command, a copy button, and that this page follows. */
export function TerminalWay() {
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(TERMINAL)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      setCopied(false) // no clipboard here: the command is on screen to select
    }
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 6, paddingTop: 10, boxShadow: "inset 0 1px 0 var(--fr-hairline)", alignSelf: "stretch" }}>
      <span className="fr-kicker">Or use Terminal</span>
      <span style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <code style={{ padding: "3px 8px", borderRadius: 4, background: "var(--color-surface)", fontSize: 12, userSelect: "all" }}>{TERMINAL}</code>
        <button className="btn btn-ghost fr-press" onClick={copy} style={{ fontSize: 12, padding: "2px 8px" }}>
          <Icon name={copied ? "check" : "copy"} />
          {copied ? "Copied" : "Copy"}
        </button>
      </span>
      <span style={{ fontSize: 12, color: "var(--color-neutral-400)", textWrap: "pretty" }}>
        Put the name of the key file you downloaded in place of client_secret.json (leave out --client-file once Friday has it). It opens Google's page the same way; when you've allowed Friday, this card shows Connected by itself.
      </span>
    </div>
  )
}

// Getting the key file, step by step, each with the Google Cloud page it happens on (about five minutes, once).
const CLOUD = "https://console.cloud.google.com"
const STEPS: { what: string; how: string; link?: [string, string] }[] = [
  { what: "Make a project", how: "Sign in with the Google account whose calendar you want, name the project “Friday” and click Create.", link: ["New project", `${CLOUD}/projectcreate`] },
  { what: "Turn on the Calendar API", how: "Click Enable. (For mail too, turn on the Gmail API the same way.)", link: ["Calendar API", `${CLOUD}/apis/library/calendar-json.googleapis.com`] },
  { what: "Say who may sign in", how: "Click Get started: app name “Friday”, your email, audience External. Then under Audience, add your own Gmail address as a test user.", link: ["Consent screen", `${CLOUD}/apis/credentials/consent`] },
  { what: "Make the key file", how: "Create credentials → OAuth client ID → application type “Desktop app” → Create → Download JSON. It lands in Downloads as client_secret_….json.", link: ["Credentials", `${CLOUD}/apis/credentials`] },
  { what: "Give it to Friday", how: "Click Choose the key file below and pick that file. Then Connect, and on Google's page click Allow. If Google says it hasn't verified the app, that's expected for your own: click Advanced, then Go to Friday." },
]

/** Before the first sign-in: what the key file is, how to get one, and a way to choose it. */
function KeyFile() {
  const client = useQueryClient()
  const file = useRef<HTMLInputElement>(null)
  const [problem, setProblem] = useState<string | null>(null)
  const send = async (picked: File) => {
    setProblem(null)
    try {
      client.setQueryData(KEY, (await command("google_client_save", { content: await picked.text() })).result)
    } catch (error) {
      setProblem(said(error))
    }
    if (file.current) file.current.value = "" // so the same file can be chosen again
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10, alignItems: "flex-start" }}>
      <span style={{ fontSize: 12, color: "var(--color-neutral-300)", textWrap: "pretty" }}>
        Google only lets apps it knows read your calendar. Friday is your own app, so you introduce it to Google once, for free: Google gives you a small <b style={{ fontWeight: 500 }}>key file</b> (client_secret_….json). It's Friday's ID card, not your password, and it stays on this Mac. About five minutes:
      </span>
      <ol style={{ margin: 0, paddingLeft: 0, listStyle: "none", display: "flex", flexDirection: "column", gap: 8, alignSelf: "stretch" }}>
        {STEPS.map((step, n) => (
          <li key={step.what} style={{ display: "grid", gridTemplateColumns: "22px minmax(0,1fr) auto", gap: 10, alignItems: "start" }}>
            <span className="tnum" style={{ width: 20, height: 20, borderRadius: "50%", display: "grid", placeItems: "center", fontSize: 11, background: "color-mix(in srgb, var(--color-accent) 18%, transparent)", color: "var(--color-accent-200)" }}>
              {n + 1}
            </span>
            <span style={{ display: "flex", flexDirection: "column", gap: 1, fontSize: 12 }}>
              <span style={{ fontWeight: 500 }}>{step.what}</span>
              <span style={{ color: "var(--color-neutral-400)", textWrap: "pretty" }}>{step.how}</span>
            </span>
            {step.link ? (
              <a className="btn btn-ghost" href={step.link[1]} target="_blank" rel="noreferrer" style={{ fontSize: 12, padding: "2px 8px", whiteSpace: "nowrap" }}>
                {step.link[0]}
                <Icon name="arrow-square-out" size={12} />
              </a>
            ) : (
              <span />
            )}
          </li>
        ))}
      </ol>
      <input ref={file} type="file" accept=".json,application/json" style={{ display: "none" }} onChange={(e) => e.target.files?.[0] && send(e.target.files[0])} />
      <button className="btn btn-primary" onClick={() => file.current?.click()} style={{ fontSize: 12 }}>
        <Icon name="key" />
        Choose the key file
      </button>
      {problem && <span style={{ fontSize: 12, color: "var(--fr-due)", textWrap: "pretty" }}>{problem}</span>}
    </div>
  )
}

type GmailPart = { enabled: boolean } & Record<string, unknown>

const useGmail = () => (useSettings().data as Record<string, unknown> | undefined)?.gmail as GmailPart | undefined

/** Gmail on or off, said beside the switch; read-only when friday.toml sets it. */
export function GmailSwitch({ text = "Read my Gmail", note }: { text?: string; note?: string }) {
  const gmail = useGmail()
  const owned = (useStatus().data?.config_keys ?? []).includes("gmail")
  const save = useCommand("settings_set", { label: () => (gmail?.enabled ? "Gmail is off" : "Gmail is on") })
  if (!gmail) return null
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
      <span style={{ opacity: owned ? 0.5 : 1, display: "flex" }}>
        <Switch on={gmail.enabled} onToggle={() => !owned && save({ key: "gmail", value: { ...gmail, enabled: !gmail.enabled } })} label={text} />
      </span>
      <span style={{ display: "flex", flexDirection: "column" }}>
        <span>{text}</span>
        {(owned || note) && <span className="fr-kicker">{owned ? "Set in friday.toml." : note}</span>}
      </span>
    </div>
  )
}

/** With Gmail on but not allowed yet: Allow Gmail once Google is connected; before that, Connect for the calendars asks
 * about mail too. */
export function GmailConnect({ again = false, done }: { again?: boolean; done?: string }) {
  const gmail = useGmail()
  const access = useGoogleAccess()
  if (!gmail?.enabled || !access) return null
  if (!access.calendar) return <span className="fr-kicker">Connect Google Calendar first; Google asks about your mail at the same time.</span>
  return <ConnectGoogle need="gmail" again={again} done={done} why={again ? "Google stopped letting Friday read your mail. Connect again to carry on." : "Google asks you once to let Friday read your mail."} />
}
