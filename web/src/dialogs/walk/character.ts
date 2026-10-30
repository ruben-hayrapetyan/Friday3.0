// The one who walks you through your week (29 Oct, after the realistic street: "revert back to doing some pixel sprite
// thing but make it more engaging not just a sprite going from left to right - make the sprite a lot better"): a
// student in a hoodie with a backpack, built in 3D and drawn as pixel art with the rest of the town (walk/World.ts
// renders everything at a low resolution with outlines). Because it's a real body with joints, it can do what the
// week has in it, from any side: walk and run, sleep, sit up and stretch when the alarm goes, type, hold its head when
// the work piles up, watch TV, picnic, sip coffee, wave. Every pose is a few joint angles, blended.

import * as THREE from "three"

export type Action = "stand" | "wave" | "stretch" | "sleep" | "type" | "focus" | "stress" | "look" | "tv" | "laptop" | "picnic" | "coffee" | "counter" | "boxes" | "calendar"

/** How each action sits: on what (the seat's height above the floor), and what's in hand. */
export const SEATED: Partial<Record<Action, number>> = { type: 0.48, focus: 0.48, stress: 0.48, tv: 0.56, laptop: 0.56, coffee: 0.48, picnic: 0.06, stretch: 0.6, sleep: 0.6 }

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
interface Pose {
  lift: number // the hips' height above the feet's floor
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
  blanket: number // under the covers (0 none, 1 to the chest, 0.5 the legs)
}

const HIPS = 0.74

function stand(): Pose {
  return { lift: HIPS, body: 0, lean: 0, twist: 0, headX: 0, headY: 0, headZ: 0, armX: [0.05, 0.05], armZ: [0.1, -0.1], elbow: [-0.15, -0.15], legX: [0, 0], legZ: [0.02, -0.02], knee: [0, 0], eyes: 1, blanket: 0 }
}

function sitting(seat: number): Pose {
  const p = stand()
  p.lift = seat + 0.07
  p.legX = [-1.5, -1.5]
  p.knee = [1.45, 1.45]
  p.legZ = [0.08, -0.08]
  return p
}

function mix(a: Pose, b: Pose, t: number): Pose {
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
    blanket: t < 0.5 ? a.blanket : b.blanket,
  }
}

const cycle = (t: number, period: number) => ((t % period) + period) % period
const ease = (x: number) => x * x * (3 - 2 * x)
const window_ = (t: number, a: number, b: number, fade = 0.35) => Math.min(ease(Math.min(1, Math.max(0, (t - a) / fade))), ease(Math.min(1, Math.max(0, (b - t) / fade))))

/** What a body doing `action` looks like `t` seconds in. */
function acting(action: Action, t: number, on?: number): Pose {
  const seat = on ?? SEATED[action]
  const p = seat !== undefined ? sitting(seat) : stand()
  const breath = Math.sin(t * 1.7) * 0.02
  p.lean += breath
  switch (action) {
    case "wave": {
      p.armX[1] = -0.3
      p.armZ[1] = -2.55
      p.elbow[1] = -0.35 + Math.sin(t * 9) * 0.35
      p.headZ = Math.sin(t * 1.3) * 0.08
      p.headX = -0.08
      break
    }
    case "stretch": {
      // sitting up in bed: a big stretch and a yawn, then looking about
      p.legX = [-1.52, -1.52]
      p.knee = [0.05, 0.05]
      p.blanket = 0.5
      const c = cycle(t, 5)
      const up = window_(c, 0.2, 2.3, 0.5)
      p.armX = [-0.6 - up * 2.3, -0.6 - up * 2.3]
      p.armZ = [0.15 + up * 0.15, -0.15 - up * 0.15]
      p.elbow = [-0.7 + up * 0.55, -0.7 + up * 0.55]
      p.headX = -0.3 * up + Math.sin(t * 0.7) * 0.05
      p.headY = (1 - up) * Math.sin(t * 0.9) * 0.35
      p.lean = -0.08 * up
      p.eyes = up > 0.5 ? 0 : 1
      break
    }
    case "sleep": {
      p.body = -Math.PI / 2
      p.lift = (seat ?? 0.6) + 0.12
      p.legX = [0, 0]
      p.knee = [0.08, 0.08]
      p.armX = [0.1, 0.1]
      p.armZ = [0.18, -0.18]
      p.elbow = [-0.3, -0.3]
      p.headY = 0.35
      p.lean = Math.sin(t * 1.1) * 0.025
      p.eyes = 0
      p.blanket = 1
      break
    }
    case "type":
    case "focus":
    case "laptop": {
      const fast = action === "focus" ? 2 : 1
      p.armX = [-0.7, -0.7]
      p.armZ = [-0.12, 0.12]
      p.elbow = [-1.05 + Math.sin(t * 14 * fast) * 0.06, -1.05 + Math.sin(t * 14 * fast + 1.7) * 0.06]
      p.headX = 0.32 + Math.sin(t * 0.8) * 0.04
      p.lean = 0.12
      if (action === "laptop") {
        p.lean = 0.28
        p.headX = 0.4
      }
      if (action === "type" && cycle(t, 7) > 5.6) {
        // a pause to think, looking up
        p.armX = [-0.4, -1.6]
        p.elbow = [-0.9, -2.3]
        p.headX = -0.2
        p.headY = 0.25
      }
      break
    }
    case "stress": {
      p.armX = [-2.55, -2.55]
      p.armZ = [0.55, -0.55]
      p.elbow = [-1.95, -1.95]
      p.headX = 0.15
      p.headY = Math.sin(t * 5) * 0.18
      p.lean = 0.18
      p.eyes = cycle(t, 1.6) < 0.8 ? 0 : 1
      break
    }
    case "look": {
      p.headX = -0.12
      p.headZ = 0.1
      const pointing = window_(cycle(t, 5), 2.6, 4.4, 0.3)
      p.armX = [-1.55, 0.05 - pointing * 1.65]
      p.armZ = [-0.25, -0.08]
      p.elbow = [-2.35, -0.15 + pointing * 0.1]
      break
    }
    case "tv": {
      p.lean = -0.28
      p.armX = [-0.35, -0.5]
      p.armZ = [0.55, -0.12]
      p.elbow = [-0.6, -1.3]
      p.headX = -0.05
      p.headY = Math.sin(t * 0.4) * 0.05
      if (cycle(t, 6) > 4.8) p.lean = -0.28 + Math.abs(Math.sin(t * 16)) * 0.08 // a laugh
      break
    }
    case "picnic": {
      p.legX = [-1.25, -1.25]
      p.legZ = [0.95, -0.95]
      p.knee = [2.3, 2.3]
      const bite = window_(cycle(t, 4.5), 0.4, 1.6, 0.3)
      p.armX = [-0.55, -0.7 - bite * 0.75]
      p.elbow = [-0.6, -1.2 - bite * 1.1]
      p.armZ = [0.25, -0.1]
      p.headX = 0.12 - bite * 0.1
      p.headY = Math.sin(t * 0.5) * 0.3 * (1 - bite)
      break
    }
    case "coffee": {
      const sip = window_(cycle(t, 6), 0.5, 2.2, 0.4)
      p.armX = [-0.75, -0.75 - sip * 0.6]
      p.armZ = [-0.1, 0.05]
      p.elbow = [-0.9, -0.95 - sip * 1.35]
      p.headX = 0.35 - sip * 0.45
      p.lean = 0.08
      break
    }
    case "counter": {
      p.armX = [-1.05, -1.05]
      p.armZ = [-0.1, 0.1]
      p.elbow = [-0.55 + Math.sin(t * 11) * 0.05, -0.55 + Math.sin(t * 11 + 2) * 0.05]
      p.headX = 0.1
      p.lean = 0.12
      break
    }
    case "boxes": {
      const c = cycle(t, 5)
      const reach = window_(c, 0.3, 2.0, 0.4)
      const read = window_(c, 2.3, 4.6, 0.4)
      p.armX = [0.05 - read * 1.2, -0.1 - reach * 2.1 - read * 1.2]
      p.armZ = [0.1, -0.1]
      p.elbow = [-0.15 - read * 1.0, -0.2 + reach * 0.1 - read * 1.0]
      p.headX = -0.3 * reach + 0.25 * read
      break
    }
    case "calendar": {
      const tap = Math.max(0, Math.sin(t * 5)) * 0.08
      p.armX = [0.05, -1.75 + tap]
      p.armZ = [0.1, -0.05]
      p.elbow = [-0.15, -0.1]
      p.headX = -0.15 + Math.sin(t * 2.2) * 0.05
      p.headZ = 0.08
      break
    }
    default: {
      p.headY = Math.sin(t * 0.35) * 0.25
    }
  }
  return p
}

/** Walking and running: legs and arms swinging with the stride, the body bobbing and leaning into it. */
function moving(phase: number, speed: number): Pose {
  const p = stand()
  const run = Math.min(1, Math.max(0, (speed - 2.2) / 2.5))
  const swing = 0.55 + run * 0.35
  const s = Math.sin(phase)
  p.legX = [s * swing, -s * swing]
  p.knee = [Math.max(0, -Math.cos(phase)) * (0.5 + run * 0.9) + 0.1, Math.max(0, Math.cos(phase)) * (0.5 + run * 0.9) + 0.1]
  p.armX = [-s * (0.45 + run * 0.4), s * (0.45 + run * 0.4)]
  p.armZ = [0.12, -0.12]
  p.elbow = [-0.35 - run * 1.0, -0.35 - run * 1.0]
  p.lift = HIPS - 0.02 - run * 0.04 + Math.abs(Math.cos(phase)) * (0.035 + run * 0.05)
  p.lean = 0.06 + run * 0.22
  p.twist = s * 0.08
  p.headX = -0.04 - run * 0.1
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
  private covers: THREE.Mesh
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
    // the covers, when in bed
    this.covers = part(rounded(0.72, 0.2, 1.25, 0.08), 0x8a9ab0, 0, 0, 0)
    this.covers.visible = false
    this.root.add(this.covers)
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

  /** The covers' colour, to match the bed. */
  bedding(color: number): void {
    ;(this.covers.material as THREE.MeshToonMaterial).color.setHex(color)
  }

  /** Each frame: `speed` while moving (metres a second), else the action `weight` of the way in. */
  update(dt: number, t: number, speed: number, action: Action, weight: number, seat?: number, before?: Action, change = 1): void {
    const stride = speed > 3 ? 1.7 : 1.15
    this.phase += (speed * dt * Math.PI * 2) / stride
    const doing = before ? mix(acting(before, t, seat), acting(action, t, seat), ease(change)) : acting(action, t, seat)
    const pose = mix(speed > 0.05 ? moving(this.phase, speed) : stand(), doing, weight)
    if (speed <= 0.05 && weight < 1) pose.headY += Math.sin(t * 0.35) * 0.15 * (1 - weight)
    this.apply(pose, t, dt)
    const holding = weight > 0.6 ? ({ coffee: "cup", picnic: "sandwich", boxes: "letter" } as Partial<Record<Action, string>>)[action] : undefined
    for (const [name, thing] of this.held) thing.visible = name === holding
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
    this.covers.visible = p.blanket > 0
    if (p.blanket > 0) {
      // over the legs when sitting up; to the chest lying down
      const lying = p.blanket >= 1
      this.covers.scale.set(1, 1.35, lying ? 1.05 : 0.75)
      this.covers.position.set(0, p.lift + (lying ? 0.03 : 0.02), lying ? 0.45 : 0.42)
    }
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
    this.live.push({ sprite, born: now, life: kind === "!" ? 0.9 : 2.2, drift: new THREE.Vector3((Math.sin(now * 3.1) * 0.5 + 0.2) * 0.12, 0.32, 0) })
  }

  /** What's showing for an action now and then: z's in bed, sweat when it piles up, steam off the coffee. */
  every(action: Action, weight: number, head: THREE.Vector3, now: number): void {
    if (weight < 0.9) return
    const gap = { sleep: 1.1, stress: 1.4, coffee: 1.6, tv: 3.2, stretch: 5 }[action as string]
    if (!gap || now - this.last < gap) return
    this.last = now
    const kind = { sleep: "z", stress: "sweat", coffee: "steam", tv: "note", stretch: "!" }[action as string] as string
    const at = head.clone().add(new THREE.Vector3(0.18, kind === "steam" ? -0.4 : 0.05, 0))
    this.emit(kind, at, now, kind === "!" ? 0.4 : 0.3)
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
