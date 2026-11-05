// The account a hosted Friday is signed in as, and Sign out (HOSTED.md S4). Nothing on your own Friday.

import { useEffect, useState } from "react"
import { type Me, signOut, whoAmI } from "@/api/session"

export function Account() {
  const [me, setMe] = useState<Me | null>(null)
  const [leaving, setLeaving] = useState(false)
  useEffect(() => {
    void whoAmI().then(setMe)
  }, [])
  if (!me) return null
  return (
    <div className="fr-row" style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 12px", marginBottom: 18, borderRadius: "var(--radius-md)", background: "var(--color-bg)" }}>
      <span style={{ flex: 1, textWrap: "pretty" }}>
        Signed in as <b>{me.name}</b> ({me.username}, {me.email})
      </span>
      <button
        className="btn"
        disabled={leaving}
        onClick={() => {
          setLeaving(true)
          void signOut()
        }}
      >
        {leaving ? "Signing out…" : "Sign out"}
      </button>
    </div>
  )
}
