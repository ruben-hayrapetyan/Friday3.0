// A page for working on the walk alone (`pnpm dev`, then /src/dialogs/walk/preview.html): ← and → walk between the
// steps; ?i=3 starts at the fourth, ?still=1 cuts instead of walking. Not part of the app's build.

import type { Schemas } from "@/api/client"
import { World } from "./World"

const answers: Schemas["SetupInput"] = {
  wake: "07:30",
  bedtime: "23:30",
  weekend_wake: "09:00",
  weekend_bedtime: "00:30",
  normal_hours: 6,
  most_hours: 9,
  focus_hours: 1.5,
  evening_free: 2,
  evening_from: "19:00",
  weekend_free: 4,
  finish_early_days: 1,
  brief: true,
  calendars: [],
}
const STEPS = ["hello", "wake", "work", "heavy", "focus", "deadline", "evening", "bed", "weekend", "brief", "ai", "bring", "calendars", "build", "reveal", "start"]
const params = new URLSearchParams(location.search)
const canvas = document.querySelector("canvas") as HTMLCanvasElement
const say = document.getElementById("say") as HTMLElement
const t0 = performance.now()
const world = new World(canvas, { still: params.get("still") === "1", onReady: () => (say.textContent += ` · ready in ${Math.round(performance.now() - t0)}ms`) })
// ?w=1080&h=675 draws at that size (a landscape window on a portrait screen)
const size = params.get("w") ? [Number(params.get("w")), Number(params.get("h") ?? 675)] : null
if (size) Object.assign(canvas.style, { width: `${size[0]}px`, height: `${size[1]}px` })
const fit = () => (size ? world.resize(size[0], size[1]) : world.resize(innerWidth, innerHeight))
fit()
addEventListener("resize", fit)
world.setShift(Number(params.get("shift") ?? 0), Number(params.get("up") ?? 0))
let i = Number(params.get("i") ?? 0)
const go = (back = false) => {
  world.go(STEPS[i], answers, back)
  say.textContent = `${i} ${STEPS[i]}`
}
go()
addEventListener("keydown", (e) => {
  if (e.key === "ArrowRight" && i < STEPS.length - 1) {
    i++
    go()
  } else if (e.key === "ArrowLeft" && i > 0) {
    i--
    go(true)
  } else if (e.key === " ") world.hurry()
})
// walk.set({ wake: "06:30" }) changes an answer, as a click in setup would
const set = (change: Partial<typeof answers>) => {
  Object.assign(answers, change)
  world.update({ ...answers })
}
Object.assign(window, { walk: { world, answers, set, step: (n: number) => ((i = n), go()) } })
