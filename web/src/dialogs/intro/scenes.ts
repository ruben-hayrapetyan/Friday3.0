// The intro's scenes (Intro.tsx), a frame at a time on the 256 × 144 canvas: Friday's bedroom, the walk to class, the
// library desk, the road to an essay due Friday, the living room at dusk, the park on a Saturday, packing the bag,
// and the week it all makes. Each scene is drawn from your answers as they are this moment, so changing one changes
// the world at once: the window's sky at your alarm, the books on the desk, where Friday finishes the essay.

import type { Schemas } from "@/api/client"
import { ALARM, BAG, CAL, CHECK_FLAG, CHIP, CONTROLLER, DROP, type Face, friday, HEART, LAPTOP, type Legs, MOON, MUG, PAPER, SPARKLE, SUN, WALK, ZZZ } from "./art"
import { arc, dissolve, G, H, isNight, scatter, sky, W } from "./draw"
import { ALL_EVENING, ALL_WEEKEND, bedOf, VIEW, wakeOf, weekOf } from "../setupWeek"

type Answers = Schemas["SetupInput"]

export interface Mem {
  x?: number // Friday's place where it walks between things (the road, the living room, the park)
  books: number[][] // when each book landed on the desk's two piles
}

export interface World {
  step: string
  t: number // ms into this step
  done: number | null // ms since it was answered, while its ending plays
  now: number
  dt: number
  a: Answers
  still: boolean // reduced motion: the last frame of everything
  bag: { ai: boolean; connected: number }
  pick?: string // what was answered, where the ending depends on it (the brief)
  mem: Mem
  fresh?: boolean // a new place: it comes out of the dark
}

const FLOOR = 112
const lerp = (a: number, b: number, s: number) => a + (b - a) * Math.max(0, Math.min(1, s))
const stepped = (s: number, n: number) => Math.floor(Math.max(0, Math.min(1, s)) * n) / n

/** Friday standing (or walking) with its feet at `feet`. */
function fri(g: G, x: number, feet: number, face: Face = "open", legs: Legs = "stand", flip = false): void {
  const bob = legs === "apart" || legs === "together" ? -1 : 0
  g.sprite(friday(face, legs), x, feet - 17 + bob, { flip })
}

/** Open eyes, a blink every few seconds. */
function blinking(w: World, base: Face = "open"): Face {
  return !w.still && w.now % 3200 < 140 ? "blink" : base
}

function walkLegs(w: World, moving: boolean): Legs {
  return moving && !w.still ? WALK[Math.floor(w.now / 110) % 4] : "stand"
}

/** Friday walks toward `target` at `speed` px/s from wherever it was; returns where it is and whether it's moving. */
function toward(w: World, target: number, speed = 90): { x: number; moving: boolean; left: boolean } {
  const from = w.mem.x ?? target
  if (w.still) {
    w.mem.x = target
    return { x: target, moving: false, left: false }
  }
  const dx = target - from
  const move = Math.sign(dx) * Math.min(Math.abs(dx), (speed * w.dt) / 1000)
  w.mem.x = from + move
  return { x: w.mem.x, moving: Math.abs(dx) > 0.5, left: dx < 0 }
}

function zzz(g: G, w: World, x: number, y: number): void {
  if (w.still) return g.sprite(ZZZ, x, y - 8, { swap: { k: "Y" } })
  for (let i = 0; i < 2; i++) {
    const s = ((w.now / 1800 + i / 2) % 1 + 1) % 1
    g.sprite(ZZZ, x + Math.round(s * 8), y - Math.round(s * 16), { alpha: s < 0.85 ? 1 : 0.4, swap: { k: "Y" } })
  }
}

// ---- Friday's room: the bedroom, by the hour ------------------------------------------------------------------------

function wall(minutes: number): string {
  const h = ((minutes % 1440) + 1440) % 1440 / 60
  if (h < 5 || h >= 21.5) return "#3b3a5c"
  if (h < 7 || h >= 19) return "#9d8296"
  return "#e3d3b4"
}

function room(g: G, minutes: number, opts: { lit?: number; bed?: boolean } = {}): void {
  const paper = wall(minutes)
  g.rect(0, 0, W, FLOOR, paper)
  for (let x = 8; x < W; x += 16) g.dither(x, 0, 1, FLOOR, "#00000022")
  // the window, its sky at this hour
  g.rect(140, 14, 8, 66, "p")
  g.rect(204, 14, 8, 66, "p")
  g.dither(140, 14, 8, 66, "r", 1)
  g.dither(204, 14, 8, 66, "r", 1)
  g.rect(148, 18, 56, 52, "w")
  sky(g, 151, 21, 50, 46, minutes)
  g.ctx.save()
  g.ctx.beginPath()
  g.ctx.rect(151, 21, 50, 46)
  g.ctx.clip()
  if (isNight(minutes)) {
    const rnd = scatter(7)
    for (let i = 0; i < 9; i++) g.rect(151 + Math.floor(rnd() * 50), 21 + Math.floor(rnd() * 30), 1, 1, "Y")
    const [mx, my] = arc((minutes + 720) % 1440, 9 * 60, 17 * 60, 151, 21, 40, 26)
    g.sprite(MOON, mx, my)
  } else {
    const [sx, sy] = arc(minutes, 6 * 60, 20 * 60, 146, 18, 50, 34)
    g.sprite(SUN, sx, sy)
  }
  g.ctx.restore()
  g.rect(175, 21, 2, 46, "w")
  g.rect(151, 43, 50, 2, "w")
  // a poster: a mountain at sunrise
  g.rect(52, 22, 30, 36, "k")
  g.rect(54, 24, 26, 32, "P")
  g.rect(60, 30, 6, 6, "y")
  for (let i = 0; i < 12; i++) g.rect(54 + i, 56 - i * 2, 26 - i * 2, 2, i > 8 ? "w" : i % 2 ? "a" : "#6f7590")
  for (let i = 0; i < 6; i++) g.rect(54, 56 - i * 2, 14 - i * 2, 2, i % 2 ? "g" : "d")
  // floor and skirting
  g.rect(0, FLOOR - 2, W, 2, "u")
  g.rect(0, FLOOR, W, H - FLOOR, "t")
  for (let y = FLOOR + 5; y < H; y += 6) g.rect(0, y, W, 1, "u")
  g.dither(120, 124, 110, 8, "l")
  if (opts.bed === false) return opts.lit ? g.shade(opts.lit) : undefined
  // the bed
  g.rect(14, 72, 6, 40, "u")
  g.rect(15, 73, 4, 38, "T")
  g.rect(14, 100, 92, 12, "t")
  g.rect(14, 100, 92, 1, "u")
  g.rect(20, 94, 86, 6, "w")
  g.rect(22, 86, 18, 9, "k")
  g.rect(23, 87, 16, 7, "w")
  // the nightstand
  g.rect(110, 92, 22, 20, "u")
  g.rect(111, 93, 20, 18, "T")
  g.rect(111, 101, 20, 1, "u")
  g.rect(119, 96, 4, 2, "y")
  if (opts.lit) g.shade(opts.lit)
}

function blanket(g: G): void {
  g.rect(26, 90, 80, 16, "b")
  g.rect(26, 90, 80, 2, "B")
  g.rect(26, 104, 80, 2, "n")
  g.dither(26, 92, 80, 12, "n", 1)
}

/** Friday asleep under the blanket. */
function asleep(g: G, w: World): void {
  g.sprite(friday("blink", "none"), 24, 79)
  blanket(g)
  zzz(g, w, 42, 80)
}

function alarm(g: G, w: World, ringing: boolean): void {
  const shake = ringing && !w.still ? (Math.floor(w.now / 50) % 2 ? 1 : -1) : 0
  g.sprite(ALARM, 116 + shake, 82)
  if (ringing && (w.still || Math.floor(w.now / 200) % 2)) {
    g.text("RING!", 108, 72, "e")
  }
}

function light(minutes: number): number {
  const h = ((minutes % 1440) + 1440) % 1440 / 60
  return h < 5 || h >= 22 ? 0.35 : h < 6.5 || h >= 20 ? 0.18 : 0
}

function titleScene(g: G, w: World): void {
  room(g, 23 * 60 + 50, { lit: 0.5 })
  asleep(g, w)
  g.shade(0.25)
  g.text("FRIDAY", 82, 14, "y", 4, "k")
  g.text("YOUR WEEK, PLANNED", 93, 42, "w", 1, "k")
  if (w.still || Math.floor(w.now / 520) % 2) g.text("PRESS START", 107, 124, "w", 1, "k")
}

function helloScene(g: G, w: World): void {
  room(g, 23 * 60 + 50, { lit: 0.3 })
  // sitting up in bed to say hello, a little bounce in it
  const bob = w.still ? 0 : Math.floor(w.now / 400) % 2
  g.sprite(friday(blinking(w, "happy"), "none"), 24, 72 - bob)
  blanket(g)
  if (!w.still && w.t < 900) g.sprite(SPARKLE, 44, 66 - Math.round(stepped(w.t / 900, 4) * 8))
  alarm(g, w, false)
}

function wakeScene(g: G, w: World): void {
  const wake = minutesOf(w.a.wake)
  const d = w.done
  if (d === null) {
    room(g, wake, { lit: light(wake) })
    asleep(g, w)
    alarm(g, w, false)
    return
  }
  // the alarm rings, Friday jumps out of bed and heads out as the sun comes up
  const m = wake + Math.min(60, d / 50)
  room(g, m, { lit: light(m) * (1 - Math.min(1, d / 2400)) })
  alarm(g, w, d < 900)
  if (d < 800) {
    g.sprite(friday(d < 350 ? "blink" : "open", "none"), 24, 79)
    blanket(g)
    return
  }
  blanket(g)
  if (d < 1300) {
    const s = (d - 800) / 500
    g.sprite(friday("happy", "apart"), lerp(24, 70, s), lerp(79, FLOOR - 17, s) - Math.sin(s * Math.PI) * 30)
    return
  }
  const x = lerp(70, 270, (d - 1450) / 1500)
  fri(g, x, FLOOR, "happy", d < 1450 ? "stand" : WALK[Math.floor(d / 110) % 4])
}

function bedScene(g: G, w: World): void {
  const bed = minutesOf(w.a.bedtime)
  const d = w.done
  room(g, bed, { lit: light(bed) + (d === null ? 0 : lerp(0, 0.45, (d - 1400) / 600)) })
  alarm(g, w, false)
  if (d === null) {
    const yawning = !w.still && w.now % 2600 < 900
    fri(g, 150, FLOOR, yawning ? "yawn" : blinking(w))
    blanket(g)
    if (yawning) g.sprite(ZZZ, 166, 82, { swap: { k: "Y" } })
    return
  }
  if (d < 1000) {
    const s = d / 1000
    blanket(g)
    fri(g, lerp(150, 60, s), FLOOR, "yawn", WALK[Math.floor(d / 110) % 4], true)
    return
  }
  if (d < 1400) {
    const s = (d - 1000) / 400
    g.sprite(friday("blink", "apart"), lerp(60, 24, s), lerp(FLOOR - 17, 79, s) - Math.sin(s * Math.PI) * 18)
    blanket(g)
    return
  }
  asleep(g, w)
}

function briefScene(g: G, w: World): void {
  const m = minutesOf(w.a.wake) + 20
  room(g, m, { lit: light(m) })
  blanket(g)
  alarm(g, w, false)
  const d = w.done
  const x = 160
  if (d === null) {
    fri(g, x, FLOOR, blinking(w, "look"))
    g.sprite(PAPER, x + 14, FLOOR - 15)
    return
  }
  if (w.pick === "on") {
    // reads it, then cheers
    if (d < 1100) {
      fri(g, x, FLOOR, "look")
      g.sprite(PAPER, x + 3, FLOOR - 17)
      return
    }
    const hop = w.still ? 0 : Math.abs(Math.sin(((d - 1100) / 300) * Math.PI)) * 6
    fri(g, x, FLOOR - hop, "happy", "apart")
    if (!w.still) g.sprite(SPARKLE, x - 8, FLOOR - 30 - (Math.floor(d / 150) % 3))
    return
  }
  // tosses it over its shoulder
  const s = Math.min(1, d / 700)
  fri(g, x, FLOOR, "happy")
  g.sprite(PAPER, lerp(x + 14, x + 110, s), FLOOR - 15 - Math.sin(s * Math.PI) * 40)
}

// ---- Outside: the walk to class ------------------------------------------------------------------------------------

const STONE = "#d8cbb0"
const STONE_SHADE = "#b8a98c"
const SLATE = "#5a5f7a"

function clouds(g: G, w: World, y: number): void {
  const at = [0, 90, 170]
  at.forEach((x0, i) => {
    const x = ((x0 + (w.still ? 0 : w.now / (90 + i * 30))) % 300) - 40
    g.rect(x, y + i * 6, 26, 5, "w")
    g.rect(x + 5, y + i * 6 - 3, 14, 4, "w")
    g.rect(x + 2, y + i * 6 + 4, 22, 1, "c")
  })
}

function tree(g: G, x: number, ground: number, size = 1): void {
  g.rect(x + 7 * size, ground - 22 * size, 4 * size, 22 * size, "u")
  g.rect(x, ground - 40 * size, 18 * size, 20 * size, "d")
  g.rect(x + 2 * size, ground - 44 * size, 14 * size, 6 * size, "g")
  g.rect(x + 2 * size, ground - 38 * size, 12 * size, 12 * size, "g")
  g.dither(x + 2 * size, ground - 42 * size, 10 * size, 6 * size, "G")
}

function hills(g: G, y: number): void {
  for (let x = 0; x < W; x += 2) {
    const h = 10 + Math.round(Math.sin(x / 23) * 5 + Math.sin(x / 9) * 2)
    g.rect(x, y - h, 2, h, "#9cc58f")
  }
  g.rect(0, y, W, 4, "#9cc58f")
}

function classesScene(g: G, w: World): void {
  sky(g, 0, 0, W, 100, 9 * 60 + 30)
  g.sprite(SUN, 26, 10)
  clouds(g, w, 14)
  hills(g, 96)
  // the clock tower
  g.rect(134, 30, 18, 70, STONE)
  g.rect(134, 30, 2, 70, STONE_SHADE)
  g.rect(136, 22, 14, 8, STONE_SHADE)
  for (let i = 0; i < 3; i++) g.rect(138 + i * 4, 24, 2, 5, "k")
  for (let i = 0; i < 6; i++) g.rect(137 + i, 20 - i * 2, 12 - i * 2, 2, SLATE)
  g.rect(138, 38, 10, 10, "k")
  g.rect(139, 39, 8, 8, "w")
  g.rect(142, 40, 1, 4, "k")
  g.rect(142, 43, 3, 1, "k")
  // the lecture hall
  g.rect(156, 54, 92, 46, STONE)
  for (let i = 0; i < 12; i++) g.rect(152 + i * 4, 54 - i, 100 - i * 8, 1, i % 3 ? STONE : STONE_SHADE)
  g.rect(152, 54, 100, 2, STONE_SHADE)
  for (let i = 0; i < 5; i++) {
    g.rect(162 + i * 18, 58, 5, 40, "w")
    g.rect(166 + i * 18, 58, 1, 40, "c")
  }
  g.rect(190, 76, 16, 24, "u")
  g.rect(196, 76, 1, 24, "k")
  g.rect(152, 98, 100, 2, STONE_SHADE)
  // grass and the path
  g.rect(0, 100, W, H - 100, "g")
  g.dither(0, 100, W, 3, "G")
  g.rect(0, 112, W, 10, "#e6d3a3")
  g.dither(0, 112, W, 1, "g")
  g.dither(0, 121, W, 1, "g", 1)
  tree(g, 18, 104)
  tree(g, 82, 104)
  // Friday walks to class, and waits at the door, bouncing, while the bell rings
  const s = w.still ? 1 : w.t / 4200
  const hop = s >= 1 && !w.still ? Math.floor(w.now / 300) % 2 : 0
  fri(g, lerp(-18, 190, s), 120 - hop, s < 1 ? "happy" : blinking(w, "happy"), s < 1 ? walkLegs(w, true) : "stand")
  if (!w.still && w.t > 4200 && Math.floor(w.t / 250) % 2 && w.t % 4000 < 1600) g.text("DING", 134, 10, "y", 1, "k")
}

// ---- The library: work, a heavy day, focus ---------------------------------------------------------------------------

const SPINES = ["b", "n", "g", "d", "p", "r", "y", "o", "l", "e", "a"]

function library(g: G): void {
  g.rect(0, 0, W, FLOOR, "#6e4a3a")
  for (const top of [10, 42, 74]) {
    const rnd = scatter(top)
    let x = 2
    while (x < W - 4) {
      const wide = 3 + Math.floor(rnd() * 4)
      const tall = 16 + Math.floor(rnd() * 12)
      const c = SPINES[Math.floor(rnd() * SPINES.length)]
      g.rect(x, top + 28 - tall, wide, tall, c)
      g.rect(x, top + 28 - tall, wide, 1, "w")
      x += wide + (rnd() < 0.15 ? 3 : 1)
    }
    g.rect(0, top + 28, W, 3, "u")
  }
  g.rect(0, FLOOR, W, H - FLOOR, "u")
  for (let y = FLOOR + 6; y < H; y += 7) g.rect(0, y, W, 1, "#3e281c")
}

function desk(g: G): void {
  g.rect(56, 92, 146, 5, "T")
  g.rect(56, 92, 146, 1, "Y")
  g.rect(60, 97, 138, 24, "t")
  g.dither(60, 97, 138, 24, "u", 1)
  g.rect(60, 97, 138, 1, "u")
}

function lamp(g: G): void {
  g.rect(186, 74, 2, 18, "k")
  g.rect(180, 66, 14, 8, "y")
  g.rect(182, 64, 10, 2, "y")
  g.rect(180, 73, 14, 1, "o")
  for (let i = 0; i < 18; i += 2) g.dither(185 - Math.floor(i * 0.7), 74 + i, 4 + Math.floor(i * 1.4), 1, "Y", (i / 2) % 2)
}

/** The books on the desk: a pile for a normal day, and a second, red one for what a heavy day adds. Each new one drops
 * in from above. */
function piles(g: G, w: World, normal: number, extra: number): void {
  const counts = [Math.round(normal), Math.max(0, Math.round(extra))]
  counts.forEach((n, p) => {
    const landed = (w.mem.books[p] ??= [])
    while (landed.length < n) landed.push(w.now)
    landed.length = n
    const x = p === 0 ? 64 : 150
    const colors = p === 0 ? ["b", "g", "p", "l", "y", "n"] : ["e", "r", "o"]
    landed.forEach((at, i) => {
      const y = 92 - 3 * (i + 1)
      const s = w.still ? 1 : stepped((w.now - at) / 260, 6)
      const yy = lerp(-10, y, s)
      g.rect(x + (i % 2), yy, 20, 3, "k")
      g.rect(x + 1 + (i % 2), yy, 18, 2, colors[i % colors.length])
      g.rect(x + 16 + (i % 2), yy, 2, 2, "w")
    })
  })
}

function atDesk(g: G, w: World, face: Face = "open"): void {
  const bob = w.still ? 0 : Math.floor(w.now / 260) % 2
  g.sprite(friday(blinking(w, face), "none"), 120, 78 - bob)
  desk(g)
  const typing = !w.still && Math.floor(w.now / 180) % 2 === 0
  g.sprite(LAPTOP, 100, 84, { swap: typing ? { s: "B", B: "s" } : undefined })
}

function workScene(g: G, w: World): void {
  library(g)
  lamp(g)
  atDesk(g, w)
  piles(g, w, w.a.normal_hours, w.step === "heavy" ? w.a.most_hours - w.a.normal_hours : 0)
  if (w.step === "heavy" && w.a.most_hours >= 10) {
    const y = w.still ? 0 : Math.floor(w.now / 300) % 3
    g.sprite(DROP, 138, 76 + y)
    if (w.a.most_hours >= 13) g.sprite(DROP, 117, 79 + ((y + 1) % 3))
  }
}

/** One sitting as long as your focus, then a coffee break, over and over; how far along, for the clock. */
export function focusCycle(focusHours: number, ms: number): { working: boolean; share: number; minutes: number } {
  const work = Math.max(900, focusHours * 1300)
  const rest = 1500
  const at = ms % (work + rest)
  const round = Math.floor(ms / (work + rest))
  const focus = Math.round(focusHours * 60)
  if (at < work) return { working: true, share: at / work, minutes: round * (focus + 15) + (at / work) * focus }
  return { working: false, share: 1, minutes: round * (focus + 15) + focus + ((at - work) / rest) * 15 }
}

function focusScene(g: G, w: World): void {
  library(g)
  lamp(g)
  const cycle = w.still ? { working: true, share: 1, minutes: 0 } : focusCycle(w.a.focus_hours, w.t)
  piles(g, w, w.a.normal_hours, 0)
  if (cycle.working) {
    atDesk(g, w, "look")
    // the sitting's bar fills over Friday's head
    g.rect(108, 62, 44, 7, "k")
    g.rect(109, 63, 42, 5, "w")
    g.rect(109, 63, Math.round(42 * stepped(cycle.share, 21)), 5, "g")
    g.rect(109, 63, Math.round(42 * stepped(cycle.share, 21)), 1, "G")
  } else {
    // a break: up from the desk with a coffee
    fri(g, 122, 92, blinking(w, "happy"))
    desk(g)
    g.sprite(LAPTOP, 100, 84)
    g.sprite(MUG, 139, 79)
    if (Math.floor(w.now / 200) % 2) g.rect(141, 75, 1, 2, "a")
    else g.rect(142, 74, 1, 2, "a")
    g.text("BREAK", 112, 62, "y")
  }
}

// ---- The road to Friday's deadline ------------------------------------------------------------------------------------

export const SIGNS = [20, 70, 120, 170, 220] // Monday to Friday

/** Where Friday finishes the essay: the day's sign, `early` days before Friday's. */
export function finishAt(early: number): number {
  return SIGNS[Math.max(0, 4 - Math.max(0, Math.min(4, early)))]
}

function deadlineScene(g: G, w: World): void {
  sky(g, 0, 0, W, 100, 14 * 60)
  g.sprite(SUN, 210, 8)
  clouds(g, w, 10)
  hills(g, 96)
  g.rect(0, 96, W, H - 96, "g")
  g.dither(0, 96, W, 3, "G")
  g.rect(0, 106, W, 12, "#e6d3a3")
  g.dither(0, 106, W, 1, "g")
  g.dither(0, 117, W, 1, "g", 1)
  const days = ["MON", "TUE", "WED", "THU"]
  days.forEach((day, i) => {
    const x = SIGNS[i]
    g.rect(x + 8, 78, 2, 30, "u")
    g.rect(x, 72, 18, 9, "k")
    g.rect(x + 1, 73, 16, 7, "w")
    g.text(day, x + 3, 74)
  })
  // Friday at 5pm: the flag
  const fx = SIGNS[4]
  g.rect(fx + 14, 46, 2, 62, "k")
  const wave = w.still ? 0 : Math.floor(w.now / 300) % 2
  g.rect(fx + 16, 46 + wave, 20, 12, "e")
  g.rect(fx + 16, 46 + wave, 20, 1, "#f28a7f")
  g.text("FRI", fx + 20, 49 + wave, "w")
  g.rect(fx - 4, 84, 20, 9, "k")
  g.rect(fx - 3, 85, 18, 7, "w")
  g.text("5PM", fx - 1, 86)
  // Friday walks to the day it'd be done, and plants its flag there
  const target = finishAt(w.a.finish_early_days) + 1
  const at = toward(w, target, 70)
  if (!at.moving) g.sprite(CHECK_FLAG, target + 19, 94, { scale: 2 })
  const d = w.done
  const hop = d !== null && !w.still ? Math.abs(Math.sin((d / 260) * Math.PI)) * 8 : 0
  fri(g, at.x, 112 - hop, d !== null ? "happy" : blinking(w), walkLegs(w, at.moving), at.left)
  if (d !== null) confetti(g, d)
}

function confetti(g: G, d: number): void {
  const rnd = scatter(3)
  const colors = ["y", "e", "b", "g", "p", "l"]
  for (let i = 0; i < 40; i++) {
    const x0 = rnd() * W
    const speed = 30 + rnd() * 50
    const y = -10 + ((d / 1000) * speed + rnd() * 40)
    g.rect(x0 + Math.sin(d / 200 + i) * 3, y, 2, 2, colors[i % colors.length])
  }
}

// ---- Evenings and weekends: a day in fast forward --------------------------------------------------------------------

/** Which part of an evening (or a weekend day) is yours: from, to, in minutes from midnight; null when none is. */
export function freeSpan(a: Answers, weekend: boolean): [number, number] | null {
  const day = weekend ? 5 : 0
  const bed = bedOf(a, day)
  if (weekend) {
    if (a.weekend_free <= 0) return null
    if (a.weekend_free >= ALL_WEEKEND) return [wakeOf(a, day), bed]
    return [Math.max(wakeOf(a, day), bed - a.weekend_free * 60), bed]
  }
  if (a.evening_free <= 0) return null
  const from = minutesOf(a.evening_from)
  return [from, a.evening_free >= ALL_EVENING ? bed : Math.min(bed, from + a.evening_free * 60)]
}

/** The time a day in fast forward has come to: `from` to `to` over a few seconds, then a pause, again. */
export function lapse(ms: number, from: number, to: number, still: boolean): number {
  if (still) return to
  const run = 8000
  const at = ms % (run + 1400)
  return from + Math.min(1, at / run) * (to - from)
}

/** A strip along the top: the hours shown, the part kept free, and where the clock is. */
function strip(g: G, from: number, to: number, free: [number, number] | null, now: number, label: string): void {
  const x0 = 40
  const width = 176
  const at = (m: number) => x0 + ((m - from) / Math.max(1, to - from)) * width
  g.rect(x0 - 2, 3, width + 4, 9, "k")
  g.rect(x0, 5, width, 5, "g")
  if (free) g.rect(at(free[0]), 5, at(free[1]) - at(free[0]), 5, "p")
  g.rect(at(now) - 1, 2, 2, 11, "w")
  g.text(label, 4, 5, "w")
}

function homeScene(g: G, w: World): void {
  const bed = bedOf(w.a, 0)
  const m = lapse(w.t, 17 * 60, bed, w.still)
  const free = freeSpan(w.a, false)
  room(g, m, { bed: false })
  // the desk, the telly and the couch
  g.rect(14, 92, 64, 4, "T")
  g.rect(18, 96, 56, 16, "t")
  g.rect(88, 88, 34, 20, "k")
  const playing = free !== null && m >= free[0] && m < free[1]
  g.rect(90, 90, 30, 16, playing && Math.floor(w.now / 200) % 2 ? "l" : "s")
  if (playing) g.rect(96 + (Math.floor(w.now / 150) % 14), 98, 4, 4, "y")
  g.rect(100, 108, 10, 4, "u")
  g.rect(150, 84, 80, 14, "r")
  g.rect(150, 96, 80, 12, "p")
  g.rect(146, 90, 8, 18, "r")
  g.rect(226, 90, 8, 18, "r")
  g.rect(150, 96, 80, 1, "P")
  const target = playing ? 180 : 30
  const at = toward(w, target, 300)
  if (at.x > 120 && !at.moving) {
    g.sprite(friday(blinking(w, "happy"), "none"), at.x, 84)
    g.rect(150, 98, 80, 10, "p")
    g.rect(150, 98, 80, 1, "P")
    g.sprite(CONTROLLER, at.x + 4, 96)
    if (!w.still) for (let i = 0; i < 2; i++) {
      const s = ((w.now / 1400 + i / 2) % 1 + 1) % 1
      g.sprite(HEART, at.x + 6 + i * 6, 80 - s * 26, { alpha: 1 - s * 0.6 })
    }
  } else if (at.x < 60 && !at.moving) {
    g.sprite(friday(blinking(w), "none"), at.x, 78)
    g.rect(14, 92, 64, 4, "T")
    g.rect(18, 96, 56, 16, "t")
    g.sprite(LAPTOP, 50, 84, { swap: Math.floor(w.now / 180) % 2 ? { s: "B", B: "s" } : undefined })
  } else fri(g, at.x, FLOOR, "happy", walkLegs(w, at.moving), at.left)
  if (!(at.x < 60 && !at.moving)) g.sprite(LAPTOP, 50, 84)
  strip(g, 17 * 60, bed, free, m, "MON")
  if (m >= bed - 30) g.shade(0.25)
}

function parkScene(g: G, w: World): void {
  const wake = wakeOf(w.a, 5)
  const bed = bedOf(w.a, 5)
  const m = lapse(w.t, wake, bed, w.still)
  const free = freeSpan(w.a, true)
  sky(g, 0, 0, W, 100, m)
  if (isNight(m)) g.sprite(MOON, 200, 18)
  else {
    const [sx, sy] = arc(m, wake, Math.min(bed, 20 * 60), 10, 14, 220, 50)
    g.sprite(SUN, sx, sy)
  }
  clouds(g, w, 20)
  hills(g, 96)
  g.rect(0, 96, W, H - 96, "g")
  g.dither(0, 96, W, 4, "G")
  tree(g, 196, 112, 1)
  // the picnic table with the laptop, and the blanket under the tree
  g.rect(20, 92, 64, 4, "T")
  g.rect(24, 96, 4, 16, "u")
  g.rect(76, 96, 4, 16, "u")
  for (let x = 140; x < 200; x += 4) for (let y = 110; y < 120; y += 4) g.rect(x, y, 4, 4, (x / 4 + y / 4) % 2 ? "e" : "w")
  const relaxing = free !== null && m >= free[0] && m < free[1]
  const at = toward(w, relaxing ? 160 : 26, 300)
  if (at.x > 120 && !at.moving) {
    // sunglasses in the sun; after dark, looking up at the stars
    fri(g, at.x, 116, isNight(m) ? "look" : blinking(w, "happy"))
    if (!isNight(m)) {
      g.rect(at.x + 3, 116 - 17 + 8, 4, 2, "k")
      g.rect(at.x + 9, 116 - 17 + 8, 4, 2, "k")
      g.rect(at.x + 7, 116 - 17 + 8, 2, 1, "k")
    }
  } else if (at.x < 60 && !at.moving) {
    g.sprite(friday(blinking(w), "none"), at.x, 78)
    g.rect(20, 92, 64, 4, "T")
  } else fri(g, at.x, 112, "happy", walkLegs(w, at.moving), at.left)
  g.sprite(LAPTOP, 48, 84)
  strip(g, wake, bed, free, m, "SAT")
  if (isNight(m)) g.shade(0.3)
}

// ---- Packing the bag: the AI, and where things come from ------------------------------------------------------------

function bagScene(g: G, w: World): void {
  room(g, 16 * 60)
  blanket(g)
  const bob = w.still ? 0 : Math.floor(w.now / 400) % 2
  const happy = w.bag.ai || w.bag.connected > 0
  fri(g, 150, FLOOR - bob, blinking(w, happy ? "happy" : "open"))
  g.sprite(BAG, 172, FLOOR - 24, { scale: 2 })
  const items = [w.bag.ai ? CHIP : null, w.bag.connected > 0 ? CAL : null].filter((x): x is string[] => !!x)
  items.forEach((art, i) => {
    const float = w.still ? 0 : Math.round(Math.sin(w.now / 300 + i) * 2)
    g.sprite(art, 178 + i * 10, FLOOR - 36 + float)
  })
}

// ---- The week -------------------------------------------------------------------------------------------------------

const COL = 26
const GAP = 4
const BOARD_X = 25
const BOARD_Y = 40
const BOARD_H = 100
const KIND: Record<string, string> = { sleep: "#2f3352", class: "b", work: "g", heavy: "g", free: "P", essay: "y", brief: "y", event: "l" }

/** Friday runs along the top of the week, and each day's blocks drop as it passes. */
function weekScene(g: G, w: World): void {
  sky(g, 0, 0, W, H, 12 * 60)
  clouds(g, w, 6)
  const bits = weekOf(w.a, "ready").bits
  const run = 3600
  const fx = w.still ? 236 : lerp(4, 236, (w.t - 300) / run)
  g.rect(BOARD_X - 3, BOARD_Y - 3, 7 * COL + 6 * GAP + 6, BOARD_H + 6, "k")
  g.rect(BOARD_X, BOARD_Y, 7 * COL + 6 * GAP, BOARD_H, "w")
  const y = (t: number) => BOARD_Y + ((Math.min(Math.max(t, VIEW.from), VIEW.to) - VIEW.from) / (VIEW.to - VIEW.from)) * BOARD_H
  const days = ["M", "T", "W", "T", "F", "S", "S"]
  for (let day = 0; day < 7; day++) {
    const x = BOARD_X + day * (COL + GAP)
    g.rect(x, BOARD_Y, COL, BOARD_H, "#eef2e5")
    g.text(days[day], x + 11, BOARD_Y - 10, "k")
    const reached = w.still ? -1e9 : (300 + ((x + COL / 2 - 4) / 232) * run)
    bits
      .filter((b) => b.day === day && b.kind !== "due")
      .forEach((b, i) => {
        const at = w.still ? 1 : stepped((w.t - reached - i * 45) / 320, 6)
        if (at <= 0) return
        const top = y(b.start)
        const h = Math.max(2, y(b.end) - top)
        const yy = lerp(BOARD_Y - 30, top, at)
        if (yy < BOARD_Y - 2) return
        if (b.kind === "brief") return g.rect(x + COL - 5, yy, 4, 3, "y")
        g.rect(x, yy, COL, h, KIND[b.kind] ?? "g")
        if (b.kind !== "sleep" && b.kind !== "free") {
          g.rect(x, yy, COL, 1, "w")
          g.rect(x, yy + h - 1, COL, 1, "k")
        }
        if (b.kind === "free") g.dither(x, yy, COL, h, "w")
      })
  }
  // Friday's run along the top of the board, then a cheer
  const finished = w.still || w.t > run + 400
  if (finished) {
    const hop = w.still ? 0 : Math.abs(Math.sin((w.t / 300) * Math.PI)) * 6
    fri(g, 236, BOARD_Y - 3 - hop, "happy", "apart")
    fireworks(g, w)
    g.text("YOUR WEEK", 92, 6, "k", 2)
    g.text("YOUR WEEK", 91, 5, "y", 2)
  } else fri(g, fx, BOARD_Y - 3, "happy", walkLegs(w, true))
}

function fireworks(g: G, w: World): void {
  if (w.still) return
  const spots: [number, number, string][] = [
    [40, 20, "y"],
    [128, 14, "e"],
    [210, 22, "b"],
  ]
  spots.forEach(([cx, cy, c], i) => {
    const s = ((w.now / 1300 + i / 3) % 1 + 1) % 1
    const r = Math.round(s * 12)
    for (let k = 0; k < 8; k++) {
      const a = (k / 8) * Math.PI * 2
      g.rect(cx + Math.cos(a) * r, cy + Math.sin(a) * r, 2, 2, s > 0.8 ? "Y" : c)
    }
  })
}

// ---- Which scene each step is in, and the clock it shows ------------------------------------------------------------

const SCENES: Record<string, (g: G, w: World) => void> = {
  title: titleScene,
  hello: helloScene,
  hello2: helloScene,
  wake: wakeScene,
  classes: classesScene,
  work: workScene,
  heavy: workScene,
  focus: focusScene,
  deadline: deadlineScene,
  evening: homeScene,
  weekend: parkScene,
  bed: bedScene,
  brief: briefScene,
  ai: bagScene,
  bring: bagScene,
  calendars: bagScene,
  week: weekScene,
}

export function paint(g: G, w: World): void {
  g.ctx.clearRect(0, 0, W, H)
  ;(SCENES[w.step] ?? titleScene)(g, w)
  if (w.fresh && !w.still && w.t < 450) dissolve(g, w.t / 450)
}

/** Where each step happens: a move from one place to another dissolves in. */
const PLACE: Record<string, string> = {
  title: "room", hello: "room", hello2: "room", wake: "room", classes: "campus", work: "library", heavy: "library",
  focus: "library", deadline: "road", evening: "home", weekend: "park", bed: "room", brief: "room", ai: "room",
  bring: "room", calendars: "room", week: "week",
}

export function placeOf(step: string): string {
  return PLACE[step] ?? step
}

export function minutesOf(hhmm: string): number {
  const [h, m] = hhmm.split(":").map(Number)
  return h * 60 + m
}

/** The day and time the clock in the corner shows, or null where there's no clock. */
export function clockOf(w: World): { day: string; minutes: number } | null {
  const a = w.a
  switch (w.step) {
    case "wake":
      return { day: "MON", minutes: minutesOf(a.wake) + (w.done === null ? 0 : Math.min(60, w.done / 50)) }
    case "classes":
      return { day: "MON", minutes: 9 * 60 + 50 + Math.min(20, w.t / 250) }
    case "work":
    case "heavy":
      return { day: "MON", minutes: 13 * 60 }
    case "focus":
      return { day: "MON", minutes: 9 * 60 + Math.round(w.still ? 0 : focusCycle(a.focus_hours, w.t).minutes) }
    case "deadline":
      return { day: "WED", minutes: 15 * 60 }
    case "evening":
      return { day: "MON", minutes: lapse(w.t, 17 * 60, bedOf(a, 0), w.still) }
    case "weekend":
      return { day: "SAT", minutes: lapse(w.t, wakeOf(a, 5), bedOf(a, 5), w.still) }
    case "bed":
      return { day: "MON", minutes: minutesOf(a.bedtime) }
    case "brief":
      return { day: "TUE", minutes: minutesOf(a.wake) + 20 }
    case "ai":
    case "bring":
    case "calendars":
      return { day: "SUN", minutes: 16 * 60 }
    default:
      return null
  }
}
