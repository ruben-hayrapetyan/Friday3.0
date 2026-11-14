// Quick taps on − and + (9 Nov: overshooting and going back did "some weird behavior with the time").
import { describe, expect, it } from "vitest"
import { NO_STEPS, type StepEvent, type Steps, shownOf, steps } from "./useSteps"

const run = (events: StepEvent[], from: Steps = NO_STEPS) => events.reduce(steps, from)

describe("what the stepper shows (black box)", () => {
  it("adds up taps on the spot", () => {
    const s = run([{ kind: "set", to: 75 }, { kind: "set", to: 90 }, { kind: "set", to: 105 }])
    expect(shownOf(s, 60)).toBe(105)
  })

  it("keeps showing what you set once it's sent, until the server says so", () => {
    const sent = run([{ kind: "set", to: 120 }, { kind: "send", server: 60 }])
    expect(shownOf(sent, 60)).toBe(120) // before: back to 60 until the answer came
    expect(shownOf(run([{ kind: "server", value: 120 }], sent), 120)).toBe(120)
  })

  it("counts a tap back after an overshoot from what you see, not the old number", () => {
    const sent = run([{ kind: "set", to: 120 }, { kind: "send", server: 60 }])
    const back = steps(sent, { kind: "set", to: (shownOf(sent, 60) as number) - 15 })
    expect(shownOf(back, 60)).toBe(105) // before: 60 − 15 = 45
  })

  it("puts back what was there when the save fails", () => {
    const sent = run([{ kind: "set", to: 120 }, { kind: "send", server: 60 }, { kind: "drop" }])
    expect(shownOf(sent, 60)).toBe(60)
  })
})

describe("the steps (glass box)", () => {
  it("sends nothing when nothing was set", () => expect(steps(NO_STEPS, { kind: "send", server: 60 })).toEqual(NO_STEPS))
  it("a server value the same as when it was sent changes nothing", () => {
    const sent = run([{ kind: "set", to: 120 }, { kind: "send", server: 60 }])
    expect(steps(sent, { kind: "server", value: 60 })).toEqual(sent)
  })
  it("the server's value moving clears what was sent, the taps since stay", () => {
    const s = run([{ kind: "set", to: 120 }, { kind: "send", server: 60 }, { kind: "set", to: 135 }, { kind: "server", value: 120 }])
    expect(s).toEqual({ pending: 135, sent: null, from: null })
  })
})
