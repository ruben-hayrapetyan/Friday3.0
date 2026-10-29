// The week beside setup's questions, as a falling-block board (29 Oct: "the introduction looks extremely like 'ai'...
// try having it be animation based (pixel art might be cool here!)"): the nights close in from either end, the
// example classes blink into place, and work drops into the gaps between them the way Friday fits it. Each piece keeps
// its id from one answer to the next (setupWeek.ts), so a piece already down slides to its new place in steps and only
// new ones fall. The sun and moon beside it sit at your wake and bed times.

import { type CSSProperties, type ReactNode, useRef, useState } from "react"
import { type Bit, FOCUS, VIEW } from "./setupWeek"
import { FLAG, MOON, SUN, Sprite } from "./pixel"

const vars = (v: Record<string, string | number | undefined>) => v as CSSProperties

const DAYS = ["M", "T", "W", "T", "F", "S", "S"]
const MARKS: [number, string][] = [
  [6 * 60, "6am"],
  [12 * 60, "noon"],
  [18 * 60, "6pm"],
  [24 * 60, "12am"],
]
const LEGEND: [string, string][] = [
  ["Sleep", "sleep"],
  ["Classes (an example)", "class"],
  ["Work", "work"],
  ["Free time", "free"],
]

/** Quarter hours from the top of the board (6 AM) to `t`, kept on the board. */
export function quarters(t: number): number {
  return Math.round((Math.min(Math.max(t, VIEW.from), VIEW.to) - VIEW.from) / 15)
}

/** When a piece first drawn falls, in ms: nights first, then the classes, free time, and the work day by day. */
export function introDelay(bit: Bit, order: number): number {
  switch (bit.kind) {
    case "sleep":
      return bit.day * 40
    case "class":
      return 380 + bit.day * 45 + order * 60
    case "free":
      return 760 + bit.day * 40
    case "work":
    case "heavy":
      return 1000 + bit.day * 110 + order * 70
    default:
      return 1800 + order * 60
  }
}

export function Board(props: { bits: Bit[]; stage: string; readout: ReactNode; legend: boolean; wake: number; bed: number }) {
  const { bits, stage, readout, legend, wake, bed } = props
  const lit = FOCUS[stage]
  const born = useRef(performance.now()) // pieces drawn in the board's first moment fall in order; later ones at once
  const intro = performance.now() - born.current < 400
  return (
    <div className="px-board" data-done={stage === "ready" || undefined}>
      <div className="px-board-title">Your week</div>
      <div className="px-frame" aria-hidden>
        <div className="px-head">
          {DAYS.map((d, i) => (
            <span key={i}>{d}</span>
          ))}
        </div>
        <div className="px-body">
          <div className="px-axis">
            {MARKS.map(([t, name]) => (
              <span key={t} style={vars({ "--top": quarters(t) })}>
                {name}
              </span>
            ))}
          </div>
          <div className="px-grid" data-focus={lit ? "" : undefined}>
            {DAYS.map((_, day) => (
              <div key={day} className="px-day" style={vars({ "--d": day })}>
                {bits
                  .filter((b) => b.day === day)
                  .map((b, k) => (
                    <Piece key={b.id} bit={b} order={k} intro={intro} lit={!!lit?.includes(b.kind)} />
                  ))}
              </div>
            ))}
          </div>
          <div className="px-sky">
            <span className="px-mark" style={vars({ "--top": quarters(wake) })} title="Up">
              <Sprite art={SUN} scale={2} />
            </span>
            <span className="px-mark" style={vars({ "--top": quarters(bed) })} title="Bed">
              <Sprite art={MOON} scale={2} />
            </span>
          </div>
        </div>
      </div>
      <p className="px-readout" aria-live="polite">
        {readout}
      </p>
      {legend && (
        <div className="px-legend" aria-hidden>
          {LEGEND.map(([name, kind]) => (
            <span key={name}>
              <i data-kind={kind} />
              {name}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

/** One piece: where it sits in quarter hours, falling (or for a night, closing in) the first time it's drawn. Its delay
 * is fixed when it first appears, so a piece that moves later slides rather than falling again. */
function Piece({ bit, order, intro, lit }: { bit: Bit; order: number; intro: boolean; lit: boolean }) {
  const [delay] = useState(() => (intro ? introDelay(bit, order) : order * 40))
  const top = quarters(bit.start)
  const size = Math.max(1, quarters(bit.end) - top)
  const style = vars({ "--top": top, "--size": size, "--delay": `${delay}ms` })
  if (bit.kind === "due")
    return (
      <span className="px-flag" style={style}>
        <Sprite art={FLAG} scale={3} />
      </span>
    )
  return <span className="px-piece" data-kind={bit.kind} data-from={bit.id.startsWith("sleep-am") ? "top" : undefined} data-lit={lit || undefined} style={style} />
}
