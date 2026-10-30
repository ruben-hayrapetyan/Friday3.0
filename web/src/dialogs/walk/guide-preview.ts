// The guide alone (`pnpm dev`, then /src/dialogs/walk/guide.html): ← and → go through what they do; guide.cue({...})
// tries one. Not part of the build.

import { type Cue, type Gesture, Guide } from "./Guide"

const canvas = document.querySelector("canvas") as HTMLCanvasElement
const guide = new Guide(canvas)
const fit = () => guide.resize(innerWidth)
fit()
addEventListener("resize", fit)
const centre = (id: string) => {
  const r = (document.getElementById(id) as HTMLElement).getBoundingClientRect()
  return { x: r.left + r.width / 2, y: r.top + r.height / 2 }
}
const nav = (document.getElementById("nav") as HTMLElement).getBoundingClientRect()
const mid = innerWidth * 0.5
const spots: Omit<Cue, "gesture">[] & { gesture: Gesture }[] = [
  { x: mid, gesture: "wave", jump: true, cheer: true, after: "heart" },
  { x: 124, gesture: "point", aim: centre("nav"), sweep: { top: nav.top + 20, bottom: nav.bottom - 240 } },
  { x: mid, gesture: "drag" },
  { x: mid, gesture: "timer" },
  { x: mid, gesture: "worry", sign: "sweat" },
  { x: innerWidth - 80, gesture: "point", aim: centre("menu"), jump: true },
  { x: mid, gesture: "search" },
  { x: mid, gesture: "watch" },
  { x: mid, gesture: "write" },
  { x: mid, gesture: "mail", after: "heart" },
  { x: mid, gesture: "book" },
  { x: mid, gesture: "think", sign: "?", after: "!" },
  { x: mid, gesture: "eureka", sign: "!" },
  { x: mid, gesture: "yawn", sign: "z" },
  { x: mid, gesture: "fix" },
  { x: innerWidth - 230, gesture: "dance", jump: true, cheer: true, shades: true },
]
let i = 0
const go = () => guide.cue(spots[i] as Cue)
go()
addEventListener("keydown", (e) => {
  if (e.key === "ArrowRight") i = Math.min(spots.length - 1, i + 1)
  else if (e.key === "ArrowLeft") i = Math.max(0, i - 1)
  else return
  go()
})
Object.assign(window, { guide, step: (n: number) => ((i = n), go()) })
