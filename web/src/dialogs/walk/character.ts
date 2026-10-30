// The one who walks you through your week (29 Oct, after the realistic street: "revert back to doing some pixel sprite
// thing but make it more engaging not just a sprite going from left to right - make the sprite a lot better"): a
// student in a hoodie with a backpack, built in 3D and drawn as pixel art with the rest of the town (walk/World.ts
// renders everything at a low resolution with outlines). Because it's a real body with joints, it can do what the
// week has in it, from any side: walk and run, get into bed and pull the covers up, sleep, sit up when the alarm goes,
// study, pin a note on a board, sit back with crossed legs, picnic, sip coffee, take a letter from a mailbox, wave.
// Every pose is a few joint angles, blended; everything moves slowly and smoothly (30 Oct: "some of the
// actions/camera movements/reactions are super unnatural"), and every movement means something: no arms thrown up
// at a click (30 Oct: "that's a bad reaction because it doesn't mean anything").

import * as THREE from "three"

export type Action = "stand" | "wave" | "wake" | "sleep" | "study" | "read" | "tv" | "laptop" | "picnic" | "coffee" | "counter" | "boxes" | "mail" | "calendar" | "point" | "present" | "think" | GuideAction

/** What the guide does showing you round Friday (Guide.ts; 30 Oct: "be creative, have the guide do unique actions"):
 * moving a block in both hands, a stopwatch, hands on the head, a magnifying glass, a look at the watch, writing on a
 * notepad, a book, an idea, a yawn and a sandwich, a wrench, and a dance for the weekend. */
export type GuideAction = "drag" | "timer" | "worry" | "search" | "watch" | "write" | "book" | "eureka" | "yawn" | "fix" | "dance"

/** What's in hand for each: a block of the calendar, a stopwatch, a magnifying glass, a notepad and pencil, a book, a
 * wrench (and after the yawn, a sandwich). */
const PROPS: Partial<Record<Action, string[]>> = { drag: ["block"], timer: ["stopwatch"], search: ["magnifier"], watch: ["wristwatch"], write: ["notepad", "pencil"], book: ["book"], fix: ["wrench"] }

/** Where each of the guide's things sits: by which hand (or between both), how far from it and turned how, in the
 * frame they face (x their left, y up, z toward you), so it shows in front of the hand from any pose. */
const HELD: Record<string, { hand: 0 | 1 | "both"; at: [number, number, number]; turn: [number, number, number] }> = {
  block: { hand: "both", at: [0, 0.02, 0.06], turn: [0, 0, 0] },
  stopwatch: { hand: 1, at: [0, 0.07, 0.05], turn: [0, 0, 0] },
  magnifier: { hand: 1, at: [0, 0.13, 0.03], turn: [0, 0, 0] },
  pencil: { hand: 1, at: [0, 0.03, 0.05], turn: [0.3, 0, 0.7] },
  wrench: { hand: 1, at: [0, 0.08, 0.05], turn: [0, 0, 0.5] },
  notepad: { hand: 0, at: [-0.02, 0.03, 0.05], turn: [-1.0, 0, 0] },
  wristwatch: { hand: 0, at: [0, 0.07, 0.04], turn: [0, 0, 0] },
  sandwich: { hand: 1, at: [0, 0.04, 0.07], turn: [0.3, 0, 0] }, // after the yawn
  book: { hand: "both", at: [0, 0.03, 0.05], turn: [-0.9, 0, 0] },
}
const GUIDE_SIZE = 1.6 // drawn bigger than life, so they read at the guide's few pixels

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
  elbowIn: [number, number] // the forearm bent in across the body (left arm negative, right positive)
  legX: [number, number]
  legZ: [number, number]
  knee: [number, number]
  eyes: number // 1 open, 0 shut
}

const HIPS = 0.74

function stand(): Pose {
  return { lift: HIPS, body: 0, lean: 0, twist: 0, headX: 0, headY: 0, headZ: 0, armX: [0.05, 0.05], armZ: [0.1, -0.1], elbow: [-0.15, -0.15], elbowIn: [0, 0], legX: [0, 0], legZ: [0.02, -0.02], knee: [0, 0], eyes: 1 }
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
    elbowIn: two(a.elbowIn, b.elbowIn),
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
 * height above the floor. Nothing raises the arms. */
export const BED = {
  stand,
  /** Standing by the bed, bending to take the covers' edge and throw them back. */
  reach(): Pose {
    const p = stand()
    p.lean = 0.5
    p.headX = 0.3
    p.armX = [-0.55, -0.85]
    p.armZ = [0.12, -0.08]
    p.elbow = [-0.35, -0.3]
    p.knee = [0.18, 0.18]
    p.legX = [-0.12, -0.12]
    p.lift = HIPS - 0.04
    return p
  },
  /** Sitting on its edge, feet on the floor, hands on the mattress either side. */
  edge(top: number): Pose {
    const p = sitting(top)
    p.armX = [0.22, 0.22]
    p.armZ = [0.32, -0.32]
    p.elbow = [-0.08, -0.08]
    return p
  },
  /** On its edge with the legs raised straight out, leaning back on the hands, ready to swing them up. */
  lift(top: number): Pose {
    const p = BED.edge(top)
    p.legX = [-1.62, -1.62]
    p.knee = [0.2, 0.2]
    p.lean = -0.28
    p.armX = [0.5, 0.5]
    p.armZ = [0.28, -0.28]
    p.headX = 0.12
    return p
  },
  /** Sitting up in it, legs out along it, hands in the lap. */
  up(top: number): Pose {
    const p = sitting(top)
    p.legX = [-1.56, -1.56]
    p.knee = [0.04, 0.04]
    p.legZ = [0.05, -0.05]
    p.armX = [-0.38, -0.38]
    p.armZ = [0.12, -0.12]
    p.elbow = [-0.7, -0.7]
    return p
  },
  /** Lying on the back, head on the pillow, hands on the stomach. */
  lie(top: number): Pose {
    const p = stand()
    p.body = -Math.PI / 2
    p.lift = top + 0.1
    p.legX = [0, 0]
    p.legZ = [0.04, -0.04]
    p.knee = [0.05, 0.05]
    // hands resting on the stomach, under the covers
    p.armX = [-0.22, -0.22]
    p.armZ = [0.16, -0.16]
    p.elbow = [-0.55, -0.55]
    p.elbowIn = [-0.9, 0.9]
    p.headX = 0.28
    return p
  },
  /** Lying, the forearms folded in across the chest, holding the covers' edge under the chin. */
  tuck(top: number): Pose {
    const p = BED.lie(top)
    p.armX = [-0.15, -0.15]
    p.armZ = [0.22, -0.22]
    p.elbow = [-0.45, -0.45]
    p.elbowIn = [-1.75, 1.75]
    return p
  },
  /** Lying, the hands down by the hips, taking the covers' edge. */
  take(top: number): Pose {
    const p = BED.lie(top)
    p.armX = [-0.05, -0.05]
    p.armZ = [0.28, -0.28]
    p.elbow = [-0.35, -0.35]
    return p
  },
}

/** A pose as a row of numbers, and back: for scenes that move through poses as a smooth curve. */
export function poseNumbers(p: Pose): number[] {
  return [p.lift, p.body, p.lean, p.twist, p.headX, p.headY, p.headZ, ...p.armX, ...p.armZ, ...p.elbow, ...p.elbowIn, ...p.legX, ...p.legZ, ...p.knee, p.eyes]
}
export function poseFrom(n: number[]): Pose {
  return { lift: n[0], body: n[1], lean: n[2], twist: n[3], headX: n[4], headY: n[5], headZ: n[6], armX: [n[7], n[8]], armZ: [n[9], n[10]], elbow: [n[11], n[12]], elbowIn: [n[13], n[14]], legX: [n[15], n[16]], legZ: [n[17], n[18]], knee: [n[19], n[20]], eyes: Math.max(0, Math.min(1, n[21])) }
}

/** How your answers have them feeling, so the same action looks different. */
export interface Mood {
  energy?: number // getting up: 0 dragging themselves up, 1 bright-eyed
  happy?: number // how much of the time is theirs
  paper?: boolean // the brief on paper, or the phone instead
  lid?: number // the laptop's lid on the sofa: 0 shut (the evening's yours), 1 open (it's work)
  restless?: number // a late night: turning over in their sleep
  aim?: number // pointing (showing you round Friday): which way, facing you, from straight down; toward their left +
  talk?: number // saying something: the head moving with it
  crouch?: number // a hop (showing you round): bent for it and landing from it, 0 to 1
  cheer?: number // both arms up in the air, 0 to 1
  shades?: boolean // sunglasses on: it's the weekend
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
      // sitting up in bed, hands in the lap. Up early: slumped, eyes half shut, the head nodding forward and lifting;
      // up late: upright, eyes open, looking round the room.
      Object.assign(p, BED.up(seat ?? 0.56))
      const energy = mood.energy ?? 0.6
      const nod = (1 - energy) * span(cycle(t, 7), 1.5, 5.5, 1.6)
      p.lean = 0.06 + (1 - energy) * 0.18 + breath * 0.02
      p.headX = 0.05 + (1 - energy) * 0.18 + nod * 0.22
      p.headY = energy * Math.sin(t * 0.45) * 0.45
      p.eyes = 1 - (1 - energy) * 0.6 - nod * 0.3
      break
    }
    case "sleep": {
      Object.assign(p, BED.lie(seat ?? 0.56))
      p.eyes = 0
      p.lean = breath * 0.03 // a slow breath
      p.headY = 0.25 + Math.sin(t * 0.13) * 0.08
      // a late night: now and then turning onto the side and back, slowly
      const roll = (mood.restless ?? 0) * span(cycle(t, 11), 3, 8.5, 1.6)
      p.twist = roll * 0.45
      p.headY += roll * 0.45
      p.legX = [-roll * 0.3, -roll * 0.15]
      p.knee = [0.05 + roll * 0.45, 0.05 + roll * 0.3]
      break
    }
    case "study": {
      // typing, unhurried, and every so often sitting back to think, chin on a hand
      const c = cycle(t, 10)
      const think = span(c, 6.6, 9.4, 0.7)
      // forearms on the table, hands on its top (not in it)
      p.armX = [-0.78 + think * 0.2, -0.78 - think * 0.75]
      p.armZ = [-0.12, 0.12 + think * 0.05]
      p.elbow = [-1.2 + Math.sin(t * 9) * 0.02 * (1 - think) - think * 0.3, -1.2 + Math.sin(t * 9 + 1.8) * 0.02 * (1 - think) - think * 1.0]
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
      // back in the sofa, the laptop on the lap, ankles crossed, both hands resting on it (30 Oct: "his hands
      // should be on the laptop... right now his hands are just suspended"): on its keys while it's open, on its
      // shut lid when the evening's all theirs (a quarter inch higher, a little nearer); now and then a laugh,
      // in the head and shoulders only, so the hands stay put. The angles put the hands on it (worked out against
      // this body, the laptop where update() sets it)
      p.lean = -0.3
      p.legX = [-1.48, -1.48]
      p.legZ = [-0.07, 0.07]
      p.knee = [1.15, 1.15]
      const lid = Math.max(0, Math.min(1, mood.lid ?? 1))
      const scroll = lid * span(cycle(t, 7), 2, 4.5, 0.4) * Math.sin(t * 5) * 0.03 // a finger on the trackpad
      p.armX = [-0.22 - lid * 0.06, -0.22 - lid * 0.06]
      p.armZ = [0.04, -0.04]
      p.elbow = [-0.78 + lid * 0.24, -0.78 + lid * 0.24 + scroll]
      p.elbowIn = [-0.7 - lid * 0.06, 0.7 + lid * 0.06]
      const laugh = span(cycle(t, 9), 5.5, 7.0, 0.5)
      p.lean -= laugh * 0.03
      p.headX = -0.04 - laugh * 0.2
      p.headY = 0.05 + Math.sin(t * 0.3) * 0.06
      p.eyes = laugh > 0.6 ? 0.3 : 1
      break
    }
    case "laptop": {
      // the laptop on the lap: hands on its keys, elbows at the sides and the forearms in to them, the head down at
      // its screen, now and then lifting it to read (the shoulders stay, so the hands stay on the keys)
      const c = cycle(t, 8)
      const read = span(c, 5, 7.4, 0.6)
      p.lean = -0.05
      p.headX = 0.45 - read * 0.2
      p.legX = [-1.48, -1.48]
      p.knee = [1.3, 1.3]
      p.legZ = [0.04, -0.04]
      p.armX = [-0.1, -0.1]
      p.armZ = [0.04, -0.04]
      p.elbow = [-1.15 + Math.sin(t * 9) * 0.03 * (1 - read), -1.15 + Math.sin(t * 9 + 1.8) * 0.03 * (1 - read)]
      p.elbowIn = [-0.74, 0.74]
      break
    }
    case "picnic": {
      const happy = mood.happy ?? 0.5
      if (happy > 0.75) {
        // all day theirs: leaning back on their hands, legs out, face to the sun
        p.legX = [-1.5, -1.46]
        p.knee = [0.12, 0.32]
        p.legZ = [0.08, -0.03]
        p.lean = -0.45
        p.armX = [0.22, 0.22]
        p.armZ = [0.22, -0.22]
        p.elbow = [-0.04, -0.04]
        p.headX = -0.3 + Math.sin(t * 0.4) * 0.04
        p.eyes = span(cycle(t, 8), 2, 5.5, 0.6) > 0.5 ? 0.15 : 1
        break
      }
      // sitting on the blanket with the knees up, forearms on them, now and then a bite, looking about
      p.legX = [-2.1, -2.1]
      p.legZ = [0.14, -0.14]
      p.knee = [2.12, 2.12]
      const bite = span(cycle(t, 6), 0.8, 2.4, 0.5)
      p.lean = 0.12
      p.armX = [-0.95, -0.95 - bite * 0.55]
      p.armZ = [0.12, -0.12]
      p.elbow = [-0.55, -0.55 - bite * 1.15]
      p.headX = 0.05 - bite * 0.08
      p.headY = Math.sin(t * 0.4) * 0.35 * (1 - bite)
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
      // hands resting on the counter's edge
      const talk = Math.sin(t * 0.8)
      p.armX = [-1.55, -1.55]
      p.armZ = [-0.08, 0.08]
      p.elbow = [-0.15, -0.15]
      p.headX = 0.05 + talk * 0.06
      p.headY = Math.sin(t * 0.35) * 0.12
      p.lean = 0.05
      break
    }
    case "boxes": {
      // in front of the wall of boxes, looking along them for theirs
      p.headX = -0.15
      p.headY = Math.sin(t * 0.35) * 0.35
      p.legZ = [0.02 + Math.sin(t * 0.6) * 0.03, -0.02 + Math.sin(t * 0.6) * 0.03]
      break
    }
    case "mail": {
      // reading what came, the letter in both hands
      p.armX = [-0.85, -0.85]
      p.armZ = [0.05, -0.05]
      p.elbow = [-1.05, -1.05]
      p.elbowIn = [-0.5, 0.5]
      p.headX = 0.38 + Math.sin(t * 0.7) * 0.03
      p.headY = Math.sin(t * 0.9) * 0.1
      break
    }
    case "point": {
      // showing you something on the screen: the arm on its side straight out toward it, the head turned to it, a
      // small beat of the hand now and then
      const aim = Math.max(-2.95, Math.min(2.95, mood.aim ?? 2.4))
      const i = aim >= 0 ? 0 : 1
      const beat = span(cycle(t, 4), 0.4, 1.1, 0.3) * 0.08
      p.armX[i] = -0.22 - beat
      p.armZ[i] = aim
      p.elbow[i] = -0.06 - beat
      p.armX[1 - i] = -0.1
      p.armZ[1 - i] = i === 0 ? -0.12 : 0.12
      p.elbow[1 - i] = -0.35
      p.headY = Math.sin(aim) * 0.5
      p.headX = -0.32 * Math.max(0, -Math.cos(aim)) + 0.1 * Math.max(0, Math.cos(aim))
      p.lean = 0.02
      break
    }
    case "present": {
      // here it all is: both arms opened out toward it, a little lift
      const lift = Math.sin(t * 1.2) * 0.04
      p.armX = [-0.42 - lift, -0.42 - lift]
      p.armZ = [0.72, -0.72]
      p.elbow = [-0.32, -0.32]
      p.lean = -0.04
      p.headX = -0.06
      p.headY = Math.sin(t * 0.4) * 0.12
      break
    }
    case "think": {
      // a hand at the chin, the other arm across, looking up and off a little
      p.armX = [-0.5, -0.95]
      p.armZ = [-0.3, -0.05]
      p.elbow = [-1.7, -2.25]
      p.headX = -0.14
      p.headY = 0.2 + Math.sin(t * 0.5) * 0.06
      p.headZ = 0.08
      break
    }
    case "drag": {
      // a block of the calendar held in both hands, moved along a day and back (the angles put the hands together in
      // front, worked out against this body, as the others below)
      const along = Math.sin(t * 1.1)
      p.armX = [-0.62, -0.62]
      p.armZ = [0.045, -0.045]
      p.elbow = [-0.9, -0.9]
      p.elbowIn = [-0.59, 0.59]
      p.twist = along * 0.3
      p.headY = along * 0.25
      p.headX = 0.15
      p.legZ = [0.04 + along * 0.03, -0.04 + along * 0.03]
      break
    }
    case "timer": {
      // a stopwatch held up in front and looked at, clicked now and then
      const click = span(cycle(t, 2.4), 1.6, 1.9, 0.08)
      p.armX = [0.05, -0.61]
      p.armZ = [0.1, -0.04]
      p.elbow = [-0.15, -1.49 - click * 0.15]
      p.elbowIn = [0, 0.61]
      p.headY = -0.15
      p.headX = 0.25
      break
    }
    case "worry": {
      // hands on the sides of the head, a shake of it: that's late
      const shake = span(cycle(t, 3), 0.3, 1.5, 0.2) * Math.sin(t * 9)
      p.armX = [-2.2, -2.2]
      p.armZ = [0.34, -0.34]
      p.elbow = [-1.94, -1.94]
      p.elbowIn = [-0.35, 0.35]
      p.twist = shake * 0.08
      p.headX = 0.05
      p.lean = 0.04
      break
    }
    case "search": {
      // a magnifying glass to the right eye, turning from the waist to look along, so it stays at the eye
      const look = Math.sin(t * 0.9)
      p.armX = [0.05, -1.69]
      p.armZ = [0.1, -0.25]
      p.elbow = [-0.15, -1.6]
      p.elbowIn = [0, 1.03]
      p.twist = look * 0.28
      p.lean = 0.08
      break
    }
    case "watch": {
      // the left wrist across in front and looked at, the right hand tapping it
      const tap = span(cycle(t, 3.2), 1.8, 2.6, 0.2) * Math.abs(Math.sin(t * 6))
      p.armX = [-1.04, -0.75]
      p.armZ = [0.04, -0.04]
      p.elbow = [-0.07, -1.08 - tap * 0.15]
      p.elbowIn = [-1.14, 0.62]
      p.headX = 0.4
      p.headY = 0.08
      break
    }
    case "write": {
      // a notepad in the left hand, the pencil going in the right, the head down at it
      const scribble = Math.sin(t * 11) * 0.04 + Math.sin(t * 2.3) * 0.06
      p.armX = [-0.73, -1.11]
      p.armZ = [0.04, -0.04]
      p.elbow = [-0.7, -0.06 - Math.abs(scribble)]
      p.elbowIn = [-0.62, 0.87 + scribble]
      p.headX = 0.45
      p.headY = 0.1
      p.lean = 0.06
      break
    }
    case "book": {
      // an open book in both hands, a page turned now and then
      const turn = span(cycle(t, 4.5), 3.2, 3.9, 0.25)
      p.armX = [-0.67, -0.67 - turn * 0.2]
      p.armZ = [0.04, -0.04 + turn * 0.3]
      p.elbow = [-0.68, -0.68 - turn * 0.3]
      p.elbowIn = [-0.53, 0.53]
      p.headX = 0.38
      p.headY = Math.sin(t * 0.8) * 0.1
      break
    }
    case "eureka": {
      // got it: a finger up high, the other hand on the hip, chin up
      const beat = span(cycle(t, 3), 0.2, 0.7, 0.15)
      p.armX = [0.55, -0.35 - beat * 0.2]
      p.armZ = [0.1, -2.75]
      p.elbow = [-1.08, -0.1]
      p.elbowIn = [-0.05, 0]
      p.headX = -0.22
      p.headY = -0.15
      p.lean = -0.04
      break
    }
    case "yawn": {
      // a big stretch and a yawn, eyes shut; then a sandwich
      const c = cycle(t, 7)
      const stretch = span(c, 0.2, 2.6, 0.6)
      const bite = span(c, 3.4, 4.4, 0.3) + span(c, 5.2, 6.2, 0.3)
      p.armX = [-0.4 * stretch, -0.4 * stretch - (1 - stretch) * (0.75 + bite * 0.55)]
      p.armZ = [0.1 + stretch * 2.55, -0.1 - stretch * 2.55]
      p.elbow = [-0.15 - stretch * 0.25, -0.15 - stretch * 0.25 - (1 - stretch) * (0.95 + bite * 1.15)]
      p.lean = -0.18 * stretch
      p.headX = -0.35 * stretch + 0.05 * (1 - stretch) - bite * 0.08
      p.eyes = stretch > 0.5 ? 0 : 1
      break
    }
    case "fix": {
      // a wrench at a bolt in front, turned a quarter and back, the other hand on the knee, leaning to it
      const turn = Math.sin(t * 2.6)
      p.armX = [-0.32, -0.9]
      p.armZ = [0.1, -0.1 + turn * 0.15]
      p.elbow = [-1.06, -0.95 + turn * 0.12]
      p.elbowIn = [-0.18, 0.45]
      p.lean = 0.18
      p.headX = 0.35
      p.twist = turn * 0.06
      break
    }
    case "dance": {
      // the weekend: arms up in turn, a bounce in the knees, a sway
      const beat = t * 4.2
      const up = Math.sin(beat / 2)
      const bounce = Math.abs(Math.sin(beat))
      p.armX = [-0.3, -0.3]
      p.armZ = [0.4 + Math.max(0, up) * 2.2, -0.4 - Math.max(0, -up) * 2.2]
      p.elbow = [-0.6 - Math.max(0, -up) * 0.6, -0.6 - Math.max(0, up) * 0.6]
      p.knee = [0.25 * bounce, 0.25 * bounce]
      p.legX = [-0.12 * bounce, -0.12 * bounce]
      p.lift -= 0.015 * bounce
      p.twist = Math.sin(beat / 2) * 0.18
      p.headZ = Math.sin(beat / 2) * 0.12
      p.headY = Math.sin(beat / 4) * 0.2
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
  // talking: the head moving a little with the words
  const talk = mood.talk ?? 0
  if (talk > 0) {
    p.headX += talk * (Math.sin(t * 7.3) * 0.035 + Math.sin(t * 3.1) * 0.025)
    p.headZ += talk * Math.sin(t * 2.3) * 0.03
  }
  // a hop (30 Oct: "have the sprite do more (like jump and point to something)"): thighs forward and knees bent,
  // the hips lowered by just what keeps the feet on the floor (thigh 0.36, shin and shoe 0.38), leaning into it
  const crouch = mood.crouch ?? 0
  if (crouch > 0) {
    const thigh = 0.55 * crouch
    const bend = 1.1 * crouch
    p.legX = [p.legX[0] - thigh, p.legX[1] - thigh]
    p.knee = [p.knee[0] + bend, p.knee[1] + bend]
    p.lift -= HIPS - (0.36 * Math.cos(thigh) + 0.38 * Math.cos(bend - thigh))
    p.lean += 0.3 * crouch
  }
  const cheer = mood.cheer ?? 0
  if (cheer > 0) {
    p.armZ = [p.armZ[0] + (2.5 - p.armZ[0]) * cheer, p.armZ[1] + (-2.5 - p.armZ[1]) * cheer]
    p.armX = [p.armX[0] + (-0.25 - p.armX[0]) * cheer, p.armX[1] + (-0.25 - p.armX[1]) * cheer]
    p.elbow = [p.elbow[0] + (-0.3 - p.elbow[0]) * cheer, p.elbow[1] + (-0.3 - p.elbow[1]) * cheer]
    p.headX -= 0.15 * cheer
  }
  return p
}

/** Walking and running: stride, knees lifting on the swing, arms against the legs, a bob twice a stride, a sway, and
 * leaning into it as it quickens. `phase` follows the ground covered, so feet don't slide. */
function moving(phase: number, speed: number): Pose {
  const p = stand()
  const run = clamp01((speed - 2.6) / 2.4)
  const step = clamp01(speed / 1.4) // short steps getting going and stopping
  const swing = (0.48 + run * 0.42) * step
  const s = Math.sin(phase)
  const c = Math.cos(phase)
  p.legX = [s * swing, -s * swing]
  p.knee = [(Math.max(0, c) * (0.5 + run * 0.75) + 0.1) * step, (Math.max(0, -c) * (0.5 + run * 0.75) + 0.1) * step]
  p.armX = [-s * (0.4 + run * 0.3) * step, s * (0.4 + run * 0.3) * step]
  p.armZ = [0.1 + run * 0.06, -0.1 - run * 0.06]
  p.elbow = [-0.3 - run * 1.1, -0.3 - run * 1.1]
  p.lift = HIPS - 0.015 - run * 0.05 + Math.abs(c) * (0.025 + run * 0.05)
  p.lean = 0.05 + run * 0.18
  p.twist = s * (0.08 + run * 0.05)
  p.headX = -0.03 - run * 0.06
  p.headY = -s * 0.03
  return p
}

/** Something done in a moment, over whatever they're doing, because of an answer you just gave: a book onto the pile,
 * the timer set, the note moved, a look at the alarm clock, a letter taken out of a box; or, while you decide, a
 * glance at you. Nothing for no reason. */
export type Reaction = "glance" | "nod" | "clock" | "stackRight" | "stackLeft" | "timer" | "restBack" | "pin" | "fetch" | "typing"

export const REACT_FOR: Record<Reaction, number> = { glance: 2.6, nod: 1.2, clock: 2.2, stackRight: 1.3, stackLeft: 1.3, timer: 1.5, restBack: 2.6, pin: 1.6, fetch: 2.0, typing: 1.6 }

/** The upper body during a reaction `t` seconds in (the legs stay as they are). `look` turns the head toward you;
 * `aim` is which way: where along a board the hand goes, or where the clock is (-1 to 1). */
function reacting(kind: Reaction, t: number, base: Pose, look: number, aim: number): Pose {
  const p: Pose = { ...base, armX: [...base.armX], armZ: [...base.armZ], elbow: [...base.elbow], elbowIn: [...base.elbowIn] }
  const swing = (period: number) => Math.sin((t / period) * Math.PI * 2)
  switch (kind) {
    case "glance":
      p.headY = look
      p.headX = -0.05
      p.eyes = 1
      break
    case "nod":
      p.headX = base.headX + Math.max(0, swing(0.6)) * 0.22
      break
    case "clock":
      // turning to look at the alarm clock: what time is it?
      p.headY = aim * 1.0
      p.headX = base.headX + 0.15
      p.eyes = 1
      break
    case "stackRight":
    case "stackLeft": {
      // a reach to the pile beside them on the desk, and back: a book on, or one off
      const i = kind === "stackRight" ? 1 : 0
      const out = kind === "stackRight" ? -1 : 1
      // seated, only the arm and the head go: the hips stay square on the chair
      p.armX[i] = -1.42 // to the top of the pile, over the table
      p.armZ[i] = out * 0.6
      p.elbow[i] = -0.25
      p.lean = base.lean + 0.15
      p.headY = out * 0.5
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
    case "restBack":
      // the timer's gone: a sitting done, so a breather, sitting back, shoulders down, eyes shut a moment
      p.lean = base.lean - 0.32
      p.armX = [0.05, 0.05]
      p.armZ = [0.25, -0.25]
      p.elbow = [-0.2, -0.2]
      p.headX = -0.25
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
      break
    }
    case "fetch": {
      // the box's door opened, the hand to its opening (angled in, to the box in front of them, not into the wall
      // beside it), the letter taken, and the hand back down with it
      const reach = span(t, 0.15, 1.35, 0.45)
      p.armX = [base.armX[0], base.armX[1] + (-1.48 - base.armX[1]) * reach]
      p.armZ = [base.armZ[0], base.armZ[1] + (0.32 - base.armZ[1]) * reach]
      p.elbow = [base.elbow[0], base.elbow[1] + (-0.55 - base.elbow[1]) * reach]
      p.headX = -0.15 * reach
      break
    }
    case "typing":
      // a few keys at the counter: the screen changes
      p.armX = [-1.55, -1.55]
      p.armZ = [-0.1, 0.1]
      p.elbow = [-0.2 + swing(0.5) * 0.04, -0.2 - swing(0.5) * 0.04]
      p.headX = 0.25
      p.lean = base.lean + 0.1
      break
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
  private pack = new THREE.Group()
  private lap = new THREE.Group() // a laptop on the lap, on the sofa
  private lid = new THREE.Group() // its lid, on its hinge at the far edge
  private screenGlow: THREE.MeshBasicMaterial
  private shades = new THREE.Group() // sunglasses, for the weekend
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
    this.pack.add(part(rounded(0.32, 0.36, 0.14, 0.05), PACK, 0, 0.24, -0.19))
    this.pack.add(part(rounded(0.22, 0.12, 0.05, 0.02), 0x9a4426, 0, 0.14, -0.27))
    for (const x of [-0.11, 0.11]) this.pack.add(part(new THREE.BoxGeometry(0.045, 0.32, 0.03), 0x7a3a22, x, 0.3, 0.11))
    this.chest.add(this.pack)
    // the laptop on the lap (30 Oct: "the laptop on his lap on the couch is the wrong way around"): the keys toward
    // them, the hinge at the far edge toward the knees, the screen facing them
    const silver = toon(0xb9bcc2)
    this.lap.add(part(new THREE.BoxGeometry(0.34, 0.018, 0.24), silver, 0, 0, 0))
    this.lap.add(part(new THREE.BoxGeometry(0.3, 0.004, 0.12), 0x2c2e33, 0, 0.011, -0.02)) // the keys
    this.lid.position.set(0, 0.009, 0.12)
    this.lid.add(part(new THREE.BoxGeometry(0.34, 0.22, 0.012), silver, 0, 0.11, 0))
    this.screenGlow = new THREE.MeshBasicMaterial({ color: 0xdfe8f5 })
    const glow = new THREE.Mesh(new THREE.PlaneGeometry(0.3, 0.18), this.screenGlow)
    glow.position.set(0, 0.11, -0.0075)
    glow.rotation.y = Math.PI
    this.lid.add(glow)
    this.lap.add(this.lid)
    this.lap.visible = false
    this.hips.add(this.lap)
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
    // what the guide shows you round Friday with (Guide.ts): in the right hand a stopwatch, a magnifying glass, a
    // pencil or a wrench; in the left a notepad or a book; and sunglasses for the weekend
    const left = this.elbows[0]
    const stopwatch = new THREE.Group()
    const dial = part(new THREE.CylinderGeometry(0.055, 0.055, 0.024, 16), 0xc9ccd2)
    dial.rotation.x = Math.PI / 2
    stopwatch.add(dial)
    stopwatch.add(part(new THREE.BoxGeometry(0.075, 0.075, 0.004), 0xfdfaf2, 0, 0, 0.013)) // its face
    stopwatch.add(part(new THREE.BoxGeometry(0.004, 0.032, 0.004), 0x1e1a26, 0, 0.012, 0.016)) // a hand
    stopwatch.add(part(new THREE.BoxGeometry(0.022, 0.022, 0.018), 0xc9ccd2, 0, 0.066, 0)) // the button
    stopwatch.position.set(0, -0.3, 0.05)
    const magnifier = new THREE.Group()
    const ring = part(new THREE.TorusGeometry(0.06, 0.012, 6, 18), 0x3a2820)
    magnifier.add(ring)
    magnifier.add(part(new THREE.CircleGeometry(0.056, 18), toon(0xbfe3ff)))
    magnifier.add(part(new THREE.CylinderGeometry(0.012, 0.012, 0.11, 6), 0x7a4a2a, 0, -0.115, 0))
    magnifier.position.set(0, -0.2, 0.08)
    const pencil = part(new THREE.CylinderGeometry(0.008, 0.008, 0.13, 6), 0xf2a33a, 0, -0.28, 0.05)
    pencil.rotation.x = 1.2
    const wrench = new THREE.Group()
    wrench.add(part(new THREE.BoxGeometry(0.025, 0.2, 0.012), 0x8a8f99, 0, -0.06, 0))
    wrench.add(part(new THREE.TorusGeometry(0.03, 0.012, 6, 10, Math.PI * 1.4), 0x8a8f99, 0, 0.055, 0))
    wrench.position.set(0, -0.3, 0.05)
    wrench.rotation.x = 1.4
    const notepad = new THREE.Group()
    notepad.add(part(new THREE.BoxGeometry(0.13, 0.008, 0.17), 0xf6e27a))
    notepad.add(part(new THREE.BoxGeometry(0.13, 0.012, 0.02), 0xc0392b, 0, 0.002, -0.085)) // its binding
    notepad.position.set(0.02, -0.29, 0.07)
    const book = new THREE.Group()
    const page = (side: number) => {
      const half = new THREE.Group()
      half.add(part(new THREE.BoxGeometry(0.11, 0.012, 0.16), 0xb5532e, side * 0.055, 0, 0)) // the cover
      half.add(part(new THREE.BoxGeometry(0.1, 0.008, 0.15), 0xfdfaf2, side * 0.055, 0.009, 0)) // the pages
      half.rotation.z = side * -0.2
      return half
    }
    book.add(page(1), page(-1))
    const wristwatch = new THREE.Group() // on the left wrist, its face to you
    wristwatch.add(part(new THREE.BoxGeometry(0.06, 0.035, 0.02), 0x2b2f3a))
    wristwatch.add(part(new THREE.BoxGeometry(0.036, 0.036, 0.012), 0xf2c14e, 0, 0, 0.012))
    const block = new THREE.Group() // a planned block of the calendar, picked up
    block.add(part(rounded(0.2, 0.09, 0.035, 0.012), 0x7fca73))
    block.add(part(new THREE.BoxGeometry(0.012, 0.09, 0.037), 0x3f8a3a, -0.094, 0, 0))
    for (const [name, thing, at] of [["block", block, hand], ["stopwatch", stopwatch, hand], ["magnifier", magnifier, hand], ["pencil", pencil, hand], ["wrench", wrench, hand], ["notepad", notepad, left], ["book", book, left], ["wristwatch", wristwatch, left]] as const) {
      thing.visible = false
      thing.scale.setScalar(GUIDE_SIZE)
      at.add(thing)
      this.held.set(name, thing)
    }
    this.shades.add(part(new THREE.BoxGeometry(0.3, 0.018, 0.02), 0x15131c, 0, 0.21, 0.19)) // the bar
    for (const side of [1, -1]) this.shades.add(part(new THREE.BoxGeometry(0.12, 0.07, 0.02), 0x15131c, side * 0.075, 0.17, 0.2))
    this.shades.visible = false
    this.head.add(this.shades)
  }

  private reaction: { kind: Reaction; at: number; aim: number } | null = null
  private snapped = false
  private last: Pose = stand()

  /** A cut to a new shot: the next pose is taken at once, not eased into at a joint's pace. */
  cut(): void {
    this.snapped = true
  }

  /** Do something in a moment, over what they're doing (an answer just changed, or a fidget while you decide). */
  react(kind: Reaction, now: number, aim = 0): void {
    this.reaction = { kind, at: now, aim }
  }

  /** The pose they're in now: where a scene (getting out of bed) starts from. */
  posed(): Pose {
    return { ...this.last, armX: [...this.last.armX], armZ: [...this.last.armZ], elbow: [...this.last.elbow], elbowIn: [...this.last.elbowIn], legX: [...this.last.legX], legZ: [...this.last.legZ], knee: [...this.last.knee] }
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
    const stride = 1.15 + clamp01((speed - 1.5) / 4) * 1.75
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
        pose = mix(pose, reacting(r.kind, age, pose, look, r.aim), into)
      }
    }
    if (!this.snapped) pose = this.limited(pose, dt, speed > 0.1 ? 30 : 9)
    this.snapped = false
    this.last = pose
    this.apply(pose, t, dt)
    // the laptop on the lap on the sofa, whatever they're doing there; its lid as open as the evening is work
    this.lap.visible = !s.pose && (action === "laptop" || action === "tv") && weight > 0.7
    if (this.lap.visible) {
      // on the thighs, along them: `along` the way they point, `up` off their top
      const thigh = (pose.legX[0] + pose.legX[1]) / 2
      const along = new THREE.Vector3(0, -Math.cos(thigh), -Math.sin(thigh)).multiplyScalar(0.25)
      const up = new THREE.Vector3(0, -Math.sin(thigh), Math.cos(thigh)).multiplyScalar(0.09)
      this.lap.position.copy(along).add(up)
      this.lap.rotation.set(thigh + Math.PI / 2, 0, 0)
      // the lid: shut (lying on the keys, toward them) to open past upright (110°)
      const open = Math.max(0, Math.min(1, mood.lid ?? 1))
      this.lid.rotation.x = open * ((110 * Math.PI) / 180) - Math.PI / 2
      this.screenGlow.color.setHex(open > 0.25 ? 0xdfe8f5 : 0x2c2e33)
    }
    const fetched = r?.kind === "fetch" && t - r.at > 1.0
    const holding = !s.pose && weight > 0.6 ? (fetched ? "letter" : ({ coffee: "cup", picnic: "sandwich", mail: "letter" } as Partial<Record<Action, string>>)[action]) : undefined
    // the guide's: what the action has in hand, the sandwich after the yawn
    const props = !s.pose && weight > 0.6 ? [...(PROPS[action] ?? []), ...(action === "yawn" && cycle(t, 7) > 3 ? ["sandwich"] : [])] : []
    for (const [name, thing] of this.held) thing.visible = (name === holding || props.includes(name)) && !(action === "picnic" && (mood.happy ?? 0) > 0.75)
    this.shades.visible = !!mood.shades
    if (props.length) this.placeHeld(props)
  }

  /** The guide's things, in front of the hand holding them (HELD), wherever the arm is. */
  private placeHeld(names: string[]): void {
    this.root.updateMatrixWorld(true)
    const facing = this.root.getWorldQuaternion(new THREE.Quaternion())
    const hands = [0, 1].map((i) => this.elbows[i].localToWorld(new THREE.Vector3(0, -0.24, 0)))
    for (const name of names) {
      const spot = HELD[name]
      const thing = this.held.get(name)
      if (!spot || !thing) continue
      const parent = thing.parent as THREE.Object3D
      const from = spot.hand === "both" ? hands[0].clone().lerp(hands[1], 0.5) : hands[spot.hand].clone()
      const where = from.add(new THREE.Vector3(...spot.at).applyQuaternion(facing))
      thing.position.copy(parent.worldToLocal(where))
      const turn = facing.clone().multiply(new THREE.Quaternion().setFromEuler(new THREE.Euler(...spot.turn)))
      thing.quaternion.copy(parent.getWorldQuaternion(new THREE.Quaternion()).invert().multiply(turn))
    }
  }

  /** The backpack on (walking about) or off (in bed, or sitting back in a seat). */
  wearPack(on: boolean): void {
    this.pack.visible = on
  }

  /** Where the body is, as round lumps (a point and a radius, in the world): what the covers lie over. The head
   * stays out. */
  samples(): { p: THREE.Vector3; r: number; torso?: boolean; arm?: boolean }[] {
    const at = (o: THREE.Object3D, x: number, y: number, z: number, r: number) => ({ p: o.localToWorld(new THREE.Vector3(x, y, z)), r })
    this.root.updateMatrixWorld(true)
    const out: { p: THREE.Vector3; r: number; torso?: boolean; arm?: boolean }[] = [at(this.hips, 0, 0, 0, 0.12)]
    // the chest is as wide as the shoulders: lumps across it, not only down the middle
    for (const x of [-0.13, 0, 0.13]) for (const y of [0.1, 0.28]) out.push({ ...at(this.chest, x, y, 0, x ? 0.1 : 0.12), torso: true })
    out.push({ ...at(this.chest, 0, 0.43, 0.02, 0.1), torso: true }) // the hood and its strings, at the collar
    for (const x of [-0.1, 0.1]) out.push(at(this.hips, x, 0, 0, 0.1))
    for (let i = 0; i < 2; i++) {
      out.push(at(this.legs[i], 0, -0.12, 0, 0.08), at(this.legs[i], 0, -0.26, 0, 0.075), at(this.knees[i], 0, 0, 0, 0.07))
      out.push(at(this.knees[i], 0, -0.16, 0, 0.065), at(this.knees[i], 0, -0.31, 0.05, 0.065), at(this.knees[i], 0, -0.33, 0.15, 0.05))
      for (const [o, y, r] of [[this.arms[i], -0.13, 0.065], [this.elbows[i], 0, 0.062], [this.elbows[i], -0.12, 0.062], [this.elbows[i], -0.24, 0.078]] as const) out.push({ ...at(o, 0, y, 0, r), arm: true })
    }
    return out
  }

  /** Each joint moved toward `pose` at most `fast` radians a second from where it was (the hips' height 2 m/s), so
   * a change of what they're doing never snaps. Blinks are as quick as they are. */
  private limited(pose: Pose, dt: number, fast: number): Pose {
    if (dt <= 0) return pose
    const from = poseNumbers(this.last)
    const to = poseNumbers(pose)
    const out = to.map((v, i) => {
      if (i === to.length - 1) return v
      const max = (i === 0 ? 2 : fast) * dt
      return from[i] + Math.max(-max, Math.min(max, v - from[i]))
    })
    return poseFrom(out)
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
      this.elbows[i].rotation.set(p.elbow[i], 0, p.elbowIn[i])
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
