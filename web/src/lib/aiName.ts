// The connected AI's name inside a sentence (3 Nov: "for non-claude systems, does it still say ask claude?"). The
// server names it "Claude", "GPT", "Gemini", "Grok", "Muse", or "AI" for one Friday has no name for; "AI" reads as
// "the AI" in a sentence, so nothing says "AI proposes" or "AI's guess".

/** The AI as said mid-sentence: "Gemini proposes", "the AI proposes". */
export function spoken(name: string): string {
  return name === "AI" ? "the AI" : name
}

/** Its, for what it chose: "Gemini's guess", "the AI's guess". */
export function whose(name: string): string {
  return `${spoken(name)}'s`
}
