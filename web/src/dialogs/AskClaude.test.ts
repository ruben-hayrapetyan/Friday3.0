import { describe, expect, it } from "vitest"
import type { Schemas } from "@/api/client"
import { applied, begin, settle } from "./asking"
import { ticked, withoutAsking } from "./AskClaude"

const action = (command: string, event: boolean, error: string | null = null) => ({ sentence: command, command, input: {}, error, event }) as Schemas["ProposedAction"]

describe("which of Claude's proposals apply without asking", () => {
  const answer = [action("edit", true), action("add", false), action("drop", true, "id: no such item"), action("repeat", true), action("rule_add", false)]

  it("with the switch on, only changes to calendar events that would run", () => {
    expect(withoutAsking(answer, true)).toEqual([0, 3])
  })

  it("with it off, none: everything waits for Apply", () => {
    expect(withoutAsking(answer, false)).toEqual([])
  })
})

describe("an answer that came while the window was closed (8 Nov: birthdays added twice)", () => {
  const birthdays = [action("add", true), action("add", true), action("add", true), action("rule_add", false)]

  it("opened from its toast, what already ran shows done and isn't ticked to apply again", () => {
    let q = settle(begin("add mom, dad and serge's birthdays", "anything", 0, 7), 7, { reply: "", actions: birthdays })
    const now = withoutAsking(birthdays, true)
    q = applied(q, 7, { at: now, ids: [1, 2, 3] })
    expect(q?.applied?.at).toEqual([0, 1, 2])
    expect(ticked(birthdays, q?.applied?.at)).toEqual([3]) // only the rule waits for Apply
  })

  it("with the switch off nothing ran, so everything is ticked for you to apply", () => {
    expect(ticked(birthdays, withoutAsking(birthdays, false))).toEqual([0, 1, 2, 3])
  })
})
