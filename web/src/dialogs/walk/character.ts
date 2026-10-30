// The one who walks you through your week (29 Oct, after the realistic street: "revert back to doing some pixel sprite
// thing but make it more engaging not just a sprite going from left to right - make the sprite a lot better"): a
// student in a hoodie with a backpack, built in 3D and drawn as pixel art with the rest of the town (walk/World.ts
// renders everything at a low resolution with outlines). Because it's a real body with joints, it can do what the
// week has in it, from any side: walk and run, get into bed and tuck in, sleep, sit up and stretch when the alarm
// goes, study, pin a note on a board, sit back with crossed legs, picnic, sip coffee, wave. Every pose is a few joint
// angles, blended; everything moves slowly and smoothly (30 Oct: "some of the actions/camera movements/reactions are
// super unnatural"): no shaking, nothing faster than a breath, a wave or a step.

import * as THREE from "three"

export type Action = "stand" | "wave" | "wake" | "sleep" | "study" | "read" | "tv" | "laptop" | "picnic" | "coffee" | "counter" | "boxes" | "calendar"

/** How high each action sits: the seat's height above the floor. */
export const SEATED: Partial<Record<Action, number>> = { study: 0.48, tv: 0.48, laptop: 0.48, coffee: 0.48, picnic: 0.06, wake: 0.56, sleep: 0.56 }

let ramp: THREE.DataTexture | null = null
function toon(color: number): THREE.MeshToonMaterial {
  if (!ramp) {
    ramp = new THREE.DataTexture(new Uint8Array([80, 170, 255]), 3, 1, THREE.RedFormat)
    ramp.minFilter = ramp.magFilter = THREE.NearestFilter
    ramp.generateMipmaps = false
    ramp.needsUpdate = true
  }
  // a little light of its own, so they read in the dusk and the dawn as a game's hero does
  const c = new THREE.Color(color)
  return new THREE.MeshToonMaterial({ color, gradientMap: ramp, emissive: c.multiplyScalar(0.22) })
}

const SKIN = 0xf2c6a2
const HAIR = 0x3a2820
const HOODIE = 0x4a84d8
const JEANS = 0x2d3447
const SHOE = 0xf3f0ea
const PACK = 0xb5532e

function part(geo: THREE.BufferGeometry, color: number | THREE.Material, x = 0, y = 0, z = 0): THREE.Mesh {
  const mesh = new THREE.Mesh(geo, typeof color === "number" ? toon(color) : color)
  mesh.position.set(x, y, z)
  mesh.castShadow = true
  mesh.receiveShadow = true
  return mesh
}
const capsule = (r: number, len: number) => new THREE.CapsuleGeometry(r, len, 4, 10)
const sphere = (r: number) => new THREE.SphereGeometry(r, 18, 14)
function rounded(w: number, h: number, d: number, r: number): THREE.BufferGeometry {
  const shape = new THREE.Shape()
  const x = -w / 2
  const y = -h / 2
  shape.moveTo(x + r, y)
  shape.lineTo(x + w - r, y)
  shape.quadraticCurveTo(x + w, y, x + w, y + r)
  shape.lineTo(x + w, y + h - r)
  shape.quadraticCurveTo(x + w, y + h, x + w - r, y + h)
  shape.lineTo(x + r, y + h)
  shape.quadraticCurveTo(x, y + h, x, y + h - r)
  shape.lineTo(x, y + r)
  shape.quadraticCurveTo(x, y, x + r, y)
  const geo = new THREE.ExtrudeGeometry(shape, { depth: d - 2 * r * 0.6, bevelEnabled: true, bevelThickness: r * 0.6, bevelSize: r * 0.5, bevelSegments: 3, curveSegments: 4 })
  geo.translate(0, 0, -(d - 2 * r * 0.6) / 2)
  return geo
}

/** A pose: every joint's angle, how high the hips are, and the rest. Blended number by number. */
export interface Pose {
  lift: number // the hips' height above the floor under them
  body: number // the whole body tipped back about the hips (lying down)
  lean: number // the chest forward
  twist: number
  headX: number
  headY: number
  headZ: number
  armX: [number, number] // left, right: forward and up
  armZ: [number, number] // out to the side
  elbow: [number, number]
  legX: [number, number]
  legZ: [number, number]
  knee: [number, number]
  eyes: number // 1 open, 0 shut
}

const HIPS = 0.74

function stand(): Pose {
  return { lift: HIPS, body: 0, lean: 0, twist: 0, headX: 0, headY: 0, headZ: 0, armX: [0.05, 0.05], armZ: [0.1, -0.1], elbow: [-0.15, -0.15], legX: [0, 0], legZ: [0.02, -0.02], knee: [0, 0], eyes: 1 }
}

function sitting(seat: number): Pose {
  const p = stand()
  p.lift = seat + 0.07
  p.legX = [-1.5, -1.5]
  p.knee = [1.45, 1.45]
  p.legZ = [0.08, -0.08]
  p.armX = [-0.35, -0.35]
  p.elbow = [-0.7, -0.7] // hands on the lap
  return p
}

export function mixPose(a: Pose, b: Pose, t: number): Pose {
  const n = (x: number, y: number) => x + (y - x) * t
  const two = (x: [number, number], y: [number, number]): [number, number] => [n(x[0], y[0]), n(x[1], y[1])]
  return {
    lift: n(a.lift, b.lift),
    body: n(a.body, b.body),
    lean: n(a.lean, b.lean),
    twist: n(a.twist, b.twist),
    headX: n(a.headX, b.headX),
    headY: n(a.headY, b.headY),
    headZ: n(a.headZ, b.headZ),
    armX: two(a.armX, b.armX),
    armZ: two(a.armZ, b.armZ),
    elbow: two(a.elbow, b.elbow),
    legX: two(a.legX, b.legX),
    legZ: two(a.legZ, b.legZ),
    knee: two(a.knee, b.knee),
    eyes: n(a.eyes, b.eyes),
  }
}
const mix = mixPose

const cycle = (t: number, period: number) => ((t % period) + period) % period
export const ease = (x: number) => {
  const c = Math.max(0, Math.min(1, x))
  return c * c * (3 - 2 * c)
}
/** Up from `a` and back down by `b`, easing over `fade` at each end. */
const span = (t: number, a: number, b: number, fade = 0.5) => Math.min(ease((t - a) / fade), ease((b - t) / fade))
const clamp01 = (x: number) => Math.max(0, Math.min(1, x))

/** In bed and getting in and out of it: the poses the scenes in walk/World.ts move between. `top` is the mattress's
 * height above the floor. */
export const BED = {
  stand,
  /** Standing by the bed, reaching down to throw the covers back. */
  reach(): Pose {
    const p = stand()
    p.lean = 0.45
    p.headX = 0.35
    p.armX = [-0.5, -1.05]
    p.armZ = [0.15, -0.1]
    p.elbow = [-0.4, -0.3]
    p.knee = [0.15, 0.15]
    p.lift = HIPS - 0.03
    return p
  },
  /** Sitting on its edge, feet on the floor. */
  edge(top: number): Pose {
    const p = sitting(top)
    p.armX = [0.25, 0.25]
    p.armZ = [0.35, -0.35]
    p.elbow = [-0.1, -0.1] // hands on the mattress either side
    return p
  },
  /** Sitting on its edge with the legs up off the floor, straight out over it, to swing them round. */
  lift(top: number): Pose {
    const p = BED.edge(top)
    p.legX = [-1.55, -1.55]
    p.knee = [0.25, 0.25]
    p.lean = -0.18
    p.armX = [0.45, 0.45]
    return p
  },
  /** Lying on the back, head on the pillow. */
  lie(top: number): Pose {
    const p = stand()
    p.body = -Math.PI / 2
    p.lift = top + 0.07 // sunk a little into the mattress, so the toes don't tent the covers
    p.legX = [0, 0]
    p.legZ = [0.04, -0.04]
    p.knee = [0.06, 0.06]
    p.armX = [-0.45, -0.45]
    p.armZ = [0.12, -0.12]
    p.elbow = [-1.05, -1.05] // hands on the covers
    p.headX = 0.32 // the head up on the pillow
    return p
  },
  /** Pulling the covers up to the chin. */
  tuck(top: number): Pose {
    const p = BED.lie(top)
    p.armX = [-1.05, -1.05]
    p.armZ = [-0.1, 0.1]
    p.elbow = [-1.9, -1.9]
    p.headX = 0.4
    return p
  },
  /** Sitting up in bed, legs out under the covers. */
  up(top: number): Pose {
    const p = sitting(top)
    p.legX = [-1.55, -1.55]
    p.knee = [0.05, 0.05]
    p.legZ = [0.05, -0.05]
    p.armX = [-0.2, -0.2]
    p.armZ = [0.25, -0.25]
    p.elbow = [-0.5, -0.5]
    return p
  },
}

/** How your answers have them feeling, so the same action looks different. */
export interface Mood {
  energy?: number // getting up: 0 dragging themselves up, 1 bright-eyed
  happy?: number // how much of the time is theirs
  paper?: boolean // the brief on paper, or the phone instead
  restless?: number // a late night: turning over in their sleep
}

/** What a body doing `action` looks like `t` seconds in, feeling `mood`; all slow, all smooth. */
function acting(action: Action, t: number, on: number | undefined, mood: Mood): Pose {
  const seat = on ?? SEATED[action]
  const p = seat !== undefined ? sitting(seat) : stand()
  const breath = Math.sin(t * 1.6)
  p.lean += breath * 0.015
  switch (action) {
    case "wave": {
      // a wave, then a look round, then another wave
      const c = cycle(t, 6)
      const wave = span(c, 0.2, 3.0, 0.5)
      p.armX[1] = -0.3 * wave
      p.armZ[1] = -0.1 - 2.45 * wave
      p.elbow[1] = -0.15 - wave * (0.45 + Math.sin(t * 7) * 0.3)
      p.headZ = Math.sin(t * 0.9) * 0.06
      p.headY = (1 - wave) * Math.sin(t * 0.6) * 0.4
      p.legZ = [0.02 + Math.sin(t * 0.8) * 0.03, -0.02 + Math.sin(t * 0.8) * 0.03]
      break
    }
    case "wake": {
      // sitting up in bed: a long, slow stretch and a yawn, arms down, a rub of the eyes when it's early, then a
      // look round the room. Up early it's a small, slow stretch; up late a big one.
      Object.assign(p, BED.up(seat ?? 0.56))
      const energy = mood.energy ?? 0.6
      const c = cycle(t, 8)
      const up = span(c, 0.3, 3.0, 1.1) * (0.6 + energy * 0.4)
      const rub = (1 - energy) * span(c, 3.3, 4.8, 0.45)
      p.armX = [-0.2 - up * 2.65, -0.2 - up * 2.65 - rub * 1.0]
      p.armZ = [0.25 - up * 0.05, -0.25 + up * 0.05 + rub * 0.15]
      p.elbow = [-0.5 + up * 0.35, -0.5 + up * 0.35 - rub * 1.45 + Math.sin(t * 5) * rub * 0.08]
      p.lean = -0.1 * up + (1 - energy) * 0.1 * (1 - up) + breath * 0.02
      p.headX = -0.35 * up + (1 - energy) * 0.18 * (1 - up)
      const look = span(c, 5.0, 7.8, 0.8)
      p.headY = look * Math.sin((c - 5) * 1.1) * 0.55
      p.eyes = up > 0.6 || rub > 0.4 ? 0 : 0.45 + energy * 0.55
      break
    }
    case "sleep": {
      Object.assign(p, BED.lie(seat ?? 0.56))
      p.eyes = 0
      p.lean = breath * 0.03 // a slow breath
      p.headY = 0.25 + Math.sin(t * 0.13) * 0.08
      // a late night: now and then turning onto the side and back, slowly
      const roll = (mood.restless ?? 0) * span(cycle(t, 11), 3, 8.5, 1.4)
      p.twist = roll * 0.55
      p.headY += roll * 0.5
      p.armX = [-0.45 - roll * 0.3, -0.45]
      p.legX = [-roll * 0.35, -roll * 0.2]
      p.knee = [0.06 + roll * 0.5, 0.06 + roll * 0.35]
      break
    }
    case "study": {
      // typing, unhurried, and every so often sitting back to think, chin on a hand
      const c = cycle(t, 10)
      const think = span(c, 6.6, 9.4, 0.7)
      p.armX = [-0.72 + think * 0.2, -0.72 - think * 0.75]
      p.armZ = [-0.12, 0.12 + think * 0.05]
      p.elbow = [-1.05 + Math.sin(t * 9) * 0.02 * (1 - think) - think * 0.3, -1.05 + Math.sin(t * 9 + 1.8) * 0.02 * (1 - think) - think * 1.15]
      p.lean = 0.14 * (1 - think) + breath * 0.015
      p.headX = 0.3 * (1 - think) - think * 0.05 + Math.sin(t * 0.5) * 0.03
      p.headY = think * 0.25
      break
    }
    case "read": {
      // reading the board: a hand at the chin, then pointing at the week, weight shifting
      const c = cycle(t, 9)
      const point = span(c, 4.5, 7.2, 0.6)
      p.headX = -0.12
      p.headZ = Math.sin(t * 0.5) * 0.06
      p.armX = [-0.5, -0.95 - point * 0.6]
      p.armZ = [-0.3, -0.05]
      p.elbow = [-1.7, -2.25 + point * 2.0] // one arm across, the other's hand at the chin or pointing
      p.legZ = [0.02 + Math.sin(t * 0.7) * 0.03, -0.02 + Math.sin(t * 0.7) * 0.03]
      break
    }
    case "tv": {
      // back in the sofa, legs crossed, an arm along its back; now and then a laugh, slowly
      p.lean = -0.32
      p.legX = [-1.78, -1.42]
      p.legZ = [-0.3, 0.06]
      p.knee = [1.55, 1.35]
      p.armX = [-0.3, -0.5]
      p.armZ = [0.75, -0.12]
      p.elbow = [-0.55, -1.15]
      const laugh = span(cycle(t, 9), 5.5, 7.0, 0.5)
      p.lean -= laugh * 0.08
      p.headX = -0.04 - laugh * 0.18
      p.headY = 0.05 + Math.sin(t * 0.3) * 0.06
      p.eyes = laugh > 0.6 ? 0.3 : 1
      break
    }
    case "laptop": {
      // forward on the seat, the laptop in front: typing, a stop to read
      const c = cycle(t, 8)
      const read = span(c, 5, 7.4, 0.6)
      p.lean = 0.32 - read * 0.12
      p.headX = 0.42 - read * 0.1
      p.armX = [-0.85 + read * 0.4, -0.85 + read * 0.4]
      p.armZ = [-0.12, 0.12]
      p.elbow = [-0.85 + Math.sin(t * 9) * 0.02 * (1 - read) - read * 0.6, -0.85 + Math.sin(t * 9 + 1.8) * 0.02 * (1 - read) - read * 0.6]
      break
    }
    case "picnic": {
      const happy = mood.happy ?? 0.5
      if (happy > 0.75) {
        // all day theirs: leaning back on their hands, legs out, face to the sun
        p.legX = [-1.45, -1.45]
        p.knee = [0.15, 0.4]
        p.legZ = [0.12, -0.05]
        p.lean = -0.55
        p.armX = [0.7, 0.7]
        p.armZ = [0.3, -0.3]
        p.elbow = [0, 0]
        p.headX = -0.35 + Math.sin(t * 0.4) * 0.05
        p.eyes = span(cycle(t, 7), 2, 5, 0.5) > 0.5 ? 0.15 : 1
        break
      }
      // cross-legged on the blanket, eating, looking about
      p.legX = [-1.25, -1.25]
      p.legZ = [0.95, -0.95]
      p.knee = [2.3, 2.3]
      const bite = span(cycle(t, 5.5), 0.5, 2.0, 0.45)
      p.armX = [-0.55, -0.7 - bite * 0.75]
      p.elbow = [-0.6, -1.2 - bite * 1.1]
      p.armZ = [0.25, -0.1]
      p.headX = 0.12 - bite * 0.1
      p.headY = Math.sin(t * 0.45) * 0.3 * (1 - bite)
      break
    }
    case "coffee": {
      const sip = span(cycle(t, 7), 0.6, 2.4, 0.55)
      p.armX = [-0.75, -0.75 - sip * 0.6]
      p.armZ = [-0.1, 0.05]
      p.elbow = [-0.9, -0.95 - sip * 1.35]
      p.headX = 0.35 - sip * 0.45
      p.lean = 0.08
      if (mood.paper === false) {
        // the phone in the other hand instead of the paper on the table
        p.armX[0] = -1.0
        p.elbow[0] = -1.6
        p.armZ[0] = -0.3
        p.headX = 0.5 - sip * 0.55
      }
      break
    }
    case "counter": {
      const talk = Math.sin(t * 0.8)
      p.armX = [-1.0, -1.0]
      p.armZ = [-0.1, 0.1]
      p.elbow = [-0.55, -0.55]
      p.headX = 0.05 + talk * 0.06
      p.headY = Math.sin(t * 0.35) * 0.12
      p.lean = 0.12
      break
    }
    case "boxes": {
      const c = cycle(t, 7)
      const reach = span(c, 0.4, 2.6, 0.6)
      const read = span(c, 3.0, 6.2, 0.6)
      p.armX = [0.05 - read * 1.2, -0.1 - reach * 2.0 - read * 1.2]
      p.armZ = [0.1, -0.1]
      p.elbow = [-0.15 - read * 1.0, -0.2 + reach * 0.1 - read * 1.0]
      p.headX = -0.25 * reach + 0.25 * read
      break
    }
    case "calendar": {
      const c = cycle(t, 8)
      const point = span(c, 0.6, 3.6, 0.6)
      p.armX = [0.05, -0.15 - point * 1.6]
      p.armZ = [0.1, -0.05]
      p.elbow = [-0.15, -0.15]
      p.headX = -0.12
      p.headY = Math.sin(t * 0.4) * 0.12
      p.headZ = 0.06
      break
    }
    default: {
      p.headY = Math.sin(t * 0.35) * 0.25
    }
  }
  return p
}

/** Walking and running: stride, knees lifting on the swing, arms against the legs, a bob twice a stride, a sway, and
 * leaning into it as it quickens. `phase` follows the ground covered, so feet don't slide. */
function moving(phase: number, speed: number): Pose {
  const p = stand()
  const run = clamp01((speed - 2.6) / 2.4)
  const swing = 0.48 + run * 0.42
  const s = Math.sin(phase)
  const c = Math.cos(phase)
  p.legX = [s * swing, -s * swing]
  p.knee = [Math.max(0, c) * (0.5 + run * 1.0) + 0.1, Math.max(0, -c) * (0.5 + run * 1.0) + 0.1]
  p.armX = [-s * (0.4 + run * 0.3), s * (0.4 + run * 0.3)]
  p.armZ = [0.1 + run * 0.06, -0.1 - run * 0.06]
  p.elbow = [-0.3 - run * 1.1, -0.3 - run * 1.1]
  p.lift = HIPS - 0.015 - run * 0.05 + Math.abs(c) * (0.025 + run * 0.05)
  p.lean = 0.05 + run * 0.18
  p.twist = s * (0.08 + run * 0.05)
  p.headX = -0.03 - run * 0.06
  p.headY = -s * 0.03
  return p
}

/** Something done in a moment, over whatever they're doing: an answer you just gave, acted out (a book onto the
 * pile, the timer set, the note moved), or a little thing while you decide (a glance at you, a yawn). */
export type Reaction = "cheer" | "yawn" | "nod" | "shrug" | "glance" | "scratch" | "relax" | "stackRight" | "stackLeft" | "timer" | "deskStretch" | "pin"

export const REACT_FOR: Record<Reaction, number> = { cheer: 1.5, yawn: 2.0, nod: 1.2, shrug: 1.4, glance: 2.6, scratch: 2.0, relax: 3.0, stackRight: 1.3, stackLeft: 1.3, timer: 1.5, deskStretch: 2.6, pin: 1.6 }

/** The upper body during a reaction `t` seconds in (the legs stay as they are). `look` turns the head toward you;
 * `aim` is where along a board the hand goes, -1 to 1. */
function reacting(kind: Reaction, t: number, base: Pose, look: number, aim: number, standing: boolean): Pose {
  const p: Pose = { ...base, armX: [...base.armX], armZ: [...base.armZ], elbow: [...base.elbow] }
  const swing = (period: number) => Math.sin((t / period) * Math.PI * 2)
  switch (kind) {
    case "cheer":
      p.armX = [-2.6, -2.6]
      p.armZ = [0.45, -0.45]
      p.elbow = [-0.3, -0.3]
      p.headX = -0.2
      if (standing) p.lift = base.lift + Math.max(0, Math.sin(clamp01((t - 0.2) / 0.55) * Math.PI)) * 0.1
      break
    case "yawn":
      p.armX = [base.armX[0], -1.5]
      p.armZ = [base.armZ[0], -0.15]
      p.elbow = [base.elbow[0], -2.3]
      p.headX = base.headX - 0.35
      p.eyes = 0
      p.lean = base.lean - 0.06
      break
    case "nod":
      p.headX = base.headX + Math.max(0, swing(0.6)) * 0.22
      break
    case "shrug":
      p.armX = [-0.35, -0.35]
      p.armZ = [0.8, -0.8]
      p.elbow = [-1.4, -1.4]
      p.headZ = 0.18
      break
    case "glance":
      p.headY = look
      p.headX = -0.05
      p.eyes = 1
      break
    case "scratch":
      p.armX = [base.armX[0], -2.45]
      p.armZ = [base.armZ[0], -0.5]
      p.elbow = [base.elbow[0], -2.2 + swing(0.5) * 0.08]
      p.headZ = 0.12
      break
    case "relax":
      // hands behind the head, leaning back
      p.armX = [-2.7, -2.7]
      p.armZ = [0.55, -0.55]
      p.elbow = [-2.1, -2.1]
      p.lean = base.lean - 0.15
      p.headX = base.headX - 0.1
      p.eyes = t > 0.8 && t < 2.4 ? 0.2 : 1
      break
    case "stackRight":
    case "stackLeft": {
      // a reach to the pile beside them on the desk, and back: a book on, or one off
      const i = kind === "stackRight" ? 1 : 0
      const out = kind === "stackRight" ? -1 : 1
      p.armX[i] = -1.05
      p.armZ[i] = out * 0.55
      p.elbow[i] = -0.25
      p.twist = base.twist - out * 0.3
      p.lean = base.lean + 0.18
      p.headY = out * 0.45
      p.headX = 0.35
      break
    }
    case "timer":
      // turning the kitchen timer on the desk
      p.armX = [base.armX[0], -1.2]
      p.armZ = [base.armZ[0], -0.12]
      p.elbow = [base.elbow[0], -0.45 + swing(0.6) * 0.06]
      p.lean = base.lean + 0.15
      p.headX = 0.45
      p.headY = -0.15
      break
    case "deskStretch":
      // the timer's gone: hands up, a long stretch back
      p.armX = [-2.85, -2.85]
      p.armZ = [0.18, -0.18]
      p.elbow = [-0.25, -0.25]
      p.lean = base.lean - 0.3
      p.headX = -0.3
      p.eyes = t > 0.6 && t < 2.0 ? 0 : 1
      break
    case "pin": {
      // the note moved to the day: a reach up to the board and along it
      const i = aim >= 0 ? 1 : 0
      p.armX[i] = -2.0
      p.armZ[i] = (i === 1 ? -1 : 1) * (0.1 + Math.abs(aim) * 0.55)
      p.elbow[i] = -0.2
      p.headX = -0.25
      p.headY = -aim * 0.3
      p.twist = base.twist - aim * 0.15
      break
    }
  }
  return p
}

export class Character {
  readonly root = new THREE.Group()
  private hips = new THREE.Group()
  private chest = new THREE.Group()
  private head = new THREE.Group()
  private arms: THREE.Group[] = []
  private elbows: THREE.Group[] = []
  private legs: THREE.Group[] = []
  private knees: THREE.Group[] = []
  private eyes: THREE.Mesh[] = []
  private held = new Map<string, THREE.Object3D>()
  private phase = 0
  private blink = 2

  constructor() {
    this.root.add(this.hips)
    this.hips.position.y = HIPS
    // legs: thigh, knee, shin, shoe
    for (const side of [1, -1]) {
      const hip = new THREE.Group()
      hip.position.set(side * 0.09, 0, 0)
      hip.add(part(capsule(0.078, 0.22), JEANS, 0, -0.17, 0))
      const knee = new THREE.Group()
      knee.position.y = -0.36
      knee.add(part(capsule(0.068, 0.2), JEANS, 0, -0.15, 0))
      knee.add(part(rounded(0.12, 0.085, 0.24, 0.035), SHOE, 0, -0.33, 0.045))
      knee.add(part(new THREE.BoxGeometry(0.125, 0.025, 0.245), 0x8a8f99, 0, -0.37, 0.045))
      hip.add(knee)
      this.hips.add(hip)
      this.legs.push(hip)
      this.knees.push(knee)
    }
    // the hoodie, its hood and pocket, the backpack
    this.chest.position.y = 0.06
    this.hips.add(this.chest)
    this.chest.add(part(rounded(0.38, 0.5, 0.24, 0.09), HOODIE, 0, 0.22, 0))
    this.chest.add(part(rounded(0.24, 0.12, 0.03, 0.02), 0x355f9e, 0, 0.08, 0.115))
    const hood = part(new THREE.TorusGeometry(0.115, 0.05, 8, 18), 0x355f9e, 0, 0.46, -0.06)
    hood.rotation.x = Math.PI / 2 - 0.3
    this.chest.add(hood)
    for (const x of [-0.045, 0.045]) this.chest.add(part(new THREE.CylinderGeometry(0.008, 0.008, 0.13, 5), 0xf3f0ea, x, 0.33, 0.125))
    this.chest.add(part(rounded(0.32, 0.36, 0.14, 0.05), PACK, 0, 0.24, -0.19))
    this.chest.add(part(rounded(0.22, 0.12, 0.05, 0.02), 0x9a4426, 0, 0.14, -0.27))
    for (const x of [-0.11, 0.11]) this.chest.add(part(new THREE.BoxGeometry(0.045, 0.32, 0.03), 0x7a3a22, x, 0.3, 0.11))
    // arms: shoulder, elbow, hand
    for (const side of [1, -1]) {
      const shoulder = new THREE.Group()
      shoulder.position.set(side * 0.225, 0.4, 0)
      shoulder.add(part(capsule(0.06, 0.16), HOODIE, 0, -0.13, 0))
      const elbow = new THREE.Group()
      elbow.position.y = -0.27
      elbow.add(part(capsule(0.055, 0.13), HOODIE, 0, -0.1, 0))
      elbow.add(part(sphere(0.058), SKIN, 0, -0.24, 0))
      shoulder.add(elbow)
      this.chest.add(shoulder)
      this.arms.push(shoulder)
      this.elbows.push(elbow)
    }
    // the head: face, eyes, cheeks, hair
    this.head.position.y = 0.49
    this.chest.add(this.head)
    this.head.add(part(capsule(0.05, 0.04), SKIN, 0, 0.0, 0))
    this.head.add(part(sphere(0.2), SKIN, 0, 0.18, 0))
    for (const side of [1, -1]) {
      const eye = part(sphere(0.03), 0x1e1a26, side * 0.075, 0.16, 0.172)
      eye.scale.set(0.75, 1.3, 0.5)
      eye.castShadow = false
      this.head.add(eye)
      this.eyes.push(eye)
      const cheek = part(sphere(0.03), 0xf09a8c, side * 0.12, 0.1, 0.15)
      cheek.scale.set(1.2, 0.6, 0.4)
      cheek.castShadow = false
      this.head.add(cheek)
      this.head.add(part(sphere(0.035), SKIN, side * 0.198, 0.16, 0)) // ears
    }
    const hair = part(new THREE.SphereGeometry(0.218, 22, 16, 0, Math.PI * 2, 0, Math.PI * 0.56), HAIR, 0, 0.19, -0.015)
    hair.rotation.x = -0.42
    this.head.add(hair)
    for (const [x, y, z, r] of [[-0.09, 0.3, 0.14, 0.07], [0.0, 0.32, 0.16, 0.075], [0.09, 0.3, 0.14, 0.07], [0.16, 0.22, 0.09, 0.06], [-0.16, 0.22, 0.09, 0.06]]) {
      const tuft = part(sphere(r), HAIR, x, y, z)
      tuft.scale.set(1, 0.7, 0.75)
      this.head.add(tuft)
    }
    // things in hand
    const hand = this.elbows[1]
    const cup = part(new THREE.CylinderGeometry(0.045, 0.038, 0.1, 12), 0xf6f3ec, 0, -0.28, 0.06)
    const sandwich = part(new THREE.BoxGeometry(0.12, 0.04, 0.1), 0xe8c27a, 0, -0.27, 0.05)
    const letter = part(new THREE.BoxGeometry(0.16, 0.005, 0.1), 0xfdfaf2, 0, -0.27, 0.06)
    for (const [name, thing] of [["cup", cup], ["sandwich", sandwich], ["letter", letter]] as const) {
      thing.visible = false
      hand.add(thing)
      this.held.set(name, thing)
    }
  }

  private reaction: { kind: Reaction; at: number; aim: number } | null = null
  private last: Pose = stand()

  /** Do something in a moment, over what they're doing (an answer just changed, or a fidget while you decide). */
  react(kind: Reaction, now: number, aim = 0): void {
    this.reaction = { kind, at: now, aim }
  }

  /** The pose they're in now: where a scene (getting out of bed) starts from. */
  posed(): Pose {
    return { ...this.last, armX: [...this.last.armX], armZ: [...this.last.armZ], elbow: [...this.last.elbow], legX: [...this.last.legX], legZ: [...this.last.legZ], knee: [...this.last.knee] }
  }

  /** Whether a reaction is still going. */
  busy(now: number): boolean {
    return !!this.reaction && now - this.reaction.at < REACT_FOR[this.reaction.kind]
  }

  /** Each frame: `speed` while moving (metres a second), else the action `weight` of the way in, feeling `mood`;
   * `before` is what they were doing at the same place, `change` of the way into the new action; `look` is where
   * you are, turned from where they face. `pose`, when a scene is moving them (into bed), is taken as it is. */
  update(dt: number, t: number, s: { speed: number; action: Action; weight: number; seat?: number; before?: Action; change?: number; mood?: Mood; look?: number; pose?: Pose; from?: Pose; into?: number }): void {
    const { speed, action, weight, seat, before, change = 1, mood = {}, look = 0 } = s
    // a stride longer the faster they go, so the feet keep to the ground
    const stride = 1.15 + clamp01((speed - 1.5) / 3.5) * 1.0
    this.phase += (speed * dt * Math.PI * 2) / stride
    let pose: Pose
    if (s.pose) pose = s.pose
    else {
      const doing = before ? mix(acting(before, t, seat, mood), acting(action, t, seat, mood), ease(change)) : acting(action, t, seat, mood)
      pose = mix(speed > 0.05 ? moving(this.phase, speed) : stand(), doing, ease(weight))
      if (speed <= 0.05 && weight < 1) pose.headY += Math.sin(t * 0.35) * 0.15 * (1 - weight)
    }
    if (s.from && !s.pose) pose = mix(s.from, pose, ease(s.into ?? 1)) // easing out of a scene's last pose
    const r = this.reaction
    if (r && speed <= 0.05 && !s.pose) {
      const age = t - r.at
      const length = REACT_FOR[r.kind]
      if (age >= length) this.reaction = null
      else {
        const into = span(age, 0, length, Math.min(0.5, length / 3))
        const standing = (SEATED[action] === undefined && seat === undefined) || weight < 0.5
        pose = mix(pose, reacting(r.kind, age, pose, look, r.aim, standing), into)
      }
    }
    this.last = pose
    this.apply(pose, t, dt)
    const holding = !s.pose && weight > 0.6 ? ({ coffee: "cup", picnic: "sandwich", boxes: "letter" } as Partial<Record<Action, string>>)[action] : undefined
    for (const [name, thing] of this.held) thing.visible = name === holding && !(action === "picnic" && (mood.happy ?? 0) > 0.75)
  }

  /** Where the head is, for the little signs over it. */
  headAt(): THREE.Vector3 {
    return this.head.localToWorld(new THREE.Vector3(0, 0.45, 0))
  }

  private apply(p: Pose, t: number, dt: number): void {
    this.hips.position.y = p.lift
    this.hips.rotation.set(p.body, p.twist * 0.5, 0)
    this.chest.rotation.set(p.lean, -p.twist, 0)
    this.head.rotation.set(p.headX, p.headY, p.headZ)
    for (let i = 0; i < 2; i++) {
      this.arms[i].rotation.set(p.armX[i], 0, p.armZ[i])
      this.elbows[i].rotation.set(p.elbow[i], 0, 0)
      this.legs[i].rotation.set(p.legX[i], 0, p.legZ[i])
      this.knees[i].rotation.set(p.knee[i], 0, 0)
    }
    // a blink every few seconds
    this.blink -= dt
    let open = p.eyes
    if (this.blink < 0) {
      open = 0.1
      if (this.blink < -0.12) this.blink = 2.5 + ((t * 7.3) % 2.5)
    }
    for (const eye of this.eyes) eye.scale.y = 1.3 * Math.max(0.12, open)
  }
}

/** Little signs over the head: z's while asleep, a ! when the alarm goes, a drop of sweat, a note. Drawn as pixels. */
export class Signs {
  readonly group = new THREE.Group()
  private live: { sprite: THREE.Sprite; born: number; life: number; drift: THREE.Vector3 }[] = []
  private textures = new Map<string, THREE.Texture>()
  private last = 0

  private texture(kind: string): THREE.Texture {
    const found = this.textures.get(kind)
    if (found) return found
    const c = document.createElement("canvas")
    c.width = c.height = 16
    const ctx = c.getContext("2d") as CanvasRenderingContext2D
    ctx.imageSmoothingEnabled = false
    const px = (rows: string[], colors: Record<string, string>) =>
      rows.forEach((row, y) =>
        [...row].forEach((ch, x) => {
          if (colors[ch]) {
            ctx.fillStyle = colors[ch]
            ctx.fillRect(x, y, 1, 1)
          }
        }),
      )
    if (kind === "z") px(["", "", "", "  oooooooooo", "  owwwwwwwwo", "  oooooowwwo", "      owwoo", "     owwoo", "    owwoo", "   owwoo", "  owwooooo", "  owwwwwwwwo", "  oooooooooo"], { o: "#2b2f55", w: "#f4f6ff" })
    if (kind === "!") px(["      oooo", "      owwo", "      owwo", "      owwo", "      owwo", "      owwo", "      owwo", "      oooo", "      owwo", "      oooo"], { o: "#7a1d14", w: "#ffdf4a" })
    if (kind === "sweat") px(["", "", "      oo", "     obbo", "    obbbbo", "   obbwbbbo", "   obwbbbbo", "   obbbbbbo", "    obbbbo", "     oooo"], { o: "#1f4a8a", b: "#8fd0ff", w: "#ffffff" })
    if (kind === "note") px(["", "      oooooo", "      owwwwo", "      oo  oo", "      o    o", "      o    o", "   oooo  oooo", "  owwwo owwwo", "  owwwo owwwo", "   ooo   ooo"], { o: "#3a2a4a", w: "#f2c14e" })
    if (kind === "heart") px(["", "", "   oo   oo", "  owwo owwo", " owwwwowwwwo", " owwwwwwwwwo", " owwwwwwwwwo", "  owwwwwwwo", "   owwwwwo", "    owwwo", "     owo", "      o"], { o: "#7a1d2e", w: "#ff7b8f" })
    if (kind === "?") px(["    oooooo", "   owwwwwwo", "  owwooowwwo", "  owwo  owwo", "   oo  owwwo", "      owwo", "     owwo", "     owwo", "     oooo", "     owwo", "     oooo"], { o: "#2b2f55", w: "#f4f6ff" })
    if (kind === "steam") px(["", "", "     ww", "    w", "    w", "     ww", "       w", "       w", "     ww"], { w: "rgba(255,255,255,0.8)" })
    const tex = new THREE.CanvasTexture(c)
    tex.magFilter = tex.minFilter = THREE.NearestFilter
    tex.generateMipmaps = false
    tex.colorSpace = THREE.SRGBColorSpace
    this.textures.set(kind, tex)
    return tex
  }

  /** A sign rising from `at`. */
  emit(kind: string, at: THREE.Vector3, now: number, size = 0.32): void {
    const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: this.texture(kind), transparent: true, depthWrite: false, fog: false }))
    sprite.scale.setScalar(size)
    sprite.position.copy(at)
    this.group.add(sprite)
    this.live.push({ sprite, born: now, life: kind === "!" ? 1.2 : 2.6, drift: new THREE.Vector3((Math.sin(now * 3.1) * 0.5 + 0.2) * 0.1, 0.22, 0) })
  }

  /** What's showing for an action now and then: z's in bed, steam off the coffee. */
  every(action: Action, weight: number, head: THREE.Vector3, now: number): void {
    if (weight < 0.95) return
    const gap = ({ sleep: 2.4, coffee: 2.2 } as Partial<Record<Action, number>>)[action]
    if (!gap || now - this.last < gap) return
    this.last = now
    const kind = action === "sleep" ? "z" : "steam"
    this.emit(kind, head.clone().add(new THREE.Vector3(0.18, kind === "steam" ? -0.4 : 0.05, 0)), now, 0.3)
  }

  update(now: number, dt: number): void {
    this.live = this.live.filter((s) => {
      const age = now - s.born
      if (age > s.life) {
        this.group.remove(s.sprite)
        s.sprite.material.dispose()
        return false
      }
      s.sprite.position.addScaledVector(s.drift, dt)
      s.sprite.material.opacity = Math.min(1, (s.life - age) / 0.5, age / 0.15)
      return true
    })
  }
}
