// @vitest-environment happy-dom
// Replanning in motion, on a page (glide.ts's useGlide): when a new plan moves a block, the block slides from where it
// was; one that's new fades in; nothing slides for the same plan, a new week, a window of another width, a block
// you just placed yourself, or with reduced motion. The boxes' places are made up here, as a browser would measure
// them.
import { cleanup, render } from "@testing-library/react"
import { useRef } from "react"
import { afterEach, describe, expect, it } from "vitest"
import { placedByHand, useGlide } from "./glide"

type Box = { key: string; x: number; y: number }

let width = 900
const animated: { key: string; frames: Keyframe[] }[] = []

function rect(x: number, y: number, w: number, h: number): DOMRect {
  return { x, y, left: x, top: y, width: w, height: h, right: x + w, bottom: y + h, toJSON: () => ({}) } as DOMRect
}

/** The calendar's panel with its boxes where `boxes` says, each answering for where it is and how it moves. */
function Calendar({ plan, place, boxes, day }: { plan: unknown; place: string; boxes: Box[]; day?: boolean }) {
  const panel = useRef<HTMLDivElement>(null)
  useGlide(panel, plan, place)
  const measured = (b: Box) => (el: HTMLDivElement | null) => {
    if (!el) return
    el.getBoundingClientRect = () => rect(b.x, b.y, 100, 40)
    el.animate = ((frames: Keyframe[]) => (animated.push({ key: b.key, frames }), {}) as Animation) as typeof el.animate
  }
  const inside = boxes.map((b) => <div key={b.key} data-block-key={b.key} ref={measured(b)} />)
  return (
    <div
      ref={(el) => {
        panel.current = el
        if (el) el.getBoundingClientRect = () => rect(0, 0, width, 800)
      }}
    >
      {day ? (
        <div
          data-top-min={String(1440 * 20000 + 480)}
          ref={(el) => {
            if (el) el.getBoundingClientRect = () => rect(0, 0, 100, 800)
          }}
        >
          {inside}
        </div>
      ) : (
        inside
      )}
    </div>
  )
}

afterEach(() => {
  cleanup()
  animated.length = 0
  width = 900
})

describe("blocks sliding to where a new plan puts them", () => {
  it("slides a moved block from where it was, and fades in a new one", () => {
    const view = render(<Calendar plan={1} place="week" boxes={[{ key: "T4@2026-11-16T09:00", x: 0, y: 100 }]} />)
    view.rerender(
      <Calendar
        plan={2}
        place="week"
        boxes={[
          { key: "T4@2026-11-16T10:00", x: 0, y: 148 },
          { key: "T7@2026-11-17T09:00", x: 200, y: 100 },
        ]}
      />,
    )
    const slid = animated.find((a) => a.key.startsWith("T4"))
    expect(slid?.frames[0]).toMatchObject({ transform: "translate(0px, -48px)" })
    expect(slid?.frames[1]).toMatchObject({ transform: "translate(0, 0)" })
    expect(animated.find((a) => a.key.startsWith("T7"))?.frames).toEqual([{ opacity: 0 }, { opacity: 1 }])
  })

  it("places a box by its day's clock when it's in a day column", () => {
    const view = render(<Calendar day plan={1} place="week" boxes={[{ key: "F9", x: 0, y: 100 }]} />)
    view.rerender(<Calendar day plan={2} place="week" boxes={[{ key: "F9", x: 0, y: 160 }]} />)
    expect(animated).toHaveLength(1)
    expect(animated[0].frames[0]).toMatchObject({ transform: "translate(0px, -60px)" })
  })

  it("leaves what didn't move where it is", () => {
    const view = render(<Calendar plan={1} place="week" boxes={[{ key: "F9", x: 0, y: 100 }]} />)
    view.rerender(<Calendar plan={2} place="week" boxes={[{ key: "F9", x: 0, y: 100 }]} />)
    expect(animated).toHaveLength(0)
  })

  it("slides nothing for the same plan, another week, or another width", () => {
    const view = render(<Calendar plan={1} place="week" boxes={[{ key: "F9", x: 0, y: 100 }]} />)
    view.rerender(<Calendar plan={1} place="week" boxes={[{ key: "F9", x: 0, y: 200 }]} />)
    view.rerender(<Calendar plan={2} place="next week" boxes={[{ key: "F9", x: 0, y: 300 }]} />)
    width = 700
    view.rerender(<Calendar plan={3} place="next week" boxes={[{ key: "F9", x: 0, y: 400 }]} />)
    expect(animated).toHaveLength(0)
  })

  it("doesn't slide a block you just placed yourself: it's where you let go", () => {
    placedByHand(42)
    const view = render(<Calendar plan={1} place="week" boxes={[{ key: "T42@2026-11-16T09:00", x: 0, y: 100 }]} />)
    view.rerender(<Calendar plan={2} place="week" boxes={[{ key: "T42@2026-11-16T11:00", x: 0, y: 196 }]} />)
    expect(animated).toHaveLength(0)
  })

  it("keeps still with reduced motion", () => {
    const was = window.matchMedia
    window.matchMedia = ((q: string) => ({ matches: q.includes("reduce"), addEventListener() {}, removeEventListener() {} })) as unknown as typeof window.matchMedia
    try {
      const view = render(<Calendar plan={1} place="week" boxes={[{ key: "F9", x: 0, y: 100 }]} />)
      view.rerender(<Calendar plan={2} place="week" boxes={[{ key: "F9", x: 0, y: 200 }]} />)
      expect(animated).toHaveLength(0)
    } finally {
      window.matchMedia = was
    }
  })
})
