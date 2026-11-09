// The terms as you read them: the little markdown terms.md uses (headings, paragraphs, bullets, **bold**, `code`
// and <links>), drawn as elements, never as HTML from a string.

import type { ReactNode } from "react"

export type Block =
  | { kind: "title" | "heading"; text: string }
  | { kind: "paragraph"; text: string }
  | { kind: "list"; items: string[] }

/** The document as blocks: `# ` is the title, `## ` a heading, `- ` lines a list, the rest paragraphs. */
export function blocks(markdown: string): Block[] {
  const out: Block[] = []
  for (const chunk of markdown.split(/\n\s*\n/)) {
    const lines = chunk.split("\n").filter((l) => l.trim())
    if (!lines.length) continue
    if (lines[0].startsWith("# ")) out.push({ kind: "title", text: lines[0].slice(2).trim() })
    else if (lines[0].startsWith("## ")) out.push({ kind: "heading", text: lines[0].slice(3).trim() })
    else if (lines.every((l) => l.startsWith("- "))) out.push({ kind: "list", items: lines.map((l) => l.slice(2).trim()) })
    else out.push({ kind: "paragraph", text: lines.join(" ") })
  }
  return out
}

const INLINE = /\*\*([^*]+)\*\*|`([^`]+)`|<(https?:\/\/[^>\s]+)>/g

/** A line's **bold**, `code` and <https://…> links as elements. */
export function inline(text: string): ReactNode[] {
  const out: ReactNode[] = []
  let at = 0
  for (const m of text.matchAll(INLINE)) {
    if (m.index > at) out.push(text.slice(at, m.index))
    const key = out.length
    if (m[1]) out.push(<strong key={key}>{m[1]}</strong>)
    else if (m[2]) out.push(<code key={key}>{m[2]}</code>)
    else out.push(<a key={key} href={m[3]} target="_blank" rel="noreferrer">{m[3]}</a>)
    at = m.index + m[0].length
  }
  if (at < text.length) out.push(text.slice(at))
  return out
}
