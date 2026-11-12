// A mailbox read by app password (C99: iCloud Mail, Yahoo, Fastmail, other IMAP): its steps, then address and app
// password (and the server, for other mail); once connected, the addresses read and a way to stop reading each.
// The password is checked with the server before it's kept, on this Mac only.

import { useQuery } from "@tanstack/react-query"
import { useState } from "react"
import { query, type Schemas } from "@/api/client"
import { useCommand } from "@/hooks/useCommand"
import type { Entry } from "./gallery"
import { useOnce } from "./Held"

export type MailAccount = Schemas["MailAppAccount"]

export function useMailAccounts() {
  return useQuery({ queryKey: ["mail_app_accounts"], queryFn: () => query("mail_app_accounts") as Promise<MailAccount[]> })
}

export function MailIntegration({ entry }: { entry: Entry }) {
  const box = entry.mail!
  const mine = (useMailAccounts().data ?? []).filter((a) => a.provider === box.provider)
  const connect = useCommand("mail_app_set", { label: (o) => o.result.message })
  const forget = useCommand("mail_app_forget", { label: (o) => o.result.message })
  const [address, setAddress] = useState("")
  const [password, setPassword] = useState("")
  const [host, setHost] = useState("")
  const other = box.provider === "other"
  const ready = address.includes("@") && password.trim() && (!other || host.includes("."))
  const [busy, once] = useOnce() // Enter and Connect during the slow check connect it once
  const submit = () =>
    once(async () => {
      if (!ready) return
      if (await connect({ provider: box.provider, address, password, host: other ? host : null })) {
        setAddress("")
        setPassword("")
        setHost("")
      }
    })
  const field = { className: "input", spellCheck: false, style: { padding: "5px 8px", minHeight: 0, fontSize: 13 } }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {mine.map((a) => (
        <div key={a.address} style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ flex: 1, minWidth: 0, fontSize: 13 }}>Reading {a.address}</span>
          <button className="btn btn-secondary" onClick={() => forget({ address: a.address })} style={{ fontSize: 12 }}>
            Stop reading
          </button>
        </div>
      ))}
      <ol style={{ margin: 0, paddingLeft: 20, listStyle: "decimal", display: "flex", flexDirection: "column", gap: 4, fontSize: 13 }}>
        {box.steps.map((s) => (
          <li key={s}>{s}</li>
        ))}
      </ol>
      {box.help && (
        <a className="fr-link" href={box.help} target="_blank" rel="noreferrer" style={{ fontSize: 12, alignSelf: "flex-start" }}>
          {entry.name}'s own help on this
        </a>
      )}
      <span className="fr-kicker">Friday only reads: nothing is sent, moved, deleted or marked read. Deadlines and events go to your Inbox, filtered by the senders and words in the Gmail box.</span>
      {other && <input {...field} aria-label="IMAP server" placeholder="IMAP server, like imap.example.com" value={host} onChange={(e) => setHost(e.target.value)} />}
      <input {...field} aria-label="Address" type="email" placeholder="Your address" value={address} onChange={(e) => setAddress(e.target.value)} />
      <div style={{ display: "flex", gap: 8 }}>
        <input {...field} aria-label="App password" type="password" autoComplete="off" placeholder="App password" value={password} onChange={(e) => setPassword(e.target.value)} onKeyDown={(e) => e.key === "Enter" && submit()} style={{ ...field.style, flex: 1, minWidth: 0 }} />
        <button className="btn btn-primary" onClick={submit} disabled={!ready || busy} style={{ fontSize: 12 }}>
          Connect
        </button>
      </div>
      <span className="fr-kicker">Your password stays on this Mac. Friday signs in once to check it.</span>
    </div>
  )
}
