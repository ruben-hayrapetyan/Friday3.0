// Pro tips (#23, 24 Nov, the user: "a popup on the bottom right corner that just slides in for 5s. they should be very
// short and just tell the user on features that they could be missing out based on their usage. don't tell them that
// its based on the usage"; then "the pro tips should show up for 10seconds and have a 'take me there' button"). The
// server picks the tip (commands/tips.py: at most one a day, the same one at most three times a week apart); here it
// slides in a few seconds after Friday opens, stays ten seconds and slides out. "Take me there" opens the page the
// feature is on. Never over the tour, Setup or a dialog, and above the Now bar.

import { useEffect, useRef, useState } from "react"
import { useNavigate } from "react-router"
import { command, query, type Schemas } from "@/api/client"
import { Icon } from "@/components/fr/controls"
import { useShell } from "./ShellContext"

export const TIP_AFTER_MS = 4000 // after Friday opens: the page has settled
export const TIP_FOR_MS = 10_000 // the user's ten seconds (24 Nov: five, then "10seconds")
const OUT_MS = 260 // the slide out

type Tip = Schemas["TipOut"]

/** Where the tip sits: the bottom right, above the Now bar when it's there. */
function bottom(): number {
  const dock = document.querySelector("[data-tour=now]")?.getBoundingClientRect()
  return dock && dock.height > 0 ? Math.max(24, window.innerHeight - dock.top + 12) : 24
}

export function ProTip() {
  const { dialog, tour } = useShell()
  const navigate = useNavigate()
  const [tip, setTip] = useState<Tip | null>(null)
  const [leaving, setLeaving] = useState(false)
  const busy = useRef(false)
  busy.current = tour || dialog !== null

  // once a load: asked a few seconds in, and shown only if nothing else is in front
  useEffect(() => {
    const ask = window.setTimeout(async () => {
      if (busy.current) return
      try {
        const found = await query("tips")
        if (!found.id || busy.current) return
        setTip(found)
        void command("tip_shown", { id: found.id }).catch(() => {})
      } catch {
        // no tip this time
      }
    }, TIP_AFTER_MS)
    return () => window.clearTimeout(ask)
  }, [])

  // five seconds, then out
  useEffect(() => {
    if (!tip) return
    const out = window.setTimeout(() => setLeaving(true), TIP_FOR_MS)
    return () => window.clearTimeout(out)
  }, [tip])
  useEffect(() => {
    if (!leaving) return
    const gone = window.setTimeout(() => setTip(null), OUT_MS)
    return () => window.clearTimeout(gone)
  }, [leaving])

  if (!tip?.text) return null
  return (
    <div role="status" className="fr-tip" data-leaving={leaving ? "" : undefined} style={{ bottom: bottom() }}>
      <Icon name="lightbulb" size={15} style={{ flex: "none", color: "var(--fr-mark)", marginTop: 2 }} />
      <span style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", gap: 8, minWidth: 0 }}>
        <span>{tip.text}</span>
        {tip.page && (
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => {
              navigate(tip.page!)
              setLeaving(true)
            }}
            style={{ fontSize: 12, padding: "3px 10px", minHeight: 0 }}
          >
            Take me there
          </button>
        )}
      </span>
    </div>
  )
}
