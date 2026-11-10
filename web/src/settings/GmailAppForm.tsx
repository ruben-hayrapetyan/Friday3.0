// Any Gmail, read with an app password (C67), as Setup and Settings both ask for it (C81, 9 Nov: a user found only
// Google Calendar to connect; Setup sent them to Settings to paste the password, and Settings' Advanced Google card
// was what they saw). The address and the app password here; Gmail checks them once; nothing else to set up.

import { useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { useCommand } from "@/hooks/useCommand"

export const APP_PASSWORDS = "https://myaccount.google.com/apppasswords"

/** The address and app password boxes and Connect; `onAdded` once Gmail took them. */
export function GmailAppForm({ onAdded }: { onAdded?: () => void }) {
  const client = useQueryClient()
  const connect = useCommand("gmail_app_set", { label: (o) => o.result.message ?? "Connected" })
  const [address, setAddress] = useState("")
  const [password, setPassword] = useState("")
  const [busy, setBusy] = useState(false)
  const add = async () => {
    if (busy || !address.trim() || !password.trim()) return
    setBusy(true)
    const done = await connect({ address, password })
    setBusy(false)
    if (done) {
      setPassword("")
      setAddress("")
      await client.invalidateQueries({ queryKey: ["gmail_app_accounts"] })
      onAdded?.()
    }
  }
  return (
    <form onSubmit={(e) => (e.preventDefault(), add())} style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
      <input className="input" type="email" autoComplete="off" placeholder="you@gmail.com" value={address} onChange={(e) => setAddress(e.target.value)} aria-label="Gmail address" style={{ width: 220 }} />
      <input className="input" type="password" autoComplete="new-password" placeholder="App password" value={password} onChange={(e) => setPassword(e.target.value)} aria-label="App password" style={{ width: 200 }} />
      <button className="btn btn-primary" type="submit" disabled={busy || !address.trim() || !password.trim()}>
        {busy ? "Checking with Gmail…" : "Connect"}
      </button>
    </form>
  )
}
