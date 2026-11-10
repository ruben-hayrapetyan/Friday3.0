// Friday's terms before anything else (PROGRESS.md C71, 9 Nov: everyone accepts them, and people already using
// Friday get "a popup on their screen" and must accept before going on). Friday stays locked on this page until you
// press Accept; Quit closes Friday, your data untouched. When the terms change, it comes back with what changed.

import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { type Output, query } from "@/api/client"
import { useCommand } from "@/hooks/useCommand"
import { inMacApp } from "@/settings/MacAccounts"
import { blocks, inline } from "./markdown"

export type Terms = Output<"terms">

export const useTerms = () => useQuery({ queryKey: ["terms"], queryFn: () => query("terms") })

/** "2026-11-09" (or "2026-11-09.2") as "9 November 2026". */
export function longDate(version: string): string {
  const day = version.slice(0, 10) // "2026-11-09.2", a second version that day, is that day too
  const d = new Date(`${day}T12:00:00Z`)
  return Number.isNaN(d.getTime()) ? version : d.toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" })
}

type Bridge = { webkit?: { messageHandlers?: { friday?: { postMessage: (m: unknown) => void } } } }

/** Quit: the Mac app closes; a browser tab closes if it can, else says it may be closed. */
function quit(): boolean {
  if (inMacApp()) {
    ;(window as unknown as Bridge).webkit?.messageHandlers?.friday?.postMessage({ quit: true })
    return true
  }
  window.close()
  return false
}

export function TermsGate({ terms }: { terms: Terms }) {
  const client = useQueryClient()
  const accept = useCommand("terms_accept", { quiet: true })
  const [busy, setBusy] = useState(false)
  const [left, setLeft] = useState(false)
  const onAccept = async () => {
    setBusy(true)
    client.setQueryData<Terms>(["terms"], { ...terms, accepted: terms.version, needed: false }) // in at once
    if (!(await accept({ version: terms.version }))) {
      setBusy(false)
      await client.invalidateQueries({ queryKey: ["terms"] }) // refused (changed while open): read them again
    }
  }
  return <TermsPage terms={terms} busy={busy} left={left} onAccept={onAccept} onQuit={() => setLeft(!quit())} />
}

export function TermsPage({ terms, busy, left, onAccept, onQuit }: { terms: Terms; busy: boolean; left: boolean; onAccept: () => void; onQuit: () => void }) {
  const again = terms.accepted !== null && terms.accepted !== undefined
  const body = blocks(terms.text).filter((b) => !(b.kind === "heading" && b.text === "What changed"))
  const changes = new Set(terms.changes)
  return (
    <main className="fr-terms" aria-labelledby="fr-terms-title">
      <div className="fr-terms-sheet">
        <p className="fr-terms-lead" id="fr-terms-title">
          {again ? "Friday's terms have changed. Read what's new and accept them to keep using Friday." : "Before you start, read Friday's terms and accept them to use Friday."}
        </p>
        {again && terms.changes.length > 0 && (
          <section className="fr-terms-changes" aria-label="What changed">
            <h2>What changed</h2>
            <ul>{terms.changes.map((c) => <li key={c}>{inline(c)}</li>)}</ul>
          </section>
        )}
        <article className="fr-terms-text">
          {body.map((b, n) => {
            if (b.kind === "title") return <h1 key={n}>{b.text}</h1>
            if (b.kind === "heading") return <h2 key={n}>{b.text}</h2>
            if (b.kind === "list") {
              if (b.items.every((i) => changes.has(i))) return null // shown above, or a first version's note
              return <ul key={n}>{b.items.map((i) => <li key={i}>{inline(i)}</li>)}</ul>
            }
            if (b.text.startsWith("Version: ")) return <p key={n} className="fr-kicker">Version of {longDate(b.text.slice(9))}</p>
            return <p key={n}>{inline(b.text)}</p>
          })}
        </article>
      </div>
      <footer className="fr-terms-bar">
        <span className="fr-terms-note">{left ? "You can close this tab now. Your data stays on your computer." : "Your data stays on your computer either way."}</span>
        <button type="button" className="btn btn-ghost" onClick={onQuit}>
          Quit
        </button>
        <button type="button" className="btn btn-primary fr-press" onClick={onAccept} disabled={busy}>
          Accept
        </button>
      </footer>
    </main>
  )
}
