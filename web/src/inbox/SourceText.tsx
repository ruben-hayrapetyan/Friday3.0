// The text a suggestion was read from (an email, a page of a syllabus), its own quotes highlighted and the others from
// the same source shaded, scrolled to its own words.

import { useLayoutEffect, useRef } from "react"
import type { Schemas } from "@/api/client"

type Suggestion = Schemas["SuggestionOut"]

/** Where a box `height` tall scrolls to show words `top` down its text: a third of the way down, never above the top. */
export function scrollToShow(top: number, height: number): number {
  return Math.max(0, Math.round(top - height / 3))
}

/** The text it was read from, this suggestion's quotes highlighted and other suggestions' shaded. */
export function SourceText({ s, all }: { s: Suggestion; all: Suggestion[] }) {
  const box = useRef<HTMLDivElement>(null)
  // Its own words in view as it opens (16 Nov: twelve suggestions from one long email each showed the email's top, the
  // same every time, their highlights thousands of characters down; "everything updated besides the black box").
  useLayoutEffect(() => {
    const el = box.current
    const mark = el?.querySelector<HTMLElement>("[data-mine]")
    if (el) el.scrollTop = mark ? scrollToShow(mark.offsetTop, el.clientHeight) : 0
  }, [s.id])
  if (!s.source_text) return null
  const mine = Object.values(s.quotes)
  const theirs = all.filter((o) => o.id !== s.id && o.source_text === s.source_text).flatMap((o) => Object.values(o.quotes))
  const segments = highlight(s.source_text, mine, theirs)
  const [subject, ...rest] = s.origin.split("\n")
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10, maxWidth: 520 }}>
      <span className="fr-kicker">From the source</span>
      <div className="fr-well" style={{ display: "flex", flexDirection: "column", gap: 12, padding: "16px 18px", borderRadius: "var(--radius-lg)" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 2, paddingBottom: 10, boxShadow: "inset 0 -1px 0 color-mix(in srgb, var(--color-text) 7%, transparent)" }}>
          <span style={{ fontWeight: 500 }}>{subject || "Document"}</span>
          <span className="fr-kicker">{rest.join(" ") || s.source}</span>
        </div>
        <div ref={box} aria-label="The source's text" style={{ position: "relative", whiteSpace: "pre-wrap", fontSize: 13, lineHeight: 1.6, color: "var(--color-neutral-300)", maxHeight: 520, overflowY: "auto" }}>
          {segments.map((g, i) => (
            <span
              key={i}
              data-mine={g.kind === "mine" || undefined}
              style={{
                background: g.kind === "mine" ? "color-mix(in srgb, var(--color-accent) 28%, transparent)" : g.kind === "theirs" ? "color-mix(in srgb, var(--color-text) 8%, transparent)" : undefined,
                color: g.kind === "mine" ? "var(--color-text)" : undefined,
                borderRadius: 3,
                padding: g.kind ? "0 2px" : undefined,
              }}
            >
              {g.text}
            </span>
          ))}
        </div>
      </div>
      <span style={{ fontSize: 11, color: "var(--color-neutral-500)" }}>Highlighted text is what Friday read. Other items from this source are shaded lightly.</span>
    </div>
  )
}

export function highlight(text: string, mine: string[], theirs: string[]): { text: string; kind: "mine" | "theirs" | null }[] {
  const marks: { at: number; end: number; kind: "mine" | "theirs" }[] = []
  for (const [quotes, kind] of [
    [mine, "mine"],
    [theirs, "theirs"],
  ] as const) {
    for (const q of quotes) {
      const at = q ? text.indexOf(q) : -1
      if (at >= 0 && !marks.some((m) => at < m.end && at + q.length > m.at)) marks.push({ at, end: at + q.length, kind })
    }
  }
  marks.sort((a, b) => a.at - b.at)
  const out: { text: string; kind: "mine" | "theirs" | null }[] = []
  let pos = 0
  for (const m of marks) {
    if (m.at > pos) out.push({ text: text.slice(pos, m.at), kind: null })
    out.push({ text: text.slice(m.at, m.end), kind: m.kind })
    pos = m.end
  }
  if (pos < text.length) out.push({ text: text.slice(pos), kind: null })
  return out
}
