import { describe, expect, it } from "vitest"
import { highlight } from "./InboxPage"

describe("source highlighting", () => {
  it("marks this suggestion's quotes strongly and the others' lightly, without overlaps", () => {
    const text = "PS5 is due Friday at 5pm. The quiz is Monday."
    const out = highlight(text, ["Friday at 5pm"], ["Monday", "Friday"])
    expect(out).toEqual([
      { text: "PS5 is due ", kind: null },
      { text: "Friday at 5pm", kind: "mine" },
      { text: ". The quiz is ", kind: null },
      { text: "Monday", kind: "theirs" },
      { text: ".", kind: null },
    ])
  })
})
