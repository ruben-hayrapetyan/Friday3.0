// The places the walk goes into (walk/stops.ts says which question is where): rooms behind doors, each built in its own
// space with its front on the street (+z) and its floor at FLOOR, then set beside the road by walk/World.ts. Seen from
// the street the way a game shows a house you walk into: its front and everything above the room cut away (they still
// throw their shadows). Your answers show in them: the alarm clock reads the time you get up, the books on the library
// table are the hours you'd work, the week on the notice board has your essay done on the day you chose. Each question
// has a scene: where the one walking you through goes, what they do there, and where the camera looks from.

import * as THREE from "three"
import type { Schemas } from "@/api/client"
import type { Action, Mood } from "./character"
import { ball, bake, block, cylinder, gable, M, panel, span } from "./props"
import { clockTime, minutesOf, type Place } from "./stops"
import { Board, hash, random } from "./textures"

type Answers = Schemas["SetupInput"]
type Mat = THREE.Material

export const FLOOR = 0.3 // a ground floor's level, a step up from the path
export const T = 0.3 // walls
export const FRONT = 8 // a building's front from the middle of the street
export const SIDEWALK: [number, number] = [5.1, 6.9] // from the middle of the street
const STOREY = 3.1

const V = (x: number, y: number, z: number) => new THREE.Vector3(x, y, z)

/** A light somewhere in a place: on at night only (a porch, a street lamp), or always (a lamp in a room). */
export interface Socket {
  at: THREE.Vector3
  color: number
  power: number
  range: number
  night: boolean
}

export interface Spot {
  pos: THREE.Vector3
  look: THREE.Vector3
}

/** What happens at a question: walked to, then done. All in the place's own space. */
export interface Scene {
  via?: THREE.Vector3[] // round the furniture, after the door
  walk: THREE.Vector3 // where the walk ends, on the floor
  at: THREE.Vector3 // where they are while doing it (the floor under their hips)
  yaw: number // which way they face (0: toward the street)
  action: Action
  seat?: number // what they sit on, when it isn't the usual height
  bed?: Bed // in bed: how they get in and out of it
  front?: number | THREE.Vector3 // sitting: how far in front of the seat they stand before sitting down, or where
  mood?: Mood // how your answers have them feeling there
  cam: Spot
}

const clamp01 = (x: number) => Math.max(0, Math.min(1, x))

/** What setup knows besides your answers: the AI you chose (and, for one on this Mac, how far its download is),
 * and whether something you brought in is being read. */
export interface Extra {
  ai: { provider: string; name: string; ready: boolean; model?: string; progress?: number | null } | null
  reading: boolean
  brought?: number // how many things have been brought in (uploads, calendars, accounts): one more, a letter comes
}

/** A bed to get into: where they stand beside it, sit on its edge, lie and sit up (feet on the floor under the
 * hips), facing which way, how high the mattress is, and its duvet with where it folds to. */
export interface Bed {
  side: THREE.Vector3
  edge: THREE.Vector3
  lie: THREE.Vector3
  up: THREE.Vector3
  yawEdge: number // sitting on the edge, facing away from the bed
  yawIn: number // in it, feet to the foot of the bed
  top: number
  duvet: Duvet
  closed: number // the duvet's fold, pulled up to the chest
  waist: number // folded back to the waist, sitting up
  open: number // thrown back, to get in or out
}

/** A duvet that lies over whoever is in the bed (30 Oct: "i want the bedsheets to bend around his legs"): a sheet of
 * cloth over the mattress, hanging over its sides and foot, lifted wherever the body under it is, folded back from
 * its top edge at `fold` (in its bed's space: the head end toward -z, the mattress's top at `top`). */
export class Duvet {
  readonly group = new THREE.Group()
  fold: number
  full = 0
  private geo: THREE.BufferGeometry
  private width: number
  private head: number
  private foot: number
  private top: number
  private body: { p: THREE.Vector3; r: number; torso?: boolean; arm?: boolean }[] = []
  private nx: number // cells across: fine enough that a hand lifts the cloth, not poke between its points
  private static NZ = 40
  private static HANG = 0.24

  constructor(width: number, head: number, foot: number, top: number, color: number) {
    this.width = width
    this.head = head
    this.foot = foot
    this.top = top
    this.group.userData.live = true
    this.group.userData.cloth = true
    this.nx = Math.round((width + 0.5) * 22)
    this.geo = new THREE.PlaneGeometry(1, 1, this.nx, Duvet.NZ)
    const cloth = M.fabric(color).clone()
    cloth.side = THREE.DoubleSide
    const mesh = new THREE.Mesh(this.geo, cloth)
    mesh.castShadow = true
    mesh.receiveShadow = true
    this.group.add(mesh)
    this.fold = head
    this.set(head + 0.1, 0)
  }

  /** Where its top edge is folded to, and (unused now) how full it is. */
  set(fold: number, full = 0): void {
    this.fold = fold
    this.full = full
    this.shape()
  }

  /** The body under it, as lumps in the world (Character.samples), or none. */
  over(body: { p: THREE.Vector3; r: number; torso?: boolean; arm?: boolean }[]): void {
    this.group.updateMatrixWorld(true)
    this.body = body.map((b) => ({ p: this.group.worldToLocal(b.p.clone()), r: b.r, torso: b.torso, arm: b.arm }))
    this.shape()
  }

  private shape(): void {
    const { NZ, HANG } = Duvet
    const NX = this.nx
    const pos = this.geo.attributes.position as THREE.BufferAttribute
    const uv = this.geo.attributes.uv as THREE.BufferAttribute
    const half = this.width / 2
    const fold = Math.min(this.fold, this.foot - 0.1)
    const back = Math.max(0, Math.min(0.42, fold - this.head)) // how much is turned back over itself
    const rest = this.top + 0.045
    const upright = this.body.some((b) => b.torso && b.p.y - this.top > 0.42)
    for (let j = 0; j <= NZ; j++) {
      const v = j / NZ
      const zFlat = fold + (this.foot + HANG - fold) * v
      for (let i = 0; i <= NX; i++) {
        const u = i / NX
        const xFlat = -half - HANG + (this.width + 2 * HANG) * u
        // past the mattress's sides and foot, the cloth hangs down, drawn in a little as it falls
        const outX = Math.max(0, Math.abs(xFlat) - half)
        const outZ = Math.max(0, zFlat - this.foot)
        const drop = Math.min(1, Math.hypot(outX, outZ) / HANG)
        const fall = drop * drop * (3 - 2 * drop)
        let x = Math.sign(xFlat) * (Math.min(Math.abs(xFlat), half) + outX * 0.35)
        let z = Math.min(zFlat, this.foot) + outZ * 0.35
        let y = rest - fall * 0.28
        // lifted over the body, smoothly, as cloth lies over a leg
        for (const b of this.body) {
          // sitting up, the cloth stays in the lap: it doesn't climb an upright chest, and arms lifted out of the bed
          // lie on top of it; lying down, all of them are under it
          if (upright && b.p.y - this.top > (b.torso ? 0.15 : b.arm ? 0.12 : 0.26)) continue
          const lift = b.p.y + b.r + 0.015
          if (lift <= y) continue
          const d = Math.hypot(x - b.p.x, z - b.p.z)
          const k = 1 - Math.min(1, Math.max(0, (d - b.r * 0.9) / (b.r * 0.4 + 0.15)))
          const lifted = y + (lift - y) * (k * k * (3 - 2 * k))
          if (lifted > y) y = lifted
        }
        // the band turned back at the top edge: a second layer, thickest at the fold
        if (back > 0.02 && zFlat < fold + back) y += 0.035 + 0.03 * (1 - (zFlat - fold) / back)
        if (j === 0) {
          // the top edge rolls under a little
          y -= 0.01
          z -= 0.01
        }
        if (outX === 0 && outZ === 0) x = xFlat
        pos.setXYZ(j * (NX + 1) + i, x, y, z)
        uv.setXY(j * (NX + 1) + i, xFlat, zFlat)
      }
    }
    pos.needsUpdate = true
    uv.needsUpdate = true
    this.geo.computeVertexNormals()
    this.geo.computeBoundingSphere()
  }
}

export interface Built {
  group: THREE.Group
  cut: THREE.Group | null // the front and what's above the room, hidden while you're inside
  stub: THREE.Group | null // the front wall cut down low, shown instead
  size: { w: number; d: number } // along the street, and back from the front
  scene: (spot: number, a: Answers, extra: Extra) => Scene
  door: { inside: THREE.Vector3; outside: THREE.Vector3 } | null // the way in and out
  sockets: Socket[]
  clear: [number, number, number, number][] // no grass here: x0, z0, x1, z1
  room: [number, number, number, number] | null // indoors: x0, z0, x1, z1
  show: (a: Answers) => void
  extra?: (e: Extra) => void
  tick?: (seconds: number, minutes: number, step: string) => void
  cue?: (name: string, seconds: number) => void // something the scene does now (the alarm going off)
}

/** How long a sitting is in the walk, in seconds, for `hours` of focus: the library's timer rings at the end of each. */
export function sittingFor(hours: number): number {
  return 5 + Math.min(4, hours) * 2.5
}



// ---- walls, windows and doors ---------------------------------------------------------------------------------------

interface Hole {
  x: number
  w: number
  y0: number
  y1: number
}

/** A wall along x with holes in it, its outer face at zo and its inner at zi; plastered inside when `inner`. */
function wallX(g: THREE.Group, x0: number, x1: number, y0: number, y1: number, zo: number, zi: number, holes: Hole[], outer: Mat, inner: Mat | null): void {
  const pieces: [number, number, number, number][] = []
  let at = x0
  for (const h of [...holes].sort((a, b) => a.x - b.x)) {
    const a = h.x - h.w / 2
    const b = h.x + h.w / 2
    if (a > at) pieces.push([at, a, y0, y1])
    if (h.y0 > y0) pieces.push([a, b, y0, h.y0])
    if (h.y1 < y1) pieces.push([a, b, h.y1, y1])
    at = b
  }
  if (at < x1) pieces.push([at, x1, y0, y1])
  const inward = Math.sign(zi - zo)
  for (const [a, b, c, d] of pieces) {
    g.add(span(a, b, c, d, zo, inner ? zi - inward * 0.02 : zi, outer))
    if (inner) g.add(span(a, b, Math.max(c, FLOOR), d, zi - inward * 0.02, zi, inner))
  }
}

const TRIM = () => M.paint(0xf1eee6, 0.5)

/** A window in a hole: frame, glazing bars, glass, and a sill outside. */
function glazing(g: THREE.Group, h: Hole, zo: number, zi: number, trim: Mat, sill: Mat): void {
  const z = (zo + zi) / 2
  const a = h.x - h.w / 2
  const b = h.x + h.w / 2
  const f = 0.07
  g.add(span(a, b, h.y0, h.y0 + f, z - 0.05, z + 0.05, trim), span(a, b, h.y1 - f, h.y1, z - 0.05, z + 0.05, trim))
  g.add(span(a, a + f, h.y0, h.y1, z - 0.05, z + 0.05, trim), span(b - f, b, h.y0, h.y1, z - 0.05, z + 0.05, trim))
  g.add(span(h.x - 0.025, h.x + 0.025, h.y0, h.y1, z - 0.03, z + 0.03, trim))
  const bar = h.y0 + (h.y1 - h.y0) * 0.56
  g.add(span(a, b, bar - 0.025, bar + 0.025, z - 0.03, z + 0.03, trim))
  g.add(panel(h.w - 2 * f, h.y1 - h.y0 - 2 * f, M.glass(), h.x, (h.y0 + h.y1) / 2, z))
  const out = Math.sign(zo - zi)
  g.add(span(a - 0.08, b + 0.08, h.y0 - 0.07, h.y0, zo - out * 0.02, zo + out * 0.13, sill))
}

/** A window on a storey we never go into: frame, dark glass that's lit some nights, sill and lintel. */
function blindWindow(g: THREE.Group, x: number, y0: number, y1: number, w: number, z: number, out: number, trim: Mat, sill: Mat, lit: boolean, seed: number): void {
  const glass = lit ? M.windowLit([0xffc98a, 0xffd9a8, 0xffb870][seed % 3]) : M.window()
  const pane = panel(w - 0.14, y1 - y0 - 0.14, glass, x, (y0 + y1) / 2, z + out * 0.012)
  if (out < 0) pane.rotation.y = Math.PI
  g.add(pane)
  const zz = (d: number) => [z, z + out * d] as const
  g.add(span(x - w / 2, x + w / 2, y0, y0 + 0.07, ...zz(0.06), trim), span(x - w / 2, x + w / 2, y1 - 0.07, y1, ...zz(0.06), trim))
  g.add(span(x - w / 2, x - w / 2 + 0.07, y0, y1, ...zz(0.06), trim), span(x + w / 2 - 0.07, x + w / 2, y0, y1, ...zz(0.06), trim))
  g.add(span(x - 0.02, x + 0.02, y0, y1, ...zz(0.04), trim))
  g.add(span(x - w / 2 - 0.08, x + w / 2 + 0.08, y0 - 0.08, y0, ...zz(0.14), sill), span(x - w / 2 - 0.1, x + w / 2 + 0.1, y1, y1 + 0.16, ...zz(0.05), sill))
}

/** A doorway with its casing (part of the front), the door swung open into the room, a step, and the path. */
function doorway(g: THREE.Group, cut: THREE.Group, d: { x: number; w: number }, trim: Mat, color: number): void {
  const a = d.x - d.w / 2
  const b = d.x + d.w / 2
  const top = FLOOR + 2.25
  cut.add(span(a - 0.12, a, FLOOR, top + 0.12, -0.02, 0.05, trim), span(b, b + 0.12, FLOOR, top + 0.12, -0.02, 0.05, trim))
  cut.add(span(a - 0.16, b + 0.16, top, top + 0.16, -0.02, 0.07, trim))
  const leaves = d.w > 1.4 ? [a, b] : [a]
  const width = d.w / leaves.length
  for (const hinge of leaves) {
    // open, against the wall inside; with the front when it's cut away (it would stand in the way)
    const dir = hinge === a ? 1 : -1
    cut.add(block(0.05, 2.22, width - 0.03, M.paint(color, 0.45), hinge + dir * 0.045, FLOOR, -T - width / 2))
    cut.add(ball(0.03, M.metal(0xc9a96a, 0.3), hinge + dir * 0.1, FLOOR + 1.0, -T - width + 0.08, 8))
  }
  g.add(span(a - 0.25, b + 0.25, 0, FLOOR, 0, 0.5, M.concrete()))
  g.add(span(d.x - 0.7, d.x + 0.7, 0, 0.16, 0.5, FRONT - SIDEWALK[1] + 0.05, M.concrete()))
}

interface RoomSpec {
  w: number
  d: number
  h: number
  outer: Mat
  inner: Mat
  floor: Mat
  door: { x: number; w: number; color: number }
  front: Hole[]
  back: Hole[]
  above: number
  roof: "gable" | "flat"
  roofMat?: Mat
  trim?: Mat
  sill?: Mat
  seed: number
}

/** A building whose ground floor is a room you can walk into: its walls, windows, door, ceiling, the storeys above
 * (with their own windows, some lit at night) and its roof. The front, the ceiling and all above go in `cut`; a low
 * front wall goes in `stub`, for when they're cut away. */
function building(g: THREE.Group, s: RoomSpec, sockets: Socket[]): { top: number; cut: THREE.Group; stub: THREE.Group } {
  const cut = new THREE.Group()
  const stub = new THREE.Group()
  cut.userData.live = true
  stub.userData.live = true
  stub.visible = false
  g.add(cut, stub)
  const { w, d, h } = s
  const ceiling = FLOOR + h
  const wallTop = ceiling + 0.3
  const xo = w / 2 + T
  const back = -2 * T - d
  const trim = s.trim ?? TRIM()
  const sill = s.sill ?? M.stone()
  g.add(span(-xo, xo, 0, FLOOR - 0.02, back, 0, s.outer))
  g.add(span(-w / 2, w / 2, FLOOR - 0.02, FLOOR, back + T, -T, s.floor))
  const doorHole = { x: s.door.x, w: s.door.w, y0: FLOOR, y1: FLOOR + 2.25 }
  wallX(cut, -xo, xo, 0, wallTop, 0, -T, [doorHole, ...s.front], s.outer, s.inner)
  wallX(stub, -xo, xo, 0, FLOOR + 0.45, 0, -T, [doorHole], s.outer, s.inner)
  wallX(stub, -xo - 0.03, xo + 0.03, FLOOR + 0.45, FLOOR + 0.52, 0.03, -T - 0.03, [{ ...doorHole, y0: FLOOR + 0.45, y1: FLOOR + 0.52 }], trim, null)
  wallX(g, -xo, xo, 0, wallTop, back, back + T, s.back, s.outer, s.inner)
  for (const side of [-1, 1]) {
    g.add(span(side * xo, side * (w / 2 + 0.02), 0, wallTop, back + T, -T, s.outer))
    g.add(span(side * (w / 2 + 0.02), (side * w) / 2, FLOOR, ceiling, back + T, -T, s.inner))
  }
  cut.add(span(-w / 2, w / 2, ceiling, ceiling + 0.02, back + T, -T, M.plaster(0xf7f5f0)))
  cut.add(span(-xo, xo, ceiling + 0.02, wallTop, back, 0, s.outer))
  // skirting boards, where walls meet the floor
  g.add(span(-w / 2, w / 2, FLOOR, FLOOR + 0.1, back + T, back + T + 0.02, trim))
  for (const side of [-1, 1]) g.add(span((side * w) / 2, side * (w / 2 - 0.02), FLOOR, FLOOR + 0.1, back + T, -T, trim))
  for (const hole of s.front) glazing(cut, hole, 0, -T, trim, sill)
  for (const hole of s.back) glazing(g, hole, back, back + T, trim, sill)
  doorway(g, cut, s.door, trim, s.door.color)
  // a lamp by the door, on at night
  cut.add(block(0.14, 0.3, 0.12, M.metal(0x1b1b1b, 0.5), s.door.x + s.door.w / 2 + 0.4, FLOOR + 1.85, 0.06))
  cut.add(block(0.1, 0.2, 0.08, M.lamp(), s.door.x + s.door.w / 2 + 0.4, FLOOR + 1.9, 0.14))
  sockets.push({ at: V(s.door.x + s.door.w / 2 + 0.4, FLOOR + 2.0, 0.5), color: 0xffc98a, power: 6, range: 7, night: true })
  let y = wallTop
  const rnd = random(s.seed)
  for (let k = 0; k < s.above; k++) {
    cut.add(span(-xo, xo, y, y + STOREY, back, 0, s.outer))
    cut.add(span(-xo - 0.05, xo + 0.05, y - 0.12, y + 0.02, back - 0.05, 0.06, trim))
    const n = Math.max(2, Math.round((2 * xo) / 2.4))
    for (let i = 0; i < n; i++) {
      const x = -xo + ((i + 0.5) * (2 * xo)) / n
      blindWindow(cut, x, y + 0.85, y + 2.4, 1.05, 0, 1, trim, sill, rnd() > 0.45, s.seed + i)
      blindWindow(cut, x, y + 0.85, y + 2.4, 1.05, back, -1, trim, sill, rnd() > 0.6, s.seed + i + 1)
    }
    y += STOREY
  }
  if (s.roof === "gable") {
    cut.add(gable(2 * xo, -back, Math.min(3.4, -back * 0.42), s.roofMat ?? M.shingles(), s.outer, 0, y, back / 2))
  } else {
    cut.add(span(-xo - 0.18, xo + 0.18, y, y + 0.5, back - 0.18, 0.18, trim))
    cut.add(span(-xo - 0.1, xo + 0.1, y + 0.5, y + 0.62, back - 0.1, 0.1, M.paint(0x5b5f66, 0.8)))
  }
  return { top: y, cut, stub }
}

/** Merge the place's still parts: the room, then its front, then the low wall, each on its own. */
function finish(g: THREE.Group, cut: THREE.Group | null, stub: THREE.Group | null): void {
  bake(g)
  if (cut) bake(cut)
  if (stub) bake(stub)
}

/** A camera looking at `look` from `from` away: in front of the room (+z) and above it. */
const cam = (look: THREE.Vector3, from: [number, number, number]): Spot => ({ look, pos: look.clone().add(V(...from)) })

// ---- things in rooms ---------------------------------------------------------------------------------------------------

/** A clock on a wall, its hands set by `set(minutes)`. Faces +z. */
function wallClock(r: number): { group: THREE.Group; set: (minutes: number) => void } {
  const g = new THREE.Group()
  g.userData.live = true
  const rim = new THREE.Mesh(new THREE.TorusGeometry(r, r * 0.09, 10, 48), M.paint(0x1d1b19, 0.4, true))
  rim.castShadow = true
  g.add(rim)
  const face = new THREE.Mesh(new THREE.CircleGeometry(r, 48), M.paint(0xf6f3ec, 0.6, true))
  face.position.z = -0.01
  g.add(face)
  for (let i = 0; i < 12; i++) {
    const tick = block(r * 0.04, r * (i % 3 ? 0.08 : 0.16), 0.005, M.paint(0x1d1b19, 0.5, true))
    const a = (i / 12) * Math.PI * 2
    tick.position.set(Math.sin(a) * r * 0.82, Math.cos(a) * r * 0.82, 0)
    tick.rotation.z = -a
    g.add(tick)
  }
  const hand = (len: number, width: number) => {
    const pivot = new THREE.Group()
    const m = block(width, len, 0.008, M.paint(0x111111, 0.5, true), 0, -len * 0.12, 0.01)
    pivot.add(m)
    g.add(pivot)
    return pivot
  }
  const hour = hand(r * 0.55, r * 0.07)
  const minute = hand(r * 0.82, r * 0.045)
  g.add(ball(r * 0.05, M.paint(0x111111, 0.5, true), 0, 0, 0.02, 8))
  return {
    group: g,
    set: (m) => {
      hour.rotation.z = -(((m / 60) % 12) / 12) * Math.PI * 2
      minute.rotation.z = -((m % 60) / 60) * Math.PI * 2
    },
  }
}

/** A bedside clock whose red digits show a time. Faces +z. */
function alarmClock(): { group: THREE.Group; set: (minutes: number) => void } {
  const g = new THREE.Group()
  g.userData.live = true
  g.add(block(0.24, 0.11, 0.09, M.paint(0x161616, 0.35, true), 0, 0, 0, 0.02))
  const board = new Board(256, 112)
  const glow = new THREE.MeshStandardMaterial({ color: 0x000000, roughness: 0.25, emissive: 0xffffff, emissiveMap: board.texture, emissiveIntensity: 2.2 })
  g.add(panel(0.2, 0.085, glow, 0, 0.056, 0.0455))
  return {
    group: g,
    set: (minutes) =>
      board.draw(String(minutes), (ctx, w, h) => {
        ctx.fillStyle = "#040404"
        ctx.fillRect(0, 0, w, h)
        const [time, half] = clockTime(minutes).split(" ")
        ctx.fillStyle = "#ff3324"
        ctx.textAlign = "center"
        ctx.textBaseline = "middle"
        ctx.font = `700 ${Math.round(h * 0.66)}px "JetBrains Mono", ui-monospace, monospace`
        ctx.fillText(time, w * 0.44, h * 0.55)
        ctx.font = `700 ${Math.round(h * 0.2)}px "JetBrains Mono", ui-monospace, monospace`
        ctx.fillText(half, w * 0.89, h * 0.3)
      }),
  }
}

const BOOK_COLORS = [0x7a2a24, 0x23365a, 0x2f5a3a, 0x6b4a2a, 0xd9cfb6, 0x1f1f22, 0x8a6a2a, 0x5a2a4a, 0x3a5f6b, 0xa8452e]

/** A pile of `n` books lying flat, at x, y, z. */
function pile(n: number, seed: number): THREE.Group {
  const g = new THREE.Group()
  const rnd = random(seed)
  let y = 0
  for (let i = 0; i < Math.round(n); i++) {
    const t = 0.03 + rnd() * 0.03
    const book = block(0.17 + rnd() * 0.06, t, 0.24 + rnd() * 0.04, M.paint(BOOK_COLORS[Math.floor(rnd() * BOOK_COLORS.length)], 0.7, true), (rnd() - 0.5) * 0.03, y, (rnd() - 0.5) * 0.03, 0.004)
    book.rotation.y = (rnd() - 0.5) * 0.35
    g.add(book)
    y += t
  }
  return g
}

/** Shelves full of books standing up: along x, `len` long, with `rows` shelves. Faces +z. */
function bookcase(len: number, height: number, rows: number, seed: number): THREE.Group {
  const g = new THREE.Group()
  const wood = M.wood(0x8a6a4c)
  g.add(span(-len / 2, len / 2, 0, height, -0.36, -0.34, wood))
  for (const x of [-len / 2, len / 2]) g.add(span(x - 0.02, x + 0.02, 0, height, -0.36, 0, wood))
  const gap = (height - 0.1) / rows
  for (let r = 0; r <= rows; r++) g.add(span(-len / 2, len / 2, r * gap, r * gap + 0.025, -0.36, 0, wood))
  const rnd = random(seed)
  const books: THREE.Matrix4[] = []
  const colors: THREE.Color[] = []
  for (let r = 0; r < rows; r++) {
    let x = -len / 2 + 0.03
    while (x < len / 2 - 0.08) {
      const w = 0.022 + rnd() * 0.04
      const h = Math.min(gap - 0.05, 0.19 + rnd() * 0.13)
      const d = 0.17 + rnd() * 0.08
      const lean = rnd() > 0.94 ? 0.25 : 0
      const m = new THREE.Matrix4().compose(V(x + w / 2, r * gap + 0.025 + h / 2, -0.34 + d / 2 + 0.01), new THREE.Quaternion().setFromAxisAngle(V(0, 0, 1), lean), V(w, h, d))
      books.push(m)
      colors.push(new THREE.Color(BOOK_COLORS[Math.floor(rnd() * BOOK_COLORS.length)]).multiplyScalar(0.75 + rnd() * 0.4))
      x += w + (rnd() > 0.92 ? 0.08 : 0.002)
    }
  }
  const mesh = new THREE.InstancedMesh(new THREE.BoxGeometry(1, 1, 1), M.paint(0xffffff, 0.75, true), books.length)
  books.forEach((m, i) => {
    mesh.setMatrixAt(i, m)
    mesh.setColorAt(i, colors[i])
  })
  mesh.castShadow = true
  mesh.receiveShadow = true
  g.add(mesh)
  return g
}

function chair(color: Mat, x: number, z: number, turn: number): THREE.Group {
  const g = new THREE.Group()
  g.add(block(0.44, 0.04, 0.42, color, 0, 0.44, 0, 0.01))
  for (const [a, b] of [[-0.19, -0.18], [0.19, -0.18], [-0.19, 0.18], [0.19, 0.18]]) g.add(block(0.035, 0.44, 0.035, color, a, 0, b))
  g.add(block(0.44, 0.42, 0.035, color, 0, 0.48, -0.2, 0.01))
  g.position.set(x, FLOOR, z)
  g.rotation.y = turn
  return g
}

function table(w: number, d: number, h: number, top: Mat, x: number, z: number): THREE.Group {
  const g = new THREE.Group()
  g.add(block(w, 0.045, d, top, 0, h - 0.045, 0, 0.01))
  for (const [a, b] of [[-1, -1], [1, -1], [-1, 1], [1, 1]]) g.add(block(0.05, h - 0.045, 0.05, top, (a * (w - 0.12)) / 2, 0, (b * (d - 0.12)) / 2))
  g.position.set(x, FLOOR, z)
  return g
}

/** A laptop, open, its screen a board that's redrawn. */
function laptop(board: Board): THREE.Group {
  const g = new THREE.Group()
  g.userData.live = true
  const alu = M.metal(0xb9bcc2, 0.35)
  g.add(block(0.32, 0.015, 0.22, alu, 0, 0, 0, 0.005))
  const lid = new THREE.Group()
  lid.add(block(0.32, 0.21, 0.008, alu, 0, 0, 0, 0.004))
  const screen = new THREE.MeshStandardMaterial({ color: 0x000000, roughness: 0.2, emissive: 0xffffff, emissiveMap: board.texture, emissiveIntensity: 1.1 })
  lid.add(panel(0.29, 0.18, screen, 0, 0.105, 0.0045))
  lid.position.set(0, 0.015, -0.105)
  lid.rotation.x = -0.28
  g.add(lid)
  return g
}

function lampShade(x: number, y: number, z: number, shade: Mat, sockets: Socket[], color = 0xffcf96, power = 9): THREE.Group {
  const g = new THREE.Group()
  const cone = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.2, 0.22, 20, 1, true), shade)
  cone.material.side = THREE.DoubleSide
  cone.position.set(x, y + 0.11, z)
  cone.castShadow = true
  g.add(cone)
  g.add(ball(0.05, M.bulb(color, 5), x, y + 0.06, z, 10))
  sockets.push({ at: V(x, y + 0.05, z), color, power, range: 6, night: false })
  return g
}

function rug(w: number, d: number, color: number, x: number, z: number): THREE.Mesh {
  return block(w, 0.012, d, M.carpet(color), x, FLOOR, z, 0.005)
}

function plant(x: number, z: number, size = 1): THREE.Group {
  const g = new THREE.Group()
  g.add(cylinder(0.16 * size, 0.12 * size, 0.3 * size, M.paint(0xb5634a, 0.8, true), 0, 0, 0, 14))
  const leafMat = M.paint(0x3f6b34, 0.6, true)
  const rnd = random(Math.round(x * 100 + z * 10))
  for (let i = 0; i < 9; i++) {
    const leaf = new THREE.Mesh(new THREE.SphereGeometry(0.12 * size, 8, 6), leafMat)
    leaf.scale.set(0.6, 1.8, 0.25)
    const a = rnd() * Math.PI * 2
    leaf.position.set(Math.cos(a) * 0.1 * size, 0.45 * size + rnd() * 0.2 * size, Math.sin(a) * 0.1 * size)
    leaf.rotation.set(Math.cos(a) * 0.6, a, Math.sin(a) * 0.6)
    leaf.castShadow = true
    g.add(leaf)
  }
  g.position.set(x, FLOOR, z)
  return g
}

/** A painted picture or poster on a wall, its board drawn once. */
function picture(w: number, h: number, paint: (ctx: CanvasRenderingContext2D, w: number, h: number) => void, frame: Mat | null): THREE.Group {
  const g = new THREE.Group()
  const board = new Board(Math.round(w * 400), Math.round(h * 400))
  board.draw("once", paint)
  g.add(panel(w, h, new THREE.MeshStandardMaterial({ map: board.texture, roughness: 0.8, envMapIntensity: 0.4 }), 0, 0, 0.012))
  if (frame) {
    g.add(span(-w / 2 - 0.03, w / 2 + 0.03, -h / 2 - 0.03, -h / 2, 0, 0.03, frame), span(-w / 2 - 0.03, w / 2 + 0.03, h / 2, h / 2 + 0.03, 0, 0.03, frame))
    g.add(span(-w / 2 - 0.03, -w / 2, -h / 2, h / 2, 0, 0.03, frame), span(w / 2, w / 2 + 0.03, -h / 2, h / 2, 0, 0.03, frame))
  }
  return g
}

const FONT = (weight: number, px: number) => `${weight} ${Math.round(px)}px Archivo, Inter, system-ui, sans-serif`
const HAND = (px: number) => `600 ${Math.round(px)}px "Marker Felt", "Chalkboard SE", "Comic Sans MS", cursive`

function abstractPoster(seed: number) {
  return (ctx: CanvasRenderingContext2D, w: number, h: number) => {
    const rnd = random(seed)
    ctx.fillStyle = ["#e9e1cf", "#1f2a44", "#d4a23a"][seed % 3]
    ctx.fillRect(0, 0, w, h)
    const colors = ["#c8442b", "#2d5d7b", "#e3b23c", "#1d1d1d", "#7a9a6a", "#f2ece0"]
    for (let i = 0; i < 6; i++) {
      ctx.fillStyle = colors[Math.floor(rnd() * colors.length)]
      if (rnd() > 0.5) {
        ctx.beginPath()
        ctx.arc(rnd() * w, rnd() * h, (0.12 + rnd() * 0.25) * w, 0, Math.PI * 2)
        ctx.fill()
      } else ctx.fillRect(rnd() * w * 0.7, rnd() * h * 0.7, (0.2 + rnd() * 0.4) * w, (0.1 + rnd() * 0.3) * h)
    }
  }
}

// ---- the places ----------------------------------------------------------------------------------------------------

function dorm(): Built {
  const g = new THREE.Group()
  const sockets: Socket[] = []
  const w = 6.4
  const d = 5
  const { cut, stub } = building(g, { w, d, h: 2.9, outer: M.brick(), inner: M.plaster(0xeee6d8), floor: M.floor(), door: { x: -2, w: 1.0, color: 0x2f4a3a }, front: [{ x: 1.2, w: 1.6, y0: 1.2, y1: 2.6 }], back: [{ x: -0.5, w: 1.9, y0: 1.15, y1: 2.75 }], above: 2, roof: "gable", roofMat: M.shingles(0x9a8f88), seed: 11 }, sockets)
  const zb = -T - d
  // the bed against the right wall, head to the back
  const bed = new THREE.Group()
  bed.add(block(1.06, 0.36, 2.06, M.wood(0x9a7a5a), 0, 0, 0, 0.02))
  bed.add(block(1.0, 0.2, 2.0, M.fabric(0xf2efe8), 0, 0.36, 0, 0.05))
  bed.add(block(0.62, 0.09, 0.36, M.fabric(0xf6f3ee), 0, 0.56, -0.76, 0.04))
  bed.add(block(1.06, 0.95, 0.06, M.wood(0x9a7a5a), 0, 0, -1.03, 0.02))
  bed.position.set(w / 2 - 0.56, FLOOR, zb + 1.06)
  g.add(bed)
  const duvet = new Duvet(1.04, -0.62, 1.03, 0.56, 0x5f84b8)
  duvet.group.position.copy(bed.position)
  g.add(duvet.group)
  const bedX = w / 2 - 0.56
  const bedZ = zb + 1.06
  const inBed: Bed = { side: V(1.62, FLOOR, bedZ - 0.05), edge: V(2.32, FLOOR, bedZ - 0.05), lie: V(bedX, FLOOR, bedZ - 0.05), up: V(bedX, FLOOR, bedZ - 0.05), yawEdge: -Math.PI / 2, yawIn: 0, top: 0.56, duvet, closed: -0.66, waist: 0.1, open: 0.42 }
  // the nightstand, and the clock on it facing you
  g.add(block(0.46, 0.56, 0.42, M.wood(0x8a6a4c), 1.55, FLOOR, zb + 0.24, 0.015))
  const clock = alarmClock()
  clock.group.position.set(1.5, FLOOR + 0.56, zb + 0.3)
  clock.group.rotation.y = -0.62
  g.add(clock.group)
  g.add(lampShade(1.72, FLOOR + 0.56 + 0.22, zb + 0.18, M.fabric(0xe8dcc4), sockets, 0xffc98a, 4))
  g.add(cylinder(0.015, 0.015, 0.22, M.metal(0x2a2a2a), 1.72, FLOOR + 0.56, zb + 0.18, 8))
  // the desk under the window, a chair, a mug
  g.add(table(1.4, 0.6, 0.75, M.wood(0xb08a62), -0.6, zb + 0.32))
  g.add(chair(M.paint(0x2b2b2b, 0.5, true), -0.5, zb + 1.0, Math.PI)) // square to the desk, to sit on (the school step)
  g.add(cylinder(0.04, 0.04, 0.1, M.paint(0xd9d4c8, 0.3, true), -0.1, FLOOR + 0.75, zb + 0.3, 14))
  g.add(pile(3, 5).translateX(-1.0).translateY(FLOOR + 0.75).translateZ(zb + 0.3))
  // curtains
  for (const side of [-1, 1]) g.add(block(0.42, 1.95, 0.06, M.fabric(0xc9b896), -0.5 + side * 1.12, FLOOR + 0.75, zb + 0.08, 0.02))
  g.add(cylinder(0.015, 0.015, 2.7, M.metal(0x333333), -0.5, FLOOR + 2.72, zb + 0.1, 8).rotateZ(Math.PI / 2))
  // a rug, a poster, a shelf
  g.add(rug(1.8, 2.3, 0xb88a3a, -0.4, zb + 2.6))
  const poster = picture(0.7, 1.0, abstractPoster(2), null)
  poster.position.set(-w / 2 + 0.01, FLOOR + 1.7, zb + 2.2)
  poster.rotation.y = Math.PI / 2
  g.add(poster)
  const shelf = bookcase(1.0, 0.9, 2, 31)
  shelf.position.set(-w / 2 + 0.36, FLOOR, zb + 3.6)
  shelf.rotation.y = Math.PI / 2
  g.add(shelf)
  // Are you in school? (C97; 10 Nov: "this had none", every other step's scene changes with its answer): beside the
  // desk, a student's things or a working person's, swapped as you answer, the new ones popping into place
  const student = new THREE.Group()
  student.add(block(0.34, 0.5, 0.22, M.fabric(0x4a5a3a), -1.55, FLOOR, zb + 0.62, 0.06)) // the backpack
  student.add(block(0.26, 0.12, 0.04, M.fabric(0x6b7a52), -1.55, FLOOR + 0.18, zb + 0.75, 0.03)) // its pocket
  student.add(pile(6, 9).translateX(-0.25).translateY(FLOOR + 0.75).translateZ(zb + 0.34)) // textbooks
  const pennant = picture(0.62, 0.26, (ctx, pw, ph) => {
    ctx.fillStyle = "#eee6d8" // the wall's own colour round the felt
    ctx.fillRect(0, 0, pw, ph)
    ctx.fillStyle = "#b3262c"
    ctx.beginPath()
    ctx.moveTo(0, 0)
    ctx.lineTo(pw, ph / 2)
    ctx.lineTo(0, ph)
    ctx.closePath()
    ctx.fill()
    ctx.fillStyle = "#f4ead8"
    ctx.font = FONT(800, ph * 0.42)
    ctx.fillText("GO TEAM", pw * 0.05, ph * 0.64)
  }, null)
  pennant.position.set(-2.45, FLOOR + 1.5, zb + 0.02) // on the wall above the bag, left of the window
  student.add(pennant)
  const worker = new THREE.Group()
  worker.add(block(0.42, 0.32, 0.12, M.fabric(0x3b2e26), -1.55, FLOOR, zb + 0.62, 0.03)) // the laptop bag
  worker.add(block(0.4, 0.05, 0.13, M.fabric(0x2c221c), -1.55, FLOOR + 0.27, zb + 0.6, 0.02)) // its flap
  worker.add(block(0.34, 0.02, 0.24, M.metal(0x9aa0a6), -0.3, FLOOR + 0.75, zb + 0.34, 0.01)) // a closed laptop
  worker.add(block(0.15, 0.025, 0.21, M.paint(0x2f4a6b, 0.6, true), 0.05, FLOOR + 0.75, zb + 0.3, 0.004)) // a planner
  const photo = picture(0.34, 0.26, (ctx, pw, ph) => {
    ctx.fillStyle = "#9cc3e0"
    ctx.fillRect(0, 0, pw, ph)
    ctx.fillStyle = "#6d9a5a"
    ctx.fillRect(0, ph * 0.62, pw, ph * 0.38)
    ctx.fillStyle = "#f1d36b"
    ctx.beginPath()
    ctx.arc(pw * 0.75, ph * 0.28, ph * 0.12, 0, Math.PI * 2)
    ctx.fill()
  }, M.wood(0x5a4030))
  photo.position.set(-2.45, FLOOR + 1.5, zb + 0.02)
  worker.add(photo)
  student.userData.live = worker.userData.live = true // not baked into the room: shown, hidden and popped as you answer
  worker.visible = false
  g.add(student, worker)
  let inSchool: boolean | null = null
  let swappedAt = -10
  let swapping = false
  sockets.push({ at: V(0, FLOOR + 2.6, zb + 2.6), color: 0xffd7a8, power: 7, range: 8, night: false })
  finish(g, cut, stub)
  let alarmAt = -10
  // at the desk for "Are you in school?", its own spot: the chair's in front of it, facing the back wall
  // round the chair's side and in beside it, to sit across onto it, as at the library's table
  const atDesk = { via: [V(0.55, FLOOR, zb + 2.0), V(0.55, FLOOR, zb + 1.0)], walk: V(0.3, FLOOR, zb + 1.0), at: V(-0.5, FLOOR, zb + 1.0), yaw: Math.PI, front: V(-0.05, FLOOR, zb + 1.0) }
  return {
    group: g,
    cut,
    stub,
    size: { w: w + 2 * T, d: d + 2 * T },
    // into bed, the alarm, sitting up: at 6:15 they drag themselves up; by 9 they're bright-eyed. Spot 1: at the desk,
    // its things for the school question in view
    scene: (spot, a) => spot === 1
      ? { ...atDesk, action: "study" as const, cam: cam(V(-0.75, 1.05, zb + 0.6), [1.7, 1.25, 3.1]) }
      : ({ walk: inBed.side, at: inBed.up, yaw: inBed.yawIn, action: "wake", seat: inBed.top, bed: inBed, mood: { energy: clamp01((minutesOf(a.wake) - 375) / 165) }, cam: cam(V(2.2, 0.9, -4.35), [-2.4, 3.7, 6.2]) }),
    door: { inside: V(-2, 0, -1.0), outside: V(-2, 0, 1.6) },
    sockets,
    clear: [[-w / 2 - T - 0.3, -d - 2 * T - 0.3, w / 2 + T + 0.3, 0.6], [-2.8, 0, -1.2, 2.8]],
    room: [-w / 2, -d - T, w / 2, -T],
    show: (a) => {
      clock.set(minutesOf(a.wake))
      const now = a.school !== false
      if (inSchool !== null && now !== inSchool) swapping = true // the tick pops them in
      inSchool = now
      student.visible = now
      worker.visible = !now
    },
    cue: (name, seconds) => {
      if (name === "alarm") alarmAt = seconds
    },
    tick: (seconds) => {
      if (swapping) {
        swappedAt = seconds
        swapping = false
      }
      // the things just swapped in grow into place, overshooting a little
      const t = Math.min(1, (seconds - swappedAt) / 0.45)
      const pop = t >= 1 ? 1 : 0.4 + 0.6 * (1 + 0.35 * Math.sin(t * Math.PI)) * t
      const shown = inSchool === false ? worker : student
      shown.scale.setScalar(pop)
      // the alarm going off: the clock buzzing on the nightstand for a moment
      const ringing = seconds - alarmAt < 1.6
      clock.group.rotation.z = ringing ? Math.sin(seconds * 60) * 0.05 : 0
      clock.group.position.y = FLOOR + 0.56 + (ringing ? Math.abs(Math.sin(seconds * 60)) * 0.01 : 0)
    },
  }
}

function library(): Built {
  const g = new THREE.Group()
  const sockets: Socket[] = []
  const w = 10
  const d = 8
  const h = 4.2
  const { cut, stub } = building(g, { w, d, h, outer: M.stone(), inner: M.plaster(0xece3cf), floor: M.floor(0x8a6a50), door: { x: 0, w: 1.8, color: 0x3a2a20 }, front: [{ x: -3.2, w: 1.5, y0: 1.2, y1: 3.8 }, { x: 3.2, w: 1.5, y0: 1.2, y1: 3.8 }], back: [{ x: -3, w: 1.5, y0: 1.3, y1: 3.8 }, { x: 3, w: 1.5, y0: 1.3, y1: 3.8 }], above: 1, roof: "gable", roofMat: M.shingles(0x6f7a80), seed: 23 }, sockets)
  const zb = -T - d
  // shelves down both walls and between the back windows
  for (const side of [-1, 1]) {
    const shelf = bookcase(6.4, 2.7, 7, side > 0 ? 41 : 43)
    shelf.position.set(side * (w / 2 - 0.36), FLOOR, -T - 4.4)
    shelf.rotation.y = -side * (Math.PI / 2)
    g.add(shelf)
  }
  const middle = bookcase(2.6, 2.3, 6, 47)
  middle.position.set(0, FLOOR, zb + 0.36)
  g.add(middle)
  // the reading tables, their lamps, chairs
  const dark = M.wood(0x6b4a34)
  for (const z of [-3.4, -6.0]) {
    g.add(table(3.4, 1.15, 0.76, dark, 0, z))
    for (const x of [-1.1, 1.1]) {
      // your chair (the near table's, on the right) pulled out from the table, to sit on
      if (z === -3.4 && x === 1.1) g.add(chair(dark, x, z - 1.1, 0))
      else g.add(chair(dark, x, z - 0.85, 0.08))
      g.add(chair(dark, x + 0.1, z + 0.85, Math.PI - 0.1))
    }
    for (const x of z === -3.4 ? [-0.45, -1.4] : [-0.9, 0.9]) {
      // on the near table, away from your end of it, so they're not between you and the camera
      g.add(block(0.14, 0.02, 0.1, M.metal(0xb08a4a, 0.3), x, FLOOR + 0.76, z - 0.25))
      g.add(cylinder(0.012, 0.012, 0.32, M.metal(0xb08a4a, 0.3), x, FLOOR + 0.78, z - 0.25, 8))
      const shade = new THREE.Mesh(new THREE.CylinderGeometry(0.07, 0.07, 0.3, 16, 1, false, 0, Math.PI), new THREE.MeshStandardMaterial({ color: 0x1f5a3a, roughness: 0.15, emissive: 0x2a8a50, emissiveIntensity: 0.35, side: THREE.DoubleSide }))
      shade.rotation.z = Math.PI / 2
      shade.rotation.y = Math.PI / 2
      shade.position.set(x, FLOOR + 1.12, z - 0.18)
      g.add(shade)
      g.add(ball(0.03, M.bulb(0xffd9a0, 4), x, FLOOR + 1.08, z - 0.18, 8))
    }
    sockets.push({ at: V(0, FLOOR + 1.0, z - 0.2), color: 0xffd29a, power: 10, range: 6, night: false })
  }
  // pendant lights
  for (const z of [-3.4, -6.0]) {
    g.add(cylinder(0.01, 0.01, 1.4, M.metal(0x222222), 0, FLOOR + h - 1.4, z, 6))
    g.add(cylinder(0.12, 0.32, 0.26, M.paint(0x24342c, 0.4, true), 0, FLOOR + h - 1.66, z, 24))
    g.add(ball(0.07, M.bulb(0xffe2b8, 4), 0, FLOOR + h - 1.66, z, 10))
  }
  sockets.push({ at: V(0, FLOOR + h - 1.8, -4.7), color: 0xffe0b0, power: 18, range: 11, night: false })
  // the clock high on the back wall
  const clock = wallClock(0.42)
  clock.group.position.set(0, FLOOR + 3.25, zb + 0.03)
  g.add(clock.group)
  // your place at the nearer table: the laptop, a notebook, and the books for a day's work
  const screen = new Board(512, 320)
  const lap = laptop(screen)
  lap.position.set(1.1, FLOOR + 0.76, -3.78)
  lap.rotation.y = Math.PI
  g.add(lap)
  // a day's books at their right hand, what a heavy day adds at their left, the timer for a sitting in front
  const normal = new THREE.Group()
  normal.userData.live = true
  normal.position.set(0.48, FLOOR + 0.76, -3.72)
  const extra = new THREE.Group()
  extra.userData.live = true
  extra.position.set(1.52, FLOOR + 0.76, -3.7)
  g.add(normal, extra)
  const timer = new THREE.Group()
  timer.userData.live = true
  timer.add(cylinder(0.075, 0.085, 0.09, M.paint(0xd2412f, 0.35, true), 0, 0, 0, 18))
  timer.add(cylinder(0.06, 0.06, 0.012, M.paint(0xf6f3ec, 0.4, true), 0, 0.09, 0, 18))
  const knob = new THREE.Group()
  knob.add(block(0.012, 0.012, 0.055, M.paint(0x1d1d1d, 0.4, true), 0, 0, 0.028))
  knob.position.set(0, 0.104, 0)
  timer.add(knob)
  timer.position.set(0.85, FLOOR + 0.76, -3.42)
  g.add(timer)
  finish(g, cut, stub)
  let said = ""
  let want = ""
  let since = -1
  let focus = 1
  let piles: [number, number] = [0, 0]
  let rangAt = -10
  // round the table's end, along between it and the chair, and sit (30 Oct: "he walks through the table")
  // round the table's end and in beside the chair, to sit across onto it, close to the table
  const seat = { via: [V(2.45, FLOOR, -2.5), V(2.45, FLOOR, -4.45)], walk: V(1.95, FLOOR, -4.45), at: V(1.1, FLOOR, -4.42), yaw: 0, front: V(1.55, FLOOR, -4.45) }
  return {
    group: g,
    cut,
    stub,
    size: { w: w + 2 * T, d: d + 2 * T },
    // studying at the table: the camera on the day's pile, then the heavy day's, then the timer for a sitting
    scene: (spot) =>
      [
        { ...seat, action: "study" as const, cam: cam(V(0.75, 0.95, -3.85), [0.6, 2.7, 5.0]) },
        { ...seat, action: "study" as const, cam: cam(V(1.35, 0.95, -3.85), [-0.4, 2.5, 4.6]) },
        { ...seat, action: "study" as const, cam: cam(V(0.95, 0.95, -3.7), [0.3, 2.2, 3.9]) },
      ][Math.min(spot, 2)],
    door: { inside: V(0, 0, -1.0), outside: V(0, 0, 1.6) },
    sockets,
    clear: [[-w / 2 - T - 0.3, -d - 2 * T - 0.3, w / 2 + T + 0.3, 0.6], [-0.9, 0, 0.9, 2.8]],
    room: [-w / 2, -d - T, w / 2, -T],
    show: (a) => {
      focus = a.focus_hours
      // a book an hour; the piles change when the hand reaches them (walk/World.ts has them reach as you answer)
      piles = [Math.min(12, Math.round(a.normal_hours)), Math.min(12, Math.round(Math.max(0, a.most_hours - a.normal_hours)))]
      want = `${piles[0]}:${piles[1]}`
      screen.draw(`${a.normal_hours}:${a.most_hours}:${a.focus_hours}`, (ctx, w2, h2) => {
        ctx.fillStyle = "#f7f6f2"
        ctx.fillRect(0, 0, w2, h2)
        ctx.fillStyle = "#1d2330"
        ctx.font = FONT(700, 26)
        ctx.fillText("Today", 26, 46)
        ctx.font = FONT(500, 18)
        ctx.fillStyle = "#6a6f7a"
        ctx.fillText(`${a.normal_hours}h of work · ${a.focus_hours}h at a time`, 26, 76)
        const blocks = Math.max(1, Math.ceil(a.normal_hours / Math.max(0.5, a.focus_hours)))
        const colors = ["#3f8f5a", "#4a74c4", "#3f8f5a", "#c9893a", "#3f8f5a", "#4a74c4"]
        for (let i = 0; i < Math.min(6, blocks); i++) {
          ctx.fillStyle = colors[i]
          ctx.fillRect(26, 100 + i * 34, 140 + ((i * 53) % 220), 24)
        }
      })
    },
    cue: (name, seconds) => {
      if (name === "ring") rangAt = seconds
    },
    tick: (seconds, minutes, step) => {
      if (want !== said) {
        if (since < 0) since = seconds
        if (!said || seconds - since > 0.55) {
          said = want
          since = -1
          normal.clear()
          normal.add(pile(piles[0], 61))
          extra.clear()
          extra.add(pile(piles[1], 67))
        }
      }
      clock.set(minutes)
      // the timer's dial at the length of a sitting; it rings at the end of each
      knob.rotation.y = -(Math.min(4, focus) / 4) * Math.PI * 1.6
      // it rings when walk/World.ts says a sitting is done (and they sit back)
      const ringing = step === "focus" && seconds - rangAt < 1.2
      timer.rotation.z = ringing ? Math.sin(seconds * 55) * 0.06 : 0
    },
  }
}

function hall(): Built {
  const g = new THREE.Group()
  const sockets: Socket[] = []
  const back = -7 // the hall stands back across a lawn
  const w = 20
  const d = 12
  const stone = M.stone()
  const trim = TRIM()
  g.add(span(-w / 2, w / 2, 0, 9, back - d, back, stone))
  g.add(span(-w / 2 - 0.2, w / 2 + 0.2, 9, 9.6, back - d - 0.2, back + 0.2, trim))
  g.add(gable(w + 0.4, d + 0.4, 4, M.shingles(0x5f6a72), stone, 0, 9.6, back - d / 2))
  for (let i = 0; i < 7; i++) {
    const x = -w / 2 + 1.6 + i * ((w - 3.2) / 6)
    if (Math.abs(x) < 3.5) continue
    for (const y of [1.3, 5.2]) blindWindow(g, x, y, y + 2.6, 1.3, back, 1, trim, stone, y > 3 && i % 2 === 0, 70 + i)
  }
  // the portico: steps, columns, the pediment
  for (let s = 0; s < 4; s++) g.add(span(-4.4 - s * 0.3, 4.4 + s * 0.3, 0, 0.45 - s * 0.11, back, back + 1.4 + (4 - s) * 0.32, stone))
  for (let i = 0; i < 4; i++) g.add(cylinder(0.3, 0.36, 6.4, M.paint(0xeae4d6, 0.6), -3 + i * 2, 0.45, back + 2.1, 20))
  g.add(span(-4.2, 4.2, 6.85, 7.6, back, back + 2.6, trim))
  const ped = new THREE.Shape()
  ped.moveTo(-4.3, 0)
  ped.lineTo(4.3, 0)
  ped.lineTo(0, 1.9)
  ped.closePath()
  const tri = new THREE.Mesh(new THREE.ExtrudeGeometry(ped, { depth: 2.6, bevelEnabled: false }), trim)
  tri.position.set(0, 7.6, back)
  tri.castShadow = true
  g.add(tri)
  g.add(span(-1.2, 1.2, 0.45, 3.4, back - 0.05, back + 0.02, M.paint(0x2a2018, 0.5)))
  // the clock tower
  g.add(span(-w / 2 - 4, -w / 2, 0, 19, back - 7, back - 3, stone))
  g.add(span(-w / 2 - 4.2, -w / 2 + 0.2, 19, 19.4, back - 7.2, back - 2.8, trim))
  const spire = new THREE.Mesh(new THREE.ConeGeometry(2.9, 6, 4), M.paint(0x46525a, 0.5))
  spire.rotation.y = Math.PI / 4
  spire.position.set(-w / 2 - 2, 22.4, back - 5)
  spire.castShadow = true
  g.add(spire)
  const tower = wallClock(1.1)
  tower.group.position.set(-w / 2 - 2, 16.6, back - 2.97)
  g.add(tower.group)
  // a path up to the steps, and the notice board on the lawn by the sidewalk
  g.add(span(-1.2, 1.2, 0, 0.16, back + 2.6, FRONT - SIDEWALK[1] + 0.05, M.concrete()))
  const board = new THREE.Group()
  const post = M.wood(0x5a4030)
  for (const x of [-1.25, 1.25]) board.add(block(0.12, 2.75, 0.12, post, x, 0, 0))
  board.add(block(2.5, 1.35, 0.06, M.cork(), 0, 1.0, 0))
  board.add(span(-1.3, 1.3, 2.35, 2.43, -0.06, 0.06, post), span(-1.3, 1.3, 0.92, 1.0, -0.06, 0.06, post))
  board.add(gable(2.8, 0.7, 0.32, M.shingles(0x6a5a50), post, 0, 2.6, 0))
  // flyers round the week
  const flyers: [number, number, number, number, number][] = [
    [-0.95, 1.92, 0.42, 0.56, 1],
    [0.98, 1.95, 0.4, 0.5, 2],
    [-1.0, 1.32, 0.38, 0.42, 3],
    [1.02, 1.38, 0.36, 0.44, 4],
  ]
  const FLYERS = [
    ["CHESS CLUB", "Thursdays 7pm", "Room 112"],
    ["OPEN MIC", "Friday night", "The Commons"],
    ["STUDY GROUP", "Calc II", "Library, 2nd floor"],
    ["BIKE FOR SALE", "Barely used", "Ask at the desk"],
  ]
  for (const [x, y, fw, fh, n] of flyers) {
    const f = picture(fw, fh, (ctx, cw, ch) => {
      ctx.fillStyle = ["#f4f1e8", "#f1d36a", "#d9e6f2", "#f4f1e8"][n - 1]
      ctx.fillRect(0, 0, cw, ch)
      const [t1, t2, t3] = FLYERS[n - 1]
      ctx.fillStyle = "#1f1f22"
      ctx.font = FONT(800, cw * 0.12)
      ctx.fillText(t1, cw * 0.08, ch * 0.24)
      ctx.font = FONT(500, cw * 0.085)
      ctx.fillText(t2, cw * 0.08, ch * 0.42)
      ctx.fillText(t3, cw * 0.08, ch * 0.55)
      for (let i = 0; i < 4; i++) ctx.fillRect(cw * 0.08, ch * (0.68 + i * 0.06), cw * (0.5 + ((i * 37) % 30) / 100), ch * 0.015)
    }, null)
    f.position.set(x, y, 0.03)
    f.rotation.z = (hash(n, 1) - 0.5) * 0.12
    board.add(f)
  }
  const week = new Board(900, 560)
  const sheet = panel(1.12, 0.7, new THREE.MeshStandardMaterial({ map: week.texture, roughness: 0.85, envMapIntensity: 0.5 }), 0, 1.68, 0.045)
  board.add(sheet)
  // the note for the day the essay's done, moved along the week by hand when you change it
  const sticky = new Board(160, 140)
  sticky.draw("done", (ctx, cw, ch) => {
    ctx.fillStyle = "#f6d94a"
    ctx.fillRect(0, 0, cw, ch)
    ctx.fillStyle = "#1d2a6a"
    ctx.font = HAND(34)
    ctx.textAlign = "center"
    ctx.fillText("essay", cw / 2, ch * 0.42)
    ctx.fillText("done ✓", cw / 2, ch * 0.78)
  })
  const note = panel(0.19, 0.165, new THREE.MeshStandardMaterial({ map: sticky.texture, roughness: 0.9, envMapIntensity: 0.5 }), 0, 1.74, 0.056)
  note.rotation.z = -0.05
  note.userData.live = true
  board.add(note)
  const column = (day: number) => -0.448 + day * 0.224
  for (const [x, y] of [[-0.5, 2.0], [0.5, 2.0], [-0.5, 1.36], [0.5, 1.36]]) board.add(ball(0.012, M.paint(0xc8302a, 0.3), x, y, 0.05, 8))
  board.position.set(1.8, 0.13, 0.9)
  g.add(board)
  g.add(span(0.2, 3.4, 0, 0.14, 0.2, FRONT - SIDEWALK[1] + 0.05, M.concrete()))
  sockets.push({ at: V(0, 6.5, back + 3.2), color: 0xffd9a8, power: 30, range: 14, night: true })
  bake(g)
  let want = 3 // the column (day) the note is going to, where it is, and since when it's moving
  let at = 3
  let from = 3
  let moving = -1
  const DAYS = ["MON", "TUE", "WED", "THU", "FRI"]
  return {
    group: g,
    size: { w: w + 8, d: -back + d + 1 },
    cut: null,
    stub: null,
    scene: () => ({ walk: V(1.8, 0.16, 2.1), at: V(1.8, 0.16, 2.0), yaw: Math.PI, action: "read", cam: cam(V(1.75, 1.45, 1.3), [3.0, 1.9, 4.6]) }),
    door: null,
    sockets,
    clear: [[-w / 2 - 4.5, back - d - 0.5, w / 2 + 0.5, back + 2.8], [-1.3, back + 2.6, 1.3, 2.8], [0.1, 0, 3.5, 2.8]],
    room: null,
    show: (a) => {
      const done = 4 - Math.max(0, Math.min(4, a.finish_early_days))
      want = done
      week.draw("week", (ctx, cw, ch) => {
        ctx.fillStyle = "#fbfaf6"
        ctx.fillRect(0, 0, cw, ch)
        ctx.fillStyle = "#1f2430"
        ctx.font = FONT(800, 46)
        ctx.fillText("THIS WEEK", 40, 66)
        ctx.font = FONT(500, 24)
        ctx.fillStyle = "#6a6f7a"
        ctx.fillText("English 1105", 330, 64)
        const col = (cw - 80) / 5
        ctx.strokeStyle = "#c9ccd2"
        ctx.lineWidth = 2
        DAYS.forEach((day, i) => {
          const x = 40 + i * col
          ctx.strokeRect(x, 96, col, ch - 136)
          ctx.fillStyle = "#1f2430"
          ctx.font = FONT(700, 28)
          ctx.fillText(day, x + 16, 136)
        })
        // the essay, due Friday at 5 (the note for the day it's done is its own, moved by hand)
        ctx.fillStyle = "#d8402f"
        ctx.fillRect(40 + 4 * col + 10, 300, col - 20, 120)
        ctx.fillStyle = "#ffffff"
        ctx.font = FONT(800, 26)
        ctx.fillText("ESSAY", 40 + 4 * col + 22, 344)
        ctx.font = FONT(600, 22)
        ctx.fillText("due 5 PM", 40 + 4 * col + 22, 380)
      })
    },
    tick: (seconds, minutes) => {
      tower.set(minutes)
      // the note follows the hand: off the board a little, along, and back on
      if (want !== at) {
        if (moving < 0) {
          moving = seconds
          from = at
        }
        const k = Math.min(1, Math.max(0, (seconds - moving - 0.45) / 0.6))
        const e = k * k * (3 - 2 * k)
        note.position.x = column(from) + (column(want) - column(from)) * e
        note.position.z = 0.056 + Math.sin(e * Math.PI) * 0.05
        if (k >= 1) {
          at = want
          moving = -1
        }
      } else note.position.x = column(at)
    },
  }
}

function home(): Built {
  const g = new THREE.Group()
  const sockets: Socket[] = []
  const w = 7
  const d = 6
  const { cut, stub } = building(g, { w, d, h: 2.8, outer: M.siding(0x9fb6c8), inner: M.plaster(0xe9e2d4), floor: M.floor(0xc8a888), door: { x: -2.3, w: 1.0, color: 0x8a2f2a }, front: [{ x: 1.5, w: 1.6, y0: 1.1, y1: 2.6 }], back: [{ x: 0.4, w: 2.8, y0: 0.95, y1: 2.6 }], above: 1, roof: "gable", roofMat: M.shingles(0x7a6a62), seed: 31 }, sockets)
  const zb = -T - d
  // the sofa on the left wall, facing the TV on the right
  const sofa = new THREE.Group()
  const cloth = M.fabric(0x5d6b45)
  sofa.add(block(0.9, 0.42, 2.2, cloth, 0, 0, 0, 0.06))
  sofa.add(block(0.25, 0.85, 2.2, cloth, -0.33, 0, 0, 0.08))
  for (const z of [-1.0, 1.0]) sofa.add(block(0.9, 0.62, 0.2, cloth, 0, 0, z, 0.08))
  for (const z of [-0.47, 0.47]) sofa.add(block(0.62, 0.16, 0.9, cloth, 0.08, 0.42, z, 0.07))
  sofa.add(block(0.12, 0.38, 0.38, M.fabric(0xd9a441), 0, 0.55, -0.6, 0.06).rotateZ(-0.3))
  sofa.position.set(-w / 2 + 0.5, FLOOR, zb + 2.6)
  g.add(sofa)
  g.add(table(1.1, 0.6, 0.42, M.wood(0x7a5a3a), -1.4, zb + 2.6))
  g.add(rug(2.6, 3.0, 0xb9a88a, -1.1, zb + 2.6))
  // the TV on a low cabinet, on the right wall
  g.add(block(0.45, 0.5, 1.6, M.wood(0x5a4232), w / 2 - 0.25, FLOOR, zb + 2.6, 0.01))
  g.add(block(0.06, 0.66, 1.15, M.paint(0x111111, 0.3, true), w / 2 - 0.3, FLOOR + 0.62, zb + 2.6, 0.01))
  const tv = new Board(512, 288)
  const tvMat = new THREE.MeshStandardMaterial({ color: 0x050505, roughness: 0.15, emissive: 0xffffff, emissiveMap: tv.texture, emissiveIntensity: 0 })
  const tvPanel = panel(1.09, 0.6, tvMat, 0, 0, 0)
  tvPanel.rotation.y = -Math.PI / 2
  tvPanel.position.set(w / 2 - 0.335, FLOOR + 0.95, zb + 2.6)
  tvPanel.userData.live = true
  g.add(tvPanel)
  tv.draw("film", (ctx, cw, ch) => {
    ctx.fillStyle = "#3a6ea8"
    ctx.fillRect(0, 0, cw, ch * 0.55)
    ctx.fillStyle = "#e9b26a"
    ctx.fillRect(0, ch * 0.42, cw, ch * 0.13)
    ctx.fillStyle = "#2e5a34"
    ctx.beginPath()
    ctx.moveTo(0, ch * 0.62)
    ctx.quadraticCurveTo(cw * 0.4, ch * 0.4, cw, ch * 0.6)
    ctx.lineTo(cw, ch)
    ctx.lineTo(0, ch)
    ctx.fill()
  })
  // the floor lamp in the corner, plants at the window, a bookcase
  g.add(cylinder(0.16, 0.18, 0.03, M.metal(0x2a2a2a), -w / 2 + 0.4, FLOOR, zb + 0.4, 16))
  g.add(cylinder(0.015, 0.015, 1.5, M.metal(0x2a2a2a), -w / 2 + 0.4, FLOOR, zb + 0.4, 8))
  g.add(lampShade(-w / 2 + 0.4, FLOOR + 1.45, zb + 0.4, M.fabric(0xeadfca), sockets, 0xffc27a, 12))
  g.add(plant(1.9, zb + 0.4, 1.3), plant(-1.4, zb + 0.35, 0.9))
  const shelf = bookcase(1.2, 1.9, 5, 77)
  shelf.position.set(w / 2 - 0.36, FLOOR, zb + 0.9 + 3.0)
  shelf.rotation.y = -Math.PI / 2
  g.add(shelf)
  const art = picture(0.9, 0.6, abstractPoster(4), M.wood(0x3a2a20))
  art.position.set(-w / 2 + 0.01, FLOOR + 1.6, zb + 2.6)
  art.rotation.y = Math.PI / 2
  g.add(art)
  const clock = wallClock(0.2)
  clock.group.position.set(w / 2 - 0.01, FLOOR + 2.0, zb + 2.6)
  clock.group.rotation.y = -Math.PI / 2
  g.add(clock.group)
  // the laptop: on their lap if the evening is work (character.ts carries it), so none on the coffee table
  const screen = new Board(512, 320)
  const lap = laptop(screen)
  lap.visible = false
  screen.draw("doc", (ctx, cw, ch) => {
    ctx.fillStyle = "#fbfbf9"
    ctx.fillRect(0, 0, cw, ch)
    ctx.fillStyle = "#c9ccd2"
    for (let i = 0; i < 9; i++) ctx.fillRect(40, 40 + i * 28, 300 + ((i * 71) % 120), 10)
  })
  const mug = cylinder(0.045, 0.04, 0.1, M.paint(0x2d4a6a, 0.35, true), -1.6, FLOOR + 0.42, zb + 2.3, 14)
  mug.userData.live = true
  g.add(mug)
  finish(g, cut, stub)
  return {
    group: g,
    cut,
    stub,
    size: { w: w + 2 * T, d: d + 2 * T },
    scene: (_spot, a) => ({ walk: V(-2.1, FLOOR, -3.2), at: V(-2.86, FLOOR, -3.7), yaw: Math.PI / 2, front: 0.42, action: a.evening_free > 0 ? "tv" : "laptop", seat: 0.56, mood: { happy: a.evening_free / 5, lid: 1 - Math.min(1, a.evening_free / 5) }, cam: { look: V(-2.5, 0.95, -3.0), pos: V(0.2, 2.75, 0.4) } }),
    door: { inside: V(-2.3, 0, -1.0), outside: V(-2.3, 0, 1.6) },
    sockets,
    clear: [[-w / 2 - T - 0.3, -d - 2 * T - 0.3, w / 2 + T + 0.3, 0.6], [-3.1, 0, -1.5, 2.8]],
    room: [-w / 2, -d - T, w / 2, -T],
    show: (a) => {
      const work = a.evening_free <= 0
      lap.visible = false // on their lap instead (character.ts)
      tvMat.emissiveIntensity = work ? 0 : 1.3
      clock.set(a.evening_free > 0 ? minutesOf(a.evening_from) : 19 * 60)
    },
  }
}

function night(): Built {
  const g = new THREE.Group()
  const sockets: Socket[] = []
  const w = 6.4
  const d = 5.4
  const { cut, stub } = building(g, { w, d, h: 2.8, outer: M.siding(0xb9c4a8), inner: M.plaster(0xdfe3e6), floor: M.floor(0xb89a7a), door: { x: -2.0, w: 1.0, color: 0x2a3a5a }, front: [{ x: 1.3, w: 1.4, y0: 1.15, y1: 2.55 }], back: [{ x: -0.2, w: 1.5, y0: 1.2, y1: 2.55 }], above: 1, roof: "gable", roofMat: M.shingles(0x6a6a70), seed: 41 }, sockets)
  const zb = -T - d
  // a double bed, head to the back wall, turned down
  const bed = new THREE.Group()
  bed.add(block(1.62, 0.32, 2.1, M.wood(0x6a5040), 0, 0, 0, 0.02))
  bed.add(block(1.56, 0.22, 2.02, M.fabric(0xf4f2ee), 0, 0.32, 0, 0.06))
  for (const x of [-0.42, 0.42]) bed.add(block(0.62, 0.09, 0.38, M.fabric(0xf7f5f1), x, 0.54, -0.8, 0.04))
  bed.add(block(1.66, 1.05, 0.08, M.wood(0x6a5040), 0, 0, -1.08, 0.02))
  bed.position.set(1.2, FLOOR, zb + 1.12)
  g.add(bed)
  const duvet = new Duvet(1.6, -0.62, 1.05, 0.54, 0x9aa8c2)
  duvet.group.position.copy(bed.position)
  g.add(duvet.group)
  const inBed: Bed = { side: V(-0.12, FLOOR, zb + 1.07), edge: V(0.58, FLOOR, zb + 1.07), lie: V(0.84, FLOOR, zb + 1.07), up: V(0.84, FLOOR, zb + 1.07), yawEdge: -Math.PI / 2, yawIn: 0, top: 0.54, duvet, closed: -0.66, waist: 0.1, open: 0.42 }
  for (const x of [-0.05, 2.45]) g.add(block(0.46, 0.52, 0.4, M.wood(0x6a5040), x, FLOOR, zb + 0.24, 0.015))
  g.add(lampShade(-0.05, FLOOR + 0.52 + 0.24, zb + 0.22, M.fabric(0xf1e4cc), sockets, 0xffb86a, 7))
  g.add(cylinder(0.05, 0.07, 0.24, M.paint(0xc9b48a, 0.4, true), -0.05, FLOOR + 0.52, zb + 0.22, 14))
  const clock = alarmClock()
  clock.group.position.set(2.42, FLOOR + 0.52, zb + 0.3)
  clock.group.rotation.y = -0.85
  g.add(clock.group)
  g.add(block(1.1, 2.1, 0.6, M.wood(0x8a6a4c), -w / 2 + 0.85, FLOOR, zb + 0.32, 0.01)) // the wardrobe
  g.add(rug(2.2, 1.4, 0x9a6a5a, 1.2, zb + 2.9))
  g.add(block(0.12, 0.06, 0.26, M.fabric(0x5a6a8a), 0.1, FLOOR, zb + 2.5, 0.03), block(0.12, 0.06, 0.26, M.fabric(0x5a6a8a), 0.32, FLOOR, zb + 2.45, 0.03))
  for (const side of [-1, 1]) g.add(block(0.42, 1.7, 0.06, M.fabric(0x3a4a6a), -0.2 + side * 0.98, FLOOR + 0.9, zb + 0.08, 0.02))
  finish(g, cut, stub)
  return {
    group: g,
    cut,
    stub,
    size: { w: w + 2 * T, d: d + 2 * T },
    // into bed and tucked in; to bed late, they turn over in their sleep
    scene: (_spot, a) => ({ walk: inBed.side, at: inBed.lie, yaw: inBed.yawIn, action: "sleep", seat: inBed.top, bed: inBed, mood: { restless: clamp01(((minutesOf(a.bedtime) + 1440 - 12 * 60) % 1440 - 11 * 60) / 150) }, cam: cam(V(1.0, 0.9, -4.6), [-2.6, 3.5, 5.8]) }),
    door: { inside: V(-2.0, 0, -1.0), outside: V(-2.0, 0, 1.6) },
    sockets,
    clear: [[-w / 2 - T - 0.3, -d - 2 * T - 0.3, w / 2 + T + 0.3, 0.6], [-2.8, 0, -1.2, 2.8]],
    room: [-w / 2, -d - T, w / 2, -T],
    show: (a) => clock.set(minutesOf(a.bedtime)),
  }
}

function park(): Built {
  const g = new THREE.Group()
  const sockets: Socket[] = []
  const gravel = M.concrete()
  g.add(span(-1.0, 1.0, 0, 0.15, -9, FRONT - SIDEWALK[1] + 0.05, gravel))
  g.add(span(-8, 8, 0, 0.15, -10.6, -9, gravel))
  // benches by the path
  const bench = (x: number, z: number, turn: number) => {
    const b = new THREE.Group()
    const slat = M.wood(0x8a6040)
    for (let i = 0; i < 4; i++) b.add(block(1.8, 0.035, 0.09, slat, 0, 0.44, -0.18 + i * 0.12, 0.01))
    for (let i = 0; i < 3; i++) b.add(block(1.8, 0.09, 0.035, slat, 0, 0.56 + i * 0.13, -0.28, 0.01))
    for (const sx of [-0.75, 0.75]) b.add(block(0.06, 0.44, 0.5, M.metal(0x1d1d1d, 0.5), sx, 0, -0.03), block(0.06, 0.5, 0.06, M.metal(0x1d1d1d, 0.5), sx, 0.44, -0.29))
    b.position.set(x, 0.13, z)
    b.rotation.y = turn
    return b
  }
  g.add(bench(-2.6, -8.2, 0), bench(3.0, -8.2, 0))
  // the blanket and basket for a free afternoon, or the laptop on the bench if it's work
  const free = new THREE.Group()
  free.userData.live = true
  const plaid = new Board(256, 256)
  plaid.draw("plaid", (ctx, cw, ch) => {
    ctx.fillStyle = "#f2ece0"
    ctx.fillRect(0, 0, cw, ch)
    ctx.fillStyle = "rgba(190,40,36,0.85)"
    for (let i = 0; i < 8; i += 2) {
      ctx.fillRect((i * cw) / 8, 0, cw / 8, ch)
      ctx.fillRect(0, (i * ch) / 8, cw, ch / 8)
    }
  })
  const blanket = block(2.0, 0.015, 1.6, new THREE.MeshStandardMaterial({ map: plaid.texture, roughness: 0.95, envMapIntensity: 0.6 }), -1.6, 0.13, -5.4, 0.005)
  blanket.rotation.y = 0.25
  free.add(blanket)
  const basket = new THREE.Group()
  basket.add(block(0.5, 0.28, 0.34, M.wood(0xb8905a), 0, 0, 0, 0.03))
  basket.add(block(0.5, 0.02, 0.36, M.fabric(0xc8302a), 0, 0.28, 0, 0.01))
  basket.position.set(-0.85, 0.145, -5.25)
  basket.rotation.y = 0.4
  free.add(basket)
  free.add(cylinder(0.13, 0.13, 0.02, M.paint(0xe94e2a, 0.4), -2.55, 0.145, -4.75, 20))
  free.add(pile(2, 9).translateX(-0.95).translateY(0.145).translateZ(-5.95))
  g.add(free)
  const busy = new THREE.Group()
  busy.userData.live = true
  const screen = new Board(512, 320)
  screen.draw("work", (ctx, cw, ch) => {
    ctx.fillStyle = "#fbfbf9"
    ctx.fillRect(0, 0, cw, ch)
    ctx.fillStyle = "#c9ccd2"
    for (let i = 0; i < 9; i++) ctx.fillRect(40, 40 + i * 28, 300 + ((i * 71) % 120), 10)
  })
  const lap = laptop(screen)
  lap.position.set(-2.9, 0.13 + 0.62, -7.82)
  lap.rotation.y = Math.PI
  busy.add(lap)
  busy.add(pile(4, 13).translateX(-2.1).translateY(0.13 + 0.475).translateZ(-8.15))
  g.add(busy)
  // lamps along the path
  for (const z of [-3, -10]) {
    g.add(cylinder(0.05, 0.07, 3.4, M.metal(0x1f2a24, 0.5), 1.4, 0.13, z, 10))
    g.add(ball(0.2, M.lamp(), 1.4, 3.75, z, 16))
    sockets.push({ at: V(1.4, 3.7, z), color: 0xffd09a, power: 14, range: 12, night: true })
  }
  bake(g)
  return {
    group: g,
    cut: null,
    stub: null,
    size: { w: 22, d: 18 },
    scene: (_spot, a) =>
      a.weekend_free > 0
        ? { walk: V(-1.2, 0.15, -4.6), at: V(-1.95, 0.13, -5.7), yaw: 0.35, front: 0.32, action: "picnic", mood: { happy: a.weekend_free / 13 }, cam: cam(V(-1.5, 0.7, -5.4), [2.6, 3.4, 6.6]) }
        : { via: [V(0, 0.15, -7.6)], walk: V(-2.2, 0.15, -7.5), at: V(-2.9, 0.13, -8.12), yaw: 0, action: "laptop", seat: 0.48, cam: cam(V(-2.6, 0.9, -7.7), [2.6, 3.0, 6.2]) },
    door: { inside: V(0.2, 0, -0.5), outside: V(0, 0, 2.0) },
    sockets,
    clear: [[-1.1, -9, 1.1, 2.8], [-8.1, -10.7, 8.1, -8.9]],
    room: null,
    show: (a) => {
      free.visible = a.weekend_free > 0
      busy.visible = a.weekend_free <= 0
    },
  }
}

function cafe(): Built {
  const g = new THREE.Group()
  const sockets: Socket[] = []
  const w = 8
  const d = 6.4
  const h = 3.2
  const { cut, stub } = building(g, { w, d, h, outer: M.brickPale(), inner: M.plaster(0xf1e6d2), floor: M.floor(0x9a7a5a), door: { x: 0.6, w: 1.1, color: 0x26453a }, front: [{ x: -2.2, w: 2.8, y0: 0.75, y1: 2.85 }, { x: 2.85, w: 1.5, y0: 0.75, y1: 2.85 }], back: [{ x: 2.6, w: 1.0, y0: 1.4, y1: 2.6 }], above: 1, roof: "flat", seed: 51 }, sockets)
  const zb = -T - d
  // the awning over the front, striped
  const stripes = new Board(512, 64)
  stripes.draw("stripes", (ctx, cw, ch) => {
    for (let i = 0; i < 16; i++) {
      ctx.fillStyle = i % 2 ? "#f2ede2" : "#2f6a52"
      ctx.fillRect((i * cw) / 16, 0, cw / 16, ch)
    }
  })
  const cloth = new THREE.MeshStandardMaterial({ map: stripes.texture, roughness: 0.9, side: THREE.DoubleSide })
  const awning = block(w + 0.4, 0.04, 1.5, cloth, 0, 0, 0)
  awning.geometry = new THREE.BoxGeometry(w + 0.4, 0.04, 1.5)
  awning.position.set(0, FLOOR + 3.05, 0.65)
  awning.rotation.x = 0.38
  cut.add(awning)
  const sign = new Board(1024, 160)
  sign.draw("sign", (ctx, cw, ch) => {
    ctx.fillStyle = "#1f2a26"
    ctx.fillRect(0, 0, cw, ch)
    ctx.fillStyle = "#e9d9b0"
    ctx.font = FONT(800, 92)
    ctx.textAlign = "center"
    ctx.textBaseline = "middle"
    ctx.fillText("COMMONS COFFEE", cw / 2, ch / 2 + 4)
  })
  cut.add(panel(4.4, 0.68, new THREE.MeshStandardMaterial({ map: sign.texture, roughness: 0.6 }), 0, FLOOR + 3.75, 0.03))
  // the counter at the back, the machine, the menu over it
  g.add(span(-3.6, 1.4, FLOOR, FLOOR + 1.02, zb + 0.4, zb + 1.05, M.wood(0x5a3e2c)))
  g.add(span(-3.65, 1.45, FLOOR + 1.02, FLOOR + 1.07, zb + 0.35, zb + 1.1, M.paint(0x2a2a2a, 0.25, true)))
  const machine = new THREE.Group()
  machine.add(block(0.75, 0.48, 0.5, M.metal(0xc9ccd0, 0.25), 0, 0, 0, 0.03))
  machine.add(block(0.75, 0.06, 0.5, M.metal(0x1d1d1d, 0.4), 0, 0.48, 0, 0.01))
  for (const x of [-0.18, 0.18]) machine.add(cylinder(0.035, 0.035, 0.08, M.metal(0x1d1d1d, 0.3), x, 0.2, 0.28, 10))
  machine.position.set(-2.3, FLOOR + 1.07, zb + 0.7)
  g.add(machine)
  for (let i = 0; i < 6; i++) g.add(cylinder(0.04, 0.035, 0.08, M.paint(0xf4f1ea, 0.3, true), -1.4 + i * 0.12, FLOOR + 1.07, zb + 0.6, 12))
  const menu = picture(2.2, 1.1, (ctx, cw, ch) => {
    ctx.fillStyle = "#23282a"
    ctx.fillRect(0, 0, cw, ch)
    ctx.fillStyle = "#efe9dc"
    ctx.font = HAND(70)
    ctx.fillText("Coffee", 50, 110)
    ctx.fillText("Latte", 50, 200)
    ctx.fillText("Tea", 50, 290)
    ctx.fillText("Croissant", 50, 380)
    ctx.textAlign = "right"
    for (const [i, p] of ["3", "4.5", "3", "3.5"].entries()) ctx.fillText(p, cw - 50, 110 + i * 90)
  }, M.wood(0x3a2a20))
  menu.position.set(-1.1, FLOOR + 2.3, zb + 0.01)
  g.add(menu)
  // pendants and small tables
  for (const x of [-2.8, -1.1, 0.6]) {
    g.add(cylinder(0.008, 0.008, 1.1, M.metal(0x1d1d1d), x, FLOOR + h - 1.1, zb + 1.6, 6))
    g.add(cylinder(0.05, 0.16, 0.18, M.metal(0x2a2a2a, 0.4), x, FLOOR + h - 1.28, zb + 1.6, 18))
    g.add(ball(0.05, M.bulb(0xffd4a0, 5), x, FLOOR + h - 1.3, zb + 1.6, 10))
  }
  sockets.push({ at: V(-1.1, FLOOR + 1.9, zb + 1.6), color: 0xffd2a0, power: 16, range: 9, night: false })
  const round = (x: number, z: number) => {
    const t = new THREE.Group()
    t.add(cylinder(0.36, 0.36, 0.03, M.paint(0xe8e2d6, 0.3, true), 0, 0.72, 0, 28))
    t.add(cylinder(0.03, 0.03, 0.72, M.metal(0x1d1d1d), 0, 0, 0, 10))
    t.add(cylinder(0.22, 0.22, 0.02, M.metal(0x1d1d1d), 0, 0, 0, 20))
    t.position.set(x, FLOOR, z)
    return t
  }
  g.add(round(-0.9, -2.6), round(-2.8, -2.2), round(2.4, -3.2))
  g.add(chair(M.wood(0x6a4a34), -0.9, -3.52, 0), chair(M.wood(0x6a4a34), -2.8, -1.6, Math.PI), chair(M.wood(0x6a4a34), 2.4, -3.8, 0))
  // a saucer for the coffee in hand, and the morning brief beside it if you'd like one
  g.add(cylinder(0.08, 0.08, 0.01, M.paint(0xf6f3ec, 0.3, true), -0.65, FLOOR + 0.75, -2.5, 20))
  const brief = new Board(420, 594)
  brief.draw("brief", (ctx, cw, ch) => {
    // the morning brief, printed: the same three parts as the real one (Setup.tsx's example)
    ctx.fillStyle = "#fcfbf8"
    ctx.fillRect(0, 0, cw, ch)
    ctx.fillStyle = "#6a6f7a"
    ctx.font = FONT(500, 20)
    ctx.fillText("Tuesday", 34, 50)
    ctx.fillStyle = "#1f2430"
    ctx.font = FONT(800, 40)
    ctx.fillText("Good morning", 34, 96)
    const parts: [string, [string, string, string][]][] = [
      ["WHAT MATTERS TODAY", [["#3f8f5a", "Problem set 6", "10:30"], ["#3f8f5a", "Essay draft", "1:00"]]],
      ["FIXED TODAY", [["#4a74c4", "Chem lecture", "9:00"]]],
      ["HEADS UP", [["#c9893a", "Lab report", "Thu"]]],
    ]
    let y = 146
    for (const [head, rows] of parts) {
      ctx.fillStyle = "#6a6f7a"
      ctx.font = FONT(700, 16)
      ctx.fillText(head, 34, y)
      y += 34
      for (const [color, what, when] of rows) {
        ctx.fillStyle = color
        ctx.fillRect(34, y - 22, 7, 30)
        ctx.fillStyle = "#1f2430"
        ctx.font = FONT(700, 24)
        ctx.fillText(what, 54, y)
        ctx.fillStyle = "#6a6f7a"
        ctx.font = FONT(500, 20)
        ctx.textAlign = "right"
        ctx.fillText(when, cw - 34, y)
        ctx.textAlign = "left"
        y += 44
      }
      y += 12
    }
  })
  const paper = panel(0.21, 0.297, new THREE.MeshStandardMaterial({ map: brief.texture, roughness: 0.9, envMapIntensity: 0.5 }), 0, 0, 0)
  paper.rotation.x = -Math.PI / 2
  paper.rotation.z = 0.3
  paper.position.set(-0.98, FLOOR + 0.752, -2.6)
  paper.userData.live = true
  g.add(paper)
  const phone = block(0.075, 0.009, 0.15, M.paint(0x1a1a1a, 0.2, true), -1.0, FLOOR + 0.75, -2.62, 0.008)
  phone.userData.live = true
  phone.rotation.y = 0.4
  g.add(phone)
  g.add(plant(3.4, -1.0, 1.2))
  finish(g, cut, stub)
  return {
    group: g,
    cut,
    stub,
    size: { w: w + 2 * T, d: d + 2 * T },
    scene: (_spot, a) => ({ via: [V(0.25, FLOOR, -2.4)], walk: V(-0.3, FLOOR, -3.12), at: V(-0.9, FLOOR, -3.48), yaw: 0, front: 0.3, action: "coffee", mood: { paper: a.brief }, cam: cam(V(-0.8, 1.0, -2.9), [1.8, 2.9, 6.0]) }),
    door: { inside: V(0.6, 0, -1.0), outside: V(0.6, 0, 1.6) },
    sockets,
    clear: [[-w / 2 - T - 0.3, -d - 2 * T - 0.3, w / 2 + T + 0.3, 0.6], [-0.2, 0, 1.4, 2.8]],
    room: [-w / 2, -d - T, w / 2, -T],
    show: (a) => {
      paper.visible = a.brief
      phone.visible = !a.brief
    },
  }
}

/** A chat's window, as each AI's own app looks (shapes and colours, big), or an install bar for one on this Mac. */
function drawAi(ctx: CanvasRenderingContext2D, cw: number, ch: number, ai: Extra["ai"], progress: number | null): void {
  const round = (x: number, y: number, w: number, h: number, r: number, fill: string, stroke?: string) => {
    ctx.beginPath()
    ctx.roundRect(x, y, w, h, r)
    ctx.fillStyle = fill
    ctx.fill()
    if (stroke) {
      ctx.lineWidth = 4
      ctx.strokeStyle = stroke
      ctx.stroke()
    }
  }
  const centred = (text: string, y: number, font: string, color: string) => {
    ctx.font = font
    ctx.fillStyle = color
    ctx.textAlign = "center"
    ctx.fillText(text, cw / 2 + 40, y)
    ctx.textAlign = "left"
  }
  const sidebar = (bg: string, line: string) => {
    ctx.fillStyle = bg
    ctx.fillRect(0, 0, 80, ch)
    ctx.fillStyle = line
    for (let i = 0; i < 6; i++) ctx.fillRect(16, 40 + i * 34, 48 - ((i * 13) % 20), 10)
  }
  const unready = () => {
    if (!ai || ai.ready || ai.provider === "local") return // a Mac model's install bar says it
    round(cw / 2 - 150, 18, 300, 44, 22, "#f6c453")
    centred("Not signed in yet", 49, FONT(700, 24), "#3a2a08")
  }
  const provider = ai?.provider ?? "none"
  if (provider === "claude") {
    // Claude: warm paper, the orange star, a greeting, the box to write in
    ctx.fillStyle = "#f4f0e6"
    ctx.fillRect(0, 0, cw, ch)
    sidebar("#ebe5d8", "#d6cfc0")
    const sx = cw / 2 - 120
    ctx.strokeStyle = "#d97757"
    ctx.lineWidth = 9
    ctx.lineCap = "round"
    for (let i = 0; i < 8; i++) {
      const a = (i / 8) * Math.PI * 2
      ctx.beginPath()
      ctx.moveTo(sx + Math.cos(a) * 6, 150 + Math.sin(a) * 6)
      ctx.lineTo(sx + Math.cos(a) * 26, 150 + Math.sin(a) * 26)
      ctx.stroke()
    }
    ctx.font = `600 46px "Source Serif 4", Georgia, serif`
    ctx.fillStyle = "#3d3929"
    ctx.fillText("Good morning", sx + 44, 166)
    round(130, 230, cw - 180, 110, 22, "#ffffff", "#e0d9ca")
    ctx.fillStyle = "#b7ae9c"
    ctx.font = FONT(500, 24)
    ctx.fillText("How can I help you today?", 156, 274)
    round(cw - 106, 286, 44, 40, 10, "#d97757")
  } else if (provider === "openai") {
    // ChatGPT: white, a grey sidebar, the question in the middle, a round box with a black send button
    ctx.fillStyle = "#ffffff"
    ctx.fillRect(0, 0, cw, ch)
    sidebar("#f4f4f4", "#dcdcdc")
    centred("What can I help with?", 170, FONT(700, 38), "#202123")
    round(120, 214, cw - 160, 86, 43, "#ffffff", "#d9d9e3")
    ctx.fillStyle = "#a0a0aa"
    ctx.font = FONT(500, 24)
    ctx.fillText("Ask anything", 152, 266)
    ctx.beginPath()
    ctx.arc(cw - 82, 257, 24, 0, Math.PI * 2)
    ctx.fillStyle = "#0d0d0d"
    ctx.fill()
  } else if (provider === "gemini") {
    ctx.fillStyle = "#ffffff"
    ctx.fillRect(0, 0, cw, ch)
    sidebar("#f0f4f9", "#d3dde9")
    ctx.font = FONT(700, 46)
    ctx.fillStyle = "#4b7be5"
    ctx.textAlign = "center"
    ctx.fillText("Hello", cw / 2 + 40, 165)
    ctx.textAlign = "left"
    round(120, 214, cw - 160, 86, 43, "#f0f4f9")
    ctx.fillStyle = "#7c8796"
    ctx.font = FONT(500, 24)
    ctx.fillText("Ask Gemini", 152, 266)
  } else if (provider === "grok") {
    ctx.fillStyle = "#0e0e10"
    ctx.fillRect(0, 0, cw, ch)
    centred("Grok", 165, FONT(800, 50), "#f2f2f2")
    round(100, 214, cw - 200, 86, 43, "#1f1f23", "#34343a")
    ctx.fillStyle = "#7a7a82"
    ctx.font = FONT(500, 24)
    ctx.fillText("What do you want to know?", 132, 266)
  } else if (provider === "local") {
    // an open model on this Mac: the download first, a bar filling up; then the model, running here
    ctx.fillStyle = "#1e1f24"
    ctx.fillRect(0, 0, cw, ch)
    round(40, 40, cw - 80, ch - 80, 18, "#2b2d33")
    for (const [i, c] of ["#ff5f57", "#febc2e", "#28c840"].entries()) {
      ctx.beginPath()
      ctx.arc(72 + i * 26, 70, 9, 0, Math.PI * 2)
      ctx.fillStyle = c
      ctx.fill()
    }
    const name = ai?.model || ai?.name || "an open model"
    if (ai?.ready && progress === null) {
      ctx.fillStyle = "#e9e9ee"
      ctx.font = FONT(700, 30)
      ctx.fillText(name, 72, 150)
      ctx.fillStyle = "#3fbf6a"
      ctx.font = FONT(600, 24)
      ctx.fillText("Running on this Mac", 72, 196)
      round(72, 240, cw - 144, 64, 14, "#1e1f24")
      ctx.fillStyle = "#8a8c95"
      ctx.fillText("> Read my syllabus", 96, 282)
    } else {
      const share = progress ?? 0
      ctx.fillStyle = "#e9e9ee"
      ctx.font = FONT(700, 30)
      ctx.fillText(progress === null ? "Ready to install" : "Installing", 72, 140)
      ctx.fillStyle = "#a6a8b0"
      ctx.font = FONT(500, 24)
      ctx.fillText(name, 72, 180)
      round(72, 220, cw - 144, 34, 17, "#16171b")
      if (share > 0) round(72, 220, Math.max(34, (cw - 144) * share), 34, 17, "#4c8cf5")
      ctx.fillStyle = "#e9e9ee"
      ctx.font = FONT(700, 26)
      ctx.fillText(`${Math.round(share * 100)}%`, 72, 300)
    }
  } else if (provider === "none") {
    // nothing chosen: the choices
    ctx.fillStyle = "#f5f4f0"
    ctx.fillRect(0, 0, cw, ch)
    ctx.fillStyle = "#1f2430"
    ctx.font = FONT(800, 34)
    ctx.fillText("Choose an AI", 40, 70)
    const options: [string, string][] = [["Claude", "#d97757"], ["ChatGPT", "#0d0d0d"], ["Gemini", "#4b7be5"], ["On this Mac", "#3fbf6a"]]
    options.forEach(([label, color], i) => {
      const y = 100 + i * 70
      round(40, y, cw - 80, 56, 12, "#ffffff", "#dedbd3")
      round(58, y + 16, 24, 24, 6, color)
      ctx.fillStyle = "#1f2430"
      ctx.font = FONT(700, 26)
      ctx.fillText(label, 100, y + 38)
    })
  } else {
    // another service: a chat like the rest, with its name
    ctx.fillStyle = "#fafafa"
    ctx.fillRect(0, 0, cw, ch)
    sidebar("#efefef", "#d8d8d8")
    centred(ai?.name ?? "AI", 165, FONT(800, 46), "#202123")
    round(120, 214, cw - 160, 86, 43, "#ffffff", "#d9d9e3")
  }
  unready()
}

function post(): Built {
  const g = new THREE.Group()
  const sockets: Socket[] = []
  const w = 9
  const d = 7
  const h = 3.6
  const { cut, stub } = building(g, { w, d, h, outer: M.brick(), inner: M.plaster(0xe8e4da), floor: M.floor(0xa0907a), door: { x: 0, w: 1.6, color: 0x23364a }, front: [{ x: -2.9, w: 1.6, y0: 1.1, y1: 3.2 }, { x: 2.9, w: 1.6, y0: 1.1, y1: 3.2 }], back: [], above: 0, roof: "flat", seed: 61 }, sockets)
  const sign = new Board(1024, 128)
  sign.draw("post", (ctx, cw, ch) => {
    ctx.fillStyle = "#e8e2d2"
    ctx.fillRect(0, 0, cw, ch)
    ctx.fillStyle = "#23364a"
    ctx.font = FONT(800, 78)
    ctx.textAlign = "center"
    ctx.textBaseline = "middle"
    ctx.fillText("POST OFFICE", cw / 2, ch / 2 + 3)
  })
  cut.add(panel(4.6, 0.58, new THREE.MeshStandardMaterial({ map: sign.texture, roughness: 0.6 }), 0, FLOOR + 3.45, 0.03))
  // the counter, its screen, parcels
  g.add(span(-2.4, 3.6, FLOOR, FLOOR + 1.05, -4.9, -4.25, M.wood(0x6a5040)))
  g.add(span(-2.45, 3.65, FLOOR + 1.05, FLOOR + 1.1, -4.95, -4.2, M.paint(0xd9d2c4, 0.35, true)))
  // the screen shows the AI you chose, as you'd see it (30 Oct: "it should show the claude chat interface for claude,
  // the chatgpt one for openai and for a mac model it should show an install bar"): drawn big, to read in pixels
  const screen = new Board(640, 400)
  const showAi = (ai: Extra["ai"]) => {
    const progress = ai?.progress == null ? null : Math.round(ai.progress * 50) / 50
    screen.draw(JSON.stringify([ai?.provider, ai?.name, ai?.ready, ai?.model, progress]), (ctx, cw, ch) => drawAi(ctx, cw, ch, ai, progress))
  }
  showAi(null)
  const monitor = new THREE.Group()
  monitor.add(block(1.22, 0.79, 0.04, M.paint(0x1d1d1d, 0.3, true), 0, 0.26, 0, 0.01))
  monitor.add(block(0.07, 0.3, 0.07, M.paint(0x1d1d1d, 0.3, true), 0, 0, -0.03), block(0.3, 0.02, 0.22, M.paint(0x1d1d1d, 0.3, true), 0, 0, -0.03))
  monitor.add(panel(1.15, 0.72, new THREE.MeshStandardMaterial({ color: 0x000000, emissive: 0xffffff, emissiveMap: screen.texture, emissiveIntensity: 1.1, roughness: 0.2 }), 0, 0.655, 0.021))
  monitor.position.set(0.8, FLOOR + 1.1, -4.6)
  monitor.rotation.y = -0.15
  g.add(monitor)
  for (const [x, s, c] of [[2.6, 0.5, 0xc9a57a], [3.1, 0.36, 0xb8925f], [2.85, 0.3, 0xd2b48a]] as const) g.add(block(s, s * 0.7, s * 0.8, M.paint(c, 0.85, true), x, FLOOR + 1.1, -4.55, 0.01))
  g.add(block(0.4, 0.06, 0.32, M.metal(0xc9ccd0, 0.3), -1.6, FLOOR + 1.1, -4.55, 0.01)) // the scale
  // the wall of boxes, on the left
  const boxes = new THREE.Group()
  const brass = M.metal(0xb89a5a, 0.3)
  boxes.add(span(-2.8, 2.8, 0, 2.3, -0.05, 0, M.wood(0x5a4232)))
  // theirs: a door that opens, with a letter inside (30 Oct: "when something is being read make him interact with
  // one of the mailboxes")
  const MINE = [3, 5] // row, column: in front of where they stand, at chest height
  const hinge = new THREE.Group()
  hinge.userData.live = true
  for (let r = 0; r < 7; r++) {
    for (let c = 0; c < 12; c++) {
      const x = -2.6 + c * 0.44 + 0.2
      const y = 0.25 + r * 0.29
      if (r === MINE[0] && c === MINE[1]) {
        boxes.add(block(0.38, 0.24, 0.02, M.paint(0x15110d, 0.9, true), x, y, -0.03))
        const letter = block(0.2, 0.012, 0.14, M.paint(0xf6f1e4, 0.8, true), x + 0.02, y + 0.03, -0.05)
        letter.rotation.x = Math.PI / 2 - 0.25
        boxes.add(letter)
        hinge.position.set(x - 0.19, y, 0.01)
        hinge.add(block(0.38, 0.24, 0.03, brass, 0.19, 0, 0, 0.005))
        hinge.add(block(0.08, 0.04, 0.02, M.paint(0x1d1d1d, 0.4), 0.09, 0.16, 0.025))
        continue
      }
      boxes.add(block(0.38, 0.24, 0.03, brass, x, y, 0.01, 0.005))
      boxes.add(block(0.08, 0.04, 0.02, M.paint(0x1d1d1d, 0.4), x - 0.1, y + 0.16, 0.035))
    }
  }
  boxes.add(hinge)
  boxes.position.set(-w / 2 + 0.05, FLOOR, -3.6)
  boxes.rotation.y = Math.PI / 2
  g.add(boxes)
  // the calendar on the right wall
  const month = picture(0.9, 1.2, (ctx, cw, ch) => {
    ctx.fillStyle = "#fbfaf6"
    ctx.fillRect(0, 0, cw, ch)
    ctx.fillStyle = "#3a5a7a"
    ctx.fillRect(0, 0, cw, ch * 0.42)
    ctx.fillStyle = "#ffffff"
    ctx.font = FONT(800, 48)
    ctx.fillText("NOVEMBER", 26, ch * 0.38)
    ctx.fillStyle = "#1f2430"
    ctx.font = FONT(600, 20)
    for (let i = 0; i < 35; i++) {
      const x = 22 + (i % 7) * ((cw - 44) / 7)
      const y = ch * 0.48 + Math.floor(i / 7) * ((ch * 0.48) / 5)
      if (i >= 2 && i < 32) ctx.fillText(String(i - 1), x, y + 22)
      if ([5, 9, 12, 16, 19, 23, 26].includes(i)) {
        ctx.fillStyle = ["#4a74c4", "#3f8f5a", "#c9893a"][i % 3]
        ctx.fillRect(x, y + 32, 36, 8)
        ctx.fillStyle = "#1f2430"
      }
    }
  }, null)
  month.position.set(w / 2 - 0.01, FLOOR + 1.65, -3.2)
  month.rotation.y = -Math.PI / 2
  g.add(month)
  for (const x of [-2, 2]) {
    g.add(span(x - 0.6, x + 0.6, FLOOR + h - 0.06, FLOOR + h, -3.5, -3.2, M.bulb(0xfff0dc, 3)))
  }
  sockets.push({ at: V(0, FLOOR + h - 0.4, -3.4), color: 0xfff0dc, power: 18, range: 10, night: false })
  finish(g, cut, stub)
  let reading = false
  let openUntil = -10
  return {
    group: g,
    cut,
    stub,
    size: { w: w + 2 * T, d: d + 2 * T },
    scene: (spot, _a, extra) =>
      [
        // beside the screen, so you can read the AI on it over their shoulder
        { walk: V(0.0, FLOOR, -3.62), at: V(0.0, FLOOR, -3.62), yaw: Math.PI - 0.45, action: "counter" as const, cam: { look: V(0.22, 1.6, -4.05), pos: V(1.55, 2.35, -1.25) } },
        { walk: V(-3.82, FLOOR, -3.4), at: V(-3.82, FLOOR, -3.4), yaw: extra.reading ? -Math.PI / 2 + 1.25 : -Math.PI / 2, action: extra.reading ? ("mail" as const) : ("boxes" as const), cam: cam(V(-3.9, 1.35, -3.4), [3.4, 2.4, 4.6]) },
        { walk: V(3.85, FLOOR, -3.2), at: V(3.85, FLOOR, -3.2), yaw: Math.PI / 2, action: "calendar" as const, cam: cam(V(3.8, 1.4, -3.2), [-3.4, 2.7, 5.4]) },
      ][Math.min(spot, 2)],
    door: { inside: V(0, 0, -1.0), outside: V(0, 0, 1.6) },
    sockets,
    clear: [[-w / 2 - T - 0.3, -d - 2 * T - 0.3, w / 2 + T + 0.3, 0.6], [-0.9, 0, 0.9, 2.8]],
    room: [-w / 2, -d - T, w / 2, -T],
    show: () => {},
    extra: (e) => {
      showAi(e.ai)
      reading = e.reading
    },
    cue: (name, seconds) => {
      if (name === "open") openUntil = seconds + 6.5
    },
    tick: (seconds, _m, step) => {
      // the box's door swings open when a letter comes (walk/World.ts cues it as they reach for it), and while
      // something's being read, and shut after
      const target = step === "bring" && (reading || seconds < openUntil) ? -1.9 : 0
      hinge.rotation.y += (target - hinge.rotation.y) * 0.18
    },
  }
}

/** The places that are built (the start and the end are only the street). */
export function buildPlace(place: Place): Built | null {
  switch (place) {
    case "dorm":
      return dorm()
    case "library":
      return library()
    case "hall":
      return hall()
    case "home":
      return home()
    case "night":
      return night()
    case "park":
      return park()
    case "cafe":
      return cafe()
    case "post":
      return post()
    default:
      return null
  }
}
