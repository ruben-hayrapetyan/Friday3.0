// "Use Touch ID next time?" as a bar inside Friday (HOSTED.md S4; H94): after signing in by email or Google, in a
// browser with no passkey that hasn't said Not now. It replaces the page that stood between the link and Friday.

import { useEffect, useState } from "react"
import { Icon } from "@/components/fr/controls"
import { useToast } from "@/components/Toasts"
import { addPasskey, canMakePasskeys } from "@/api/passkeys"
import { passkeyLater, whoAmI } from "@/api/session"

/** Whether to offer: a hosted Friday that says so, in a window that can make passkeys (not the Mac app's). */
export function shouldOffer(me: { offer_passkey?: boolean } | null, canMake: boolean): boolean {
  return Boolean(me?.offer_passkey) && canMake
}

export function PasskeyOffer({ hidden = false }: { hidden?: boolean }) {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const toast = useToast()
  useEffect(() => {
    void whoAmI().then((me) => setOpen(shouldOffer(me, canMakePasskeys())))
  }, [])
  if (!open || hidden) return null
  const later = () => {
    setOpen(false) // at once; the server remembers after (optimistic, as every click is)
    void passkeyLater()
  }
  const add = async () => {
    setBusy(true)
    try {
      const name = await addPasskey()
      setOpen(false)
      toast({ message: `Passkey added: ${name}. Next time Touch ID signs you in.` })
    } catch (error) {
      const cancelled = error instanceof Error && error.name === "NotAllowedError"
      if (!cancelled) toast({ message: `Couldn't add a passkey: ${String((error as Error).message ?? error)}`, tone: "error" })
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="fr-float" role="status" style={{ position: "absolute", top: 66, left: "50%", transform: "translateX(-50%)", zIndex: 8, display: "flex", gap: 10, alignItems: "center", padding: "8px 12px", maxWidth: "calc(100% - 24px)", flexWrap: "wrap" }}>
      <span style={{ textWrap: "pretty" }}>
        <b>Use Touch ID next time?</b> Sign in without waiting for an email.
      </span>
      <button className="btn btn-primary" disabled={busy} onClick={() => void add()}>
        Add a passkey
      </button>
      <button className="btn btn-secondary" disabled={busy} onClick={later}>
        Not now
      </button>
      <button className="btn btn-icon btn-ghost" onClick={later} aria-label="Not now" style={{ width: 26, height: 26 }}>
        <Icon name="x" />
      </button>
    </div>
  )
}
