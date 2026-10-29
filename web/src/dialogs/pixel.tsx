// Setup's pixel art (29 Oct: "the introduction looks extremely like 'ai'... try having it be animation based (pixel
// art might be cool here!)"). Each sprite is drawn as rows of letters, one a pixel, in the stage's few colours
// (setup.css's --px- tokens), and drawn as square SVG cells that stay sharp at any size.

import { useEffect, useMemo, useState } from "react"

const INK: Record<string, string> = {
  k: "var(--px-ink)",
  w: "var(--px-white)",
  y: "var(--px-gold)",
  Y: "var(--px-gold-hi)",
  o: "var(--px-gold-lo)",
  g: "var(--px-work)",
  G: "var(--px-work-hi)",
  d: "var(--px-work-lo)",
  b: "var(--px-class)",
  B: "var(--px-class-hi)",
  n: "var(--px-class-lo)",
  p: "var(--px-free)",
  m: "var(--px-moon)",
  M: "var(--px-moon-lo)",
  c: "var(--px-cell)",
  x: "var(--px-ink-3)",
  l: "var(--px-event)",
}

/** A sprite's cells as runs along each row: [x, y, length, colour letter]; "." is left clear. */
export function runs(art: readonly string[]): [number, number, number, string][] {
  const out: [number, number, number, string][] = []
  art.forEach((row, y) => {
    let x = 0
    while (x < row.length) {
      const c = row[x]
      let end = x + 1
      while (end < row.length && row[end] === c) end++
      if (c !== ".") out.push([x, y, end - x, c])
      x = end
    }
  })
  return out
}

export function Sprite({ art, scale = 3, className }: { art: readonly string[]; scale?: number; className?: string }) {
  const cells = useMemo(() => runs(art), [art])
  const w = Math.max(...art.map((r) => r.length))
  return (
    <svg className={className} width={w * scale} height={art.length * scale} viewBox={`0 0 ${w} ${art.length}`} shapeRendering="crispEdges" aria-hidden>
      {cells.map(([x, y, length, c]) => (
        <rect key={`${x}-${y}`} x={x} y={y} width={length} height={1} fill={INK[c] ?? c} />
      ))}
    </svg>
  )
}

export const SUN = [
  "......y......",
  "..y...y...y..",
  "...y.....y...",
  ".....yyy.....",
  "....yYYyy....",
  "...yYYyyyy...",
  "yy.yYyyyyo.yy",
  "...yyyyyyo...",
  "....yyyoo....",
  ".....ooo.....",
  "...y.....y...",
  "..y...y...y..",
  "......y......",
]

export const MOON = [
  "...mmmm..",
  ".mmmmM...",
  ".mmmM....",
  "mmmM.....",
  "mmmM.....",
  "mmmM.....",
  ".mmmM....",
  ".mmmmM...",
  "...mmmm..",
]

/** Friday's ring round its F, as on its icon. */
export const LOGO = [
  ".....yyyyy.....",
  "...yyyyyyyyy...",
  "..yyywwwwwyyy..",
  ".yyywwwwwwwyyo.",
  ".yywwkkkkkwwoo.",
  "yywwwkkwwwwwwoo",
  "yywwwkkwwwwwwoo",
  "yywwwkkkkwwwwoo",
  "yywwwkkwwwwwwoo",
  "yywwwkkwwwwwwoo",
  ".yywwkkwwwwwoo.",
  ".yyywwwwwwwooo.",
  "..yyowwwwwooo..",
  "...ooooooooo...",
  ".....ooooo.....",
]

/** Work dropping into the gap between two classes. */
export const DROP = [
  "...ggg...",
  "...gGg...",
  "...ggd...",
  "....k....",
  "...kkk...",
  ".........",
  "bbb...bbb",
  "bBb...bBb",
  "bbn...bbn",
]

/** Planned again. */
export const AGAIN = [
  "..kkkk...",
  ".k....k.k",
  "k......kk",
  "k.....kkk",
  ".........",
  "kkk.....k",
  "kk......k",
  "k.k....k.",
  "...kkkk..",
]

/** How long things really take. */
export const WATCH = [
  "....kkk....",
  ".....k.....",
  "...kkkkk...",
  "..kkwwwkk..",
  ".kkwwkwwkk.",
  ".kwwwkwwwk.",
  ".kwwwkwwwk.",
  ".kwwwkkkwk.",
  ".kwwwwwwwk.",
  ".kkwwwwwkk.",
  "..kkwwwkk..",
  "...kkkkk...",
]

/** The deadline's flag. */
export const FLAG = [
  "kyyyy",
  "kyYyy",
  "kyyyo",
  "k....",
  "k....",
  "k....",
]

export const CURSOR = ["k...", "kk..", "kkk.", "kkkk", "kkk.", "kk..", "k..."]

export const MORE = ["kkkkkkk", ".kkkkk.", "..kkk..", "...k..."]

export const CHECK = ["......w", ".....ww", "w...ww.", "ww.ww..", ".www...", "..w...."]

export const ARROW = ["....k....", "....kk...", "kkkkkkk..", "kkkkkkkk.", "kkkkkkk..", "....kk...", "....k...."]

/** A sitting's length as a bar filled as far as it is long, out of four hours. */
export function lengthArt(hours: number): string[] {
  const filled = Math.max(2, Math.round(Math.min(1, hours / 4) * 15))
  const row = (on: string, last: string) => `k${on.repeat(filled - 1)}${last}${"w".repeat(15 - filled)}k`
  const edge = "k".repeat(17)
  return [edge, row("G", "G"), row("g", "d"), row("g", "d"), row("d", "d"), edge]
}

/** Four days up to a deadline, its flag on the last; the day the work is done filled in. */
export function earlyArt(days: number): string[] {
  const done = 3 - Math.max(0, Math.min(3, days))
  const cells = (r: number) => [0, 1, 2, 3].map((i) => (i === done ? ["gGg", "ggg", "ddd"][r] : "xxx")).join(".")
  return [
    "................kyyy",
    "................kyYy",
    "................kyyo",
    "................k...",
    "................k...",
    `${cells(0)}.k...`,
    `${cells(1)}.k...`,
    `${cells(2)}.k...`,
  ]
}

/** How far through setup: a block a screen, those done filled and the one you're on blinking. */
export function Steps({ at, of, done }: { at: number; of: number; done: boolean }) {
  return (
    <span className="px-steps" role="progressbar" aria-valuemin={1} aria-valuemax={of} aria-valuenow={at + 1} aria-label="Setup">
      {Array.from({ length: of }, (_, i) => (
        <i key={i} data-state={done || i < at ? "done" : i === at ? "now" : undefined} />
      ))}
    </span>
  )
}

/** How long a letter waits before the next is typed: a beat longer after the end of a sentence or a clause. */
export function letterDelay(letter: string): number {
  return ".!?".includes(letter) ? 180 : ",:;".includes(letter) ? 90 : 18
}

const still = () => typeof window !== "undefined" && !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches

/** A line typed out a letter at a time, as a game's text box does: what's typed so far, whether it's still typing,
 * and a way to show the whole line at once (Return or a click). With reduced motion it's whole from the start. */
export function useTyped(text: string): [string, boolean, () => void] {
  const [typed, setTyped] = useState({ text, n: still() ? text.length : 0 })
  const n = typed.text === text ? typed.n : still() ? text.length : 0
  useEffect(() => {
    if (n >= text.length) return
    const timer = setTimeout(() => setTyped({ text, n: n + 1 }), n ? letterDelay(text[n - 1]) : 120)
    return () => clearTimeout(timer)
  }, [text, n])
  return [text.slice(0, n), n < text.length, () => setTyped({ text, n: text.length })]
}
