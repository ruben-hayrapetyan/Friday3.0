// The connected AI's name in sentences: never "Claude" when it isn't Claude (3 Nov).
import { describe, expect, it } from "vitest"
import { spoken, whose } from "./aiName"

const NAMES = ["Claude", "GPT", "Gemini", "Grok", "Muse"] // the server's NAMES, apart from "AI"

describe("glass box", () => {
  it("a named AI is said by its name", () => {
    for (const n of NAMES) expect(spoken(n)).toBe(n)
  })
  it("an unnamed one is the AI", () => {
    expect(spoken("AI")).toBe("the AI")
    expect(whose("AI")).toBe("the AI's")
  })
})

describe("black box", () => {
  it("what a non-Claude AI chose never says Claude", () => {
    for (const n of [...NAMES.slice(1), "AI"]) expect(whose(n)).not.toContain("Claude")
  })
  it("it reads as a sentence", () => {
    expect(`${whose("Gemini")} guess`).toBe("Gemini's guess")
    expect(`${spoken("AI")} proposes`).toBe("the AI proposes")
  })
})
