// The guide alone (`pnpm dev`, then /src/dialogs/walk/guide.html): ← and → go between the spots. Not part of the build.

import { type Gesture, Guide } from "./Guide"

const canvas = document.querySelector("canvas") as HTMLCanvasElement
const guide = new Guide(canvas)
const fit = () => guide.resize(innerWidth)
fit()
addEventListener("resize", fit)
const centre = (id: string) => {
  const r = (document.getElementById(id) as HTMLElement).getBoundingClientRect()
  return { x: r.left + r.width / 2, y: r.top + r.height / 2 }
}
const spots: [number, Gesture, string | null][] = [
  [innerWidth * 0.4, "wave", null],
  [260, "point", "nav"],
  [innerWidth - 240, "point", "menu"],
  [innerWidth * 0.55, "present", null],
  [innerWidth * 0.5, "think", null],
  [innerWidth * 0.3, "mail", null],
]
let i = 0
const go = () => {
  const [x, gesture, at] = spots[i]
  guide.cue({ x, gesture, aim: at ? centre(at) : null })
}
go()
addEventListener("keydown", (e) => {
  if (e.key === "ArrowRight") i = Math.min(spots.length - 1, i + 1)
  else if (e.key === "ArrowLeft") i = Math.max(0, i - 1)
  else return
  go()
})
Object.assign(window, { guide, step: (n: number) => ((i = n), go()) })
