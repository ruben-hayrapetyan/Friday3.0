import { readFileSync } from "node:fs"
import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it } from "vitest"
import { blocks, inline } from "./markdown"
import { longDate, type Terms, TermsPage } from "./TermsGate"

const TEXT = readFileSync(new URL("../../../src/friday/core/terms.md", import.meta.url), "utf8")

function terms(accepted: string | null, changes = ["The first terms for Friday."]): Terms {
  return { version: "2026-11-09", text: TEXT, changes, accepted, needed: true }
}

const page = (t: Terms, left = false) =>
  renderToStaticMarkup(<TermsPage terms={t} busy={false} left={left} onAccept={() => {}} onQuit={() => {}} />)

describe("the terms page (glass box: the markdown it draws)", () => {
  it("reads headings, paragraphs and lists", () => {
    const found = blocks("# Title\n\nVersion: 1\n\n## One\n\nA line\nwrapped.\n\n- first\n- second")
    expect(found).toEqual([
      { kind: "title", text: "Title" },
      { kind: "paragraph", text: "Version: 1" },
      { kind: "heading", text: "One" },
      { kind: "paragraph", text: "A line wrapped." },
      { kind: "list", items: ["first", "second"] },
    ])
  })

  it("draws bold, code and links as elements, never as HTML from the text", () => {
    const html = renderToStaticMarkup(<p>{inline("**No** `LICENSE` <https://example.com/x> <b>x</b>")}</p>)
    expect(html).toContain("<strong>No</strong>")
    expect(html).toContain("<code>LICENSE</code>")
    expect(html).toContain('<a href="https://example.com/x" target="_blank" rel="noreferrer">https://example.com/x</a>')
    expect(html).toContain("&lt;b&gt;x&lt;/b&gt;")
  })
})

describe("the terms page (black box: what you see)", () => {
  it("asks a new user to read and accept, with Accept and Quit", () => {
    const html = page(terms(null))
    expect(html).toContain("Before you start, read Friday&#x27;s terms")
    expect(html).toContain(">Accept</button>")
    expect(html).toContain(">Quit</button>")
    expect(html).not.toContain('aria-label="What changed"')
  })

  it("has every section of the terms, in order", () => {
    const html = page(terms(null))
    const headings = [...html.matchAll(/<h2>([^<]+)<\/h2>/g)].map((m) => m[1])
    expect(headings[0]).toBe("1. Agreeing to these terms")
    expect(headings).toContain("3. Friday&#x27;s code")
    expect(headings).toContain("6. Privacy")
    expect(headings.at(-1)).toBe("16. Everything else")
  })

  it("says what changed to someone who accepted an earlier version", () => {
    const html = page(terms("2026-01-01", ["Section 4 now says what a price covers."]))
    expect(html).toContain("Friday&#x27;s terms have changed")
    expect(html).toContain('aria-label="What changed"')
    expect(html).toContain("Section 4 now says what a price covers.")
  })

  it("gives its version as a date", () => {
    expect(page(terms(null))).toContain("Version of 9 November 2026")
    expect(longDate("not a date")).toBe("not a date")
  })

  it("says the tab may be closed once Quit couldn't close it", () => {
    expect(page(terms(null), true)).toContain("You can close this tab now")
  })

  it("puts Accept last, after Quit, so it doesn't move with the note", () => {
    const html = page(terms(null))
    expect(html.indexOf(">Quit</button>")).toBeLessThan(html.indexOf(">Accept</button>"))
    expect(html.indexOf("fr-terms-note")).toBeLessThan(html.indexOf(">Quit</button>"))
  })
})
