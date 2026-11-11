// A service connected by the calendar link it publishes (C96: Blackboard, Moodle, Brightspace, Schoology; When I Work,
// Deputy, 7shifts, Sling): its own steps to the link, what Friday does with it, the box to paste it in, and the links
// you've added from it. Homebase gives no link: its box says how its shifts reach Friday through the Mac's calendars.

import { useState } from "react"
import { useNavigate } from "react-router"
import { useCommand } from "@/hooks/useCommand"
import { useInbox } from "@/inbox/InboxPage"
import { when } from "@/lib/format"
import { useShell } from "@/shell/ShellContext"
import type { Entry } from "./gallery"

interface Source {
  id: number
  kind: string
  name: string
  enabled: boolean
  last_sync: string | null
  last_error: string | null
  service?: string | null
}

/** The links added from this service's box, still read. */
export function useServiceLinks(service: string): Source[] {
  const sources = (useInbox().data?.sources ?? []) as Source[]
  return sources.filter((s) => s.kind === "ics" && s.enabled && s.service === service)
}

/** webcal:// is a calendar app's way of saying https:// (or http://). */
export function asFetchable(link: string): string {
  const trimmed = link.trim()
  return trimmed.replace(/^webcals?:\/\//i, "https://")
}

export function looksLikeALink(link: string): boolean {
  return /^(https?|webcals?):\/\/[^\s/]+\.[^\s]+/i.test(link.trim())
}

export function LinkIntegration({ entry }: { entry: Entry }) {
  const mine = useServiceLinks(entry.id)
  const add = useCommand("source_add", { label: (o) => o.result.message })
  const remove = useCommand("source_remove", { label: (o) => o.result.message })
  const { today } = useShell()
  const [link, setLink] = useState("")
  const steps = entry.link!
  const submit = async () => {
    if (!looksLikeALink(link)) return
    const name = mine.length ? `${entry.name} ${mine.length + 1}` : entry.name
    if (await add({ name, url: asFetchable(link), service: entry.id })) setLink("")
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {mine.map((s) => (
        <div key={s.id} style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ flex: 1, minWidth: 0, fontSize: 13, color: s.last_error ? "var(--fr-warn)" : undefined }}>
            {s.name}: {s.last_error ?? (s.last_sync ? `read ${when(s.last_sync, today)}` : "reading it within the minute")}
          </span>
          <button className="btn btn-secondary" onClick={() => remove({ id: s.id })} style={{ fontSize: 12 }}>
            Remove
          </button>
        </div>
      ))}
      <ol style={{ margin: 0, paddingLeft: 20, listStyle: "decimal", display: "flex", flexDirection: "column", gap: 4, fontSize: 13 }}>
        {steps.steps.map((s) => (
          <li key={s}>{s}</li>
        ))}
      </ol>
      <a className="fr-link" href={steps.help} target="_blank" rel="noreferrer" style={{ fontSize: 12, alignSelf: "flex-start" }}>
        {entry.name}'s own help on this
      </a>
      <span className="fr-kicker">{steps.reads}</span>
      <label className="fr-kicker" htmlFor={`link-${entry.id}`}>
        {mine.length ? `Another ${entry.name} link` : `${entry.name}'s calendar link`}
      </label>
      <div style={{ display: "flex", gap: 8 }}>
        <input
          id={`link-${entry.id}`}
          className="input"
          spellCheck={false}
          value={link}
          onChange={(e) => setLink(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
          placeholder="https://… or webcal://…"
          style={{ flex: 1, minWidth: 0, padding: "5px 8px", minHeight: 0, fontSize: 13 }}
        />
        <button className="btn btn-primary" onClick={submit} disabled={!looksLikeALink(link)} style={{ fontSize: 12 }}>
          Add
        </button>
      </div>
      <span className="fr-kicker">The link is private to you: Friday keeps it on this Mac and reads it every half hour.</span>
    </div>
  )
}

/** A service that reaches Friday through the Mac's calendars (Homebase): its steps, and the way to those calendars. */
export function ViaMac({ entry, onOpen }: { entry: Entry; onOpen: (id: string) => void }) {
  const navigate = useNavigate()
  const via = entry.viaMac!
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <ol style={{ margin: 0, paddingLeft: 20, listStyle: "decimal", display: "flex", flexDirection: "column", gap: 4, fontSize: 13 }}>
        {via.steps.map((s) => (
          <li key={s}>{s}</li>
        ))}
      </ol>
      <a className="fr-link" href={via.help} target="_blank" rel="noreferrer" style={{ fontSize: 12, alignSelf: "flex-start" }}>
        {entry.name}'s own help on this
      </a>
      <div style={{ display: "flex", gap: 8 }}>
        <button className="btn btn-secondary" onClick={() => onOpen("mac-calendars")} style={{ fontSize: 12 }}>
          Calendars on this Mac
        </button>
        <button className="fr-link" onClick={() => navigate("/settings#/settings/calendars")} style={{ fontSize: 12 }}>
          Choose which calendars Friday reads
        </button>
      </div>
    </div>
  )
}
