// A question to your AI that outlives its window (3 Nov).
import { describe, expect, it } from "vitest"
import type { Schemas } from "@/api/client"
import { applied, begin, fail, settle, stop, waiting } from "./asking"

const answer = (reply: string) => ({ reply, actions: [] }) as Schemas["AskClaudeOut"]
const q = begin("no mornings", "rule", 1000, 1)

describe("glass box", () => {
  it("begins asking, with when it began", () => {
    expect(q).toEqual({ id: 1, text: "no mornings", purpose: "rule", began: 1000, state: "asking" })
  })
  it("the answer to the question waited on is kept", () => {
    expect(settle(q, 1, answer("ok"))).toMatchObject({ state: "answered", answer: { reply: "ok" } })
  })
  it("what of an answer ran by itself is kept with it, for that answer only", () => {
    const answered = settle(q, 1, answer("ok"))
    expect(applied(answered, 1, { at: [0, 2], ids: [41, 42] })).toMatchObject({ applied: { at: [0, 2], ids: [41, 42] } })
    expect(applied(answered, 2, { at: [0], ids: [41] })).toBe(answered) // another question's
    expect(applied(q, 1, { at: [0], ids: [41] })).toBe(q) // not answered yet
  })
  it("a failure says why", () => {
    expect(fail(q, 1, "no AI")).toMatchObject({ state: "failed", error: "no AI" })
  })
  it("seconds, then minutes", () => {
    expect(waiting(4.7, "Gemini")).toEqual({ line: "Asking Gemini… 4s", note: null })
    expect(waiting(75, "the AI").line).toBe("Asking the AI… 1m 15s")
  })
  it("once it's slow, says you needn't wait", () => {
    expect(waiting(8, "GPT").note).toMatch(/keep working/)
  })
})

describe("black box", () => {
  it("an answer after Stop is dropped", () => {
    const stopped = stop(q, 1)
    expect(settle(stopped, 1, answer("late"))).toEqual(stopped)
  })
  it("an answer to a question since replaced is dropped", () => {
    const second = begin("move my 5pm", "anything", 2000, 2)
    expect(settle(second, 1, answer("old"))).toEqual(second)
    expect(fail(second, 1, "old error")).toEqual(second)
  })
  it("once answered, a late failure or stop changes nothing", () => {
    const done = settle(q, 1, answer("ok"))
    expect(fail(done, 1, "x")).toEqual(done)
    expect(stop(done, 1)).toEqual(done)
  })
  it("with nothing asked, nothing happens", () => {
    expect(settle(null, 1, answer("x"))).toBeNull()
    expect(stop(null, 1)).toBeNull()
  })
  it("whatever happens in whatever order, it ends in one state and keeps its question", () => {
    const steps = [(a: ReturnType<typeof settle>) => settle(a, 1, answer("ok")), (a: ReturnType<typeof settle>) => fail(a, 1, "e"), (a: ReturnType<typeof settle>) => stop(a, 1)]
    for (const order of [[0, 1, 2], [1, 0, 2], [2, 0, 1], [2, 1, 0], [0, 2, 1], [1, 2, 0]]) {
      const end = order.reduce((a, i) => steps[i](a), q as ReturnType<typeof settle>)
      expect(["answered", "failed", "stopped"]).toContain(end?.state)
      expect(end?.text).toBe("no mornings")
      expect(end).toEqual(steps[order[0]](q)) // the first thing to happen decides it
    }
  })
})
