import { describe, expect, it } from "vitest"
import type { Schemas } from "@/api/client"
import { withoutAsking } from "./AskClaude"

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
