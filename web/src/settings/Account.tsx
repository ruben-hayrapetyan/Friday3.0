// The account a hosted Friday is signed in as, its passkeys and Sign out (HOSTED.md S4; H88, H90). Nothing on your
// own Friday, which has no accounts.

import { useCallback, useEffect, useState } from "react"
import { addPasskey, canMakePasskeys, listPasskeys, type Passkey, removePasskey } from "@/api/passkeys"
import { type Me, signOut, whoAmI } from "@/api/session"

/** "Nov 5" from engine minutes. */
export function day(minutes: number): string {
  return new Date(minutes * 60_000).toLocaleDateString(undefined, { month: "short", day: "numeric" })
}

export function Account() {
  const [me, setMe] = useState<Me | null>(null)
  const [keys, setKeys] = useState<Passkey[]>([])
  const [said, setSaid] = useState("")
  const [busy, setBusy] = useState(false)
  const reload = useCallback(() => void listPasskeys().then(setKeys), [])
  useEffect(() => {
    void whoAmI().then((found) => {
      setMe(found)
      if (found) reload()
    })
  }, [reload])
  if (!me) return null
  const add = async () => {
    setBusy(true)
    setSaid("")
    try {
      setSaid(`Passkey added: ${await addPasskey()}`)
      reload()
    } catch (error) {
      setSaid(error instanceof Error && error.name === "NotAllowedError" ? "No passkey made." : `Couldn't add a passkey: ${String((error as Error).message ?? error)}`)
    } finally {
      setBusy(false)
    }
  }
  const row = { display: "flex", alignItems: "center", gap: 12, padding: "8px 12px", borderRadius: "var(--radius-md)", background: "var(--color-bg)" }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6, marginBottom: 18 }}>
      <div className="fr-row" style={row}>
        <span style={{ flex: 1, textWrap: "pretty" }}>
          Signed in as <b>{me.name}</b> ({me.username}, {me.email})
        </span>
        <button className="btn" disabled={busy} onClick={() => (setBusy(true), void signOut())}>
          Sign out
        </button>
      </div>
      {keys.map((k) => (
        <div key={k.id} className="fr-row" style={row}>
          <span style={{ flex: 1 }}>
            Passkey: <b>{k.name}</b> <span className="fr-kicker">made {day(k.created)}{k.used ? `, last used ${day(k.used)}` : ", not used yet"}</span>
          </span>
          <button className="btn btn-ghost" onClick={() => void removePasskey(k.id).then(reload)} aria-label={`Remove the passkey ${k.name}`}>
            Remove
          </button>
        </div>
      ))}
      {canMakePasskeys() && (
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <button className="btn" disabled={busy} onClick={() => void add()}>
            Add a passkey
          </button>
          <span className="fr-kicker">Sign in with Touch ID instead of an email link. The link always still works.</span>
        </div>
      )}
      {said && <span role="status">{said}</span>}
    </div>
  )
}
