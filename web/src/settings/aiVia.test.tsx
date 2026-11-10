import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it } from "vitest"
import { type AiState, ClaudeSetup } from "./AiConnect"

// The choice between Claude Code and an API key (C95, 10 Nov: "right now it is very hard/impossible for friday users
// to input an api key for an ai that is using the cli").
const base: AiState = { provider: "claude", name: "Claude", ready: true, key: false, cli: true, command: "claude", via: "command", why: null, note: null, base_url: null }

function shown(ai: Partial<AiState>): string {
  return renderToStaticMarkup(
    <QueryClientProvider client={new QueryClient()}>
      <ClaudeSetup ai={{ ...base, ...ai }} />
    </QueryClientProvider>,
  )
}

describe("asking Claude through Claude Code or an API key", () => {
  it("offers both when Claude Code is installed, the chosen one pressed", () => {
    const html = shown({})
    expect(html).toMatch(/role="radiogroup" aria-label="Ask Claude through"/)
    expect(html).toContain("Claude Code on this Mac")
    expect(html).toContain("An API key")
    expect(html.match(/aria-checked="true"/g)).toHaveLength(1)
    expect(html.indexOf('aria-checked="true"')).toBeLessThan(html.indexOf("Claude Code on this Mac"))
  })
  it("with Claude Code chosen, still shows where a key goes, as a backup", () => {
    const html = shown({})
    expect(html).toContain("Anthropic API key")
    expect(html).toContain("A backup, used only if Claude Code fails.")
  })
  it("with the key chosen, asks for the key and says nothing of a backup", () => {
    const html = shown({ via: "key", ready: false })
    expect(html).toContain("Anthropic API key")
    expect(html).not.toContain("A backup")
    expect(html.indexOf('aria-checked="true"')).toBeGreaterThan(html.indexOf("Claude Code on this Mac"))
  })
  it("without Claude Code, there's no choice: only the key, and how to get Claude Code", () => {
    const html = shown({ cli: false, command: null, ready: false })
    expect(html).not.toContain("radiogroup")
    expect(html).toContain("Claude Code isn’t installed here")
    expect(html).toContain("Anthropic API key")
  })
})
