// A check of the walk, for working on it (preview.html: `await walk.audit()`): plays every step, every way between
// two steps and each way an answer can be, as fast as it can and without drawing, and reports what looks wrong
// (30 Oct: "go through all of the animations for these kinds of things so i don't have to"): the body inside
// furniture, a wall or a tree; a joint snapping, shaking or turning too fast; a jump in place or heading; the camera
// inside something, cutting, or with the character hidden or off the picture. What it can't judge (whether a pose
// looks natural) is for looking at. Not part of the app.

import * as THREE from "three"
import type { Schemas } from "@/api/client"
import { poseNumbers } from "./character"

type Answers = Schemas["SetupInput"]
// biome-ignore lint: the walk's insides, for checking them
type Any = any

export interface Finding {
  where: string // "wake", "wake→work"
  what: string
  t: number // seconds in
  n?: number // how many frames it held for
}

const STEPS = ["hello", "wake", "work", "heavy", "focus", "deadline", "evening", "bed", "weekend", "brief", "ai", "bring", "calendars", "build", "reveal", "start"]
const FPS = 30
const DIRS = [new THREE.Vector3(0, 1, 0), new THREE.Vector3(1, 0, 0), new THREE.Vector3(0, 0, -1)]
const VARIANTS: [string, Partial<Answers>][] = [
  ["", {}],
  ["early", { wake: "06:15", bedtime: "22:30" }],
  ["late", { wake: "09:00", bedtime: "01:00" }],
  ["no evening, no weekend, no brief", { evening_free: 0, weekend_free: 0, brief: false }],
  ["all evening, all weekend", { evening_free: 5, weekend_free: 13 }],
]
export const PARTS = [...VARIANTS.map((_, i) => `hold:${i}`), ...STEPS.slice(1).map((_, i) => `between:${i}`), "answers"]

const JOINTS = ["lift", "body", "lean", "twist", "headX", "headY", "headZ", "armX0", "armX1", "armZ0", "armZ1", "elbow0", "elbow1", "in0", "in1", "legX0", "legX1", "legZ0", "legZ1", "knee0", "knee1", "eyes"]

export class Audit {
  private w: Any
  private findings: Finding[] = []
  private where = ""
  private t = 0
  private time = 0
  private solids = new Map<THREE.Object3D, THREE.Mesh[]>()
  private ray = new THREE.Raycaster()
  private history: number[][] = []
  private walked: boolean[] = [] // walking, in each frame of the history
  private shut = false // the iris was shut last frame
  private sides = new Map<THREE.Material, THREE.Side>()

  constructor(world: unknown) {
    this.w = world
  }

  /** Part of the check, so each part is quick: "hold:0" (every step held, with the first kind of answers; there
   * are five kinds), "between:3" (from the fourth step to the fifth and back), or "answers" (each answer changed). */
  run(answers: Answers, part: string): Finding[] {
    const w = this.w
    cancelAnimationFrame(w.raf)
    const raf = window.requestAnimationFrame
    window.requestAnimationFrame = (() => 0) as typeof window.requestAnimationFrame
    const render = w.composer.render
    w.composer.render = () => {}
    this.time = Math.max(performance.now(), w.last)
    w.last = this.time
    w.started = this.time
    this.doubleSided(true)
    this.findings = []
    // as setup shows it on a 1080 by 675 window: the picture beside the question's box on the right
    const shift = [...w.shift] as [number, number]
    const size = { ...w.size }
    w.resize(1080, 675)
    w.setShift(Math.min(0.24, 260 / 1080), 0)
    try {
      const [kind, arg] = part.split(":")
      if (kind === "hold") {
        const [name, change] = VARIANTS[Number(arg)]
        for (const step of STEPS) this.hold(step, { ...answers, ...change }, name)
      } else if (kind === "between") {
        const i = Number(arg)
        this.between(STEPS[i], STEPS[i + 1], answers)
        this.between(STEPS[i + 1], STEPS[i], answers)
      } else this.answering(answers)
    } finally {
      this.doubleSided(false)
      w.resize(size.w, size.h)
      w.setShift(...shift)
      w.composer.render = render
      window.requestAnimationFrame = raf
      w.last = performance.now()
      w.raf = requestAnimationFrame(w.loop)
    }
    return this.merged()
  }

  // ---- playing --------------------------------------------------------------------------------------------------------

  /** At a step, settled, for a while. */
  private hold(step: string, a: Answers, name: string): void {
    this.settle(step, a)
    this.where = `${step}${name ? ` (${name})` : ""}`
    this.history = []
    this.walked = []
    this.frames(10, 2)
  }

  /** Settled at `from`, then walked to `to`. */
  private between(from: string, to: string, a: Answers): void {
    this.settle(from, a)
    this.where = `${from}→${to}`
    this.history = []
    this.walked = []
    this.w.options.still = false
    this.w.go(to, a, STEPS.indexOf(to) < STEPS.indexOf(from))
    let n = 0
    while ((this.w.trip || this.w.script || (this.w.act && this.w.weight < 1)) && n < 30 * FPS) {
      this.frame(n % 2 === 0)
      n++
    }
    this.frames(2, 2)
  }

  /** Each answer changed where it's asked: what they do then. */
  private answering(a: Answers): void {
    const changes: [string, Partial<Answers>][] = [
      ["wake", { wake: "06:30" }],
      ["wake", { wake: "09:00" }],
      ["work", { normal_hours: 10 }],
      ["work", { normal_hours: 2 }],
      ["heavy", { most_hours: 14 }],
      ["focus", { focus_hours: 3 }],
      ["deadline", { finish_early_days: 0 }],
      ["deadline", { finish_early_days: 3 }],
      ["evening", { evening_free: 0 }],
      ["evening", { evening_free: 5 }],
      ["bed", { bedtime: "01:30" }],
      ["weekend", { weekend_free: 0 }],
      ["weekend", { weekend_free: 13 }],
      ["brief", { brief: false }],
    ]
    for (const [step, change] of changes) {
      this.settle(step, a)
      this.where = `${step}: ${JSON.stringify(change)}`
      this.history = []
    this.walked = []
      this.w.options.still = false
      this.w.update({ ...a, ...change })
      if (this.w.hero.reaction) this.w.hero.reaction.at = this.seconds()
      this.frames(6, 2)
    }
    const claude = { provider: "claude", name: "Claude", ready: true }
    const gpt = { provider: "openai", name: "GPT", ready: true }
    for (const [step, extra] of [["ai", { ai: gpt, reading: false }], ["bring", { ai: claude, reading: true }]] as const) {
      this.settle(step, a)
      this.w.setExtra({ ai: claude, reading: false })
      this.where = `${step}: ${JSON.stringify(extra)}`
      this.history = []
    this.walked = []
      this.w.setExtra(extra)
      if (this.w.hero.reaction) this.w.hero.reaction.at = this.seconds()
      this.frames(6, 2)
    }
    this.w.setExtra({ ai: null, reading: false })
  }

  /** Straight to a step, all moves done. */
  private settle(step: string, a: Answers): void {
    this.w.options.still = true
    this.w.go(step, a)
    for (let n = 0; n < 6 * FPS && (this.w.trip || this.w.script || (this.w.act && this.w.weight < 1)); n++) this.frame(false, true)
    this.w.options.still = false
    this.w.hero.reaction = null
    this.frames(0.5, 0, true)
  }

  private seconds(): number {
    return (this.time - this.w.started) / 1000
  }

  private frames(seconds: number, every: number, quiet = false): void {
    for (let n = 0; n < seconds * FPS; n++) this.frame(every > 0 && n % every === 0, quiet)
  }

  private frame(look: boolean, quiet = false): void {
    this.time += 1000 / FPS
    this.t += 1 / FPS
    this.w.loop(this.time)
    if (quiet) return
    this.motion()
    if (look) this.collisions()
  }

  // ---- checks -------------------------------------------------------------------------------------------------------

  private note(what: string): void {
    this.findings.push({ where: this.where, what, t: Math.round(this.t * 10) / 10 })
  }

  /** Snaps, shakes and jumps: joints faster than a person moves them, back and forth more often than a breath, the
   * body or the camera moving further in a frame than they can. */
  private motion(): void {
    const w = this.w
    const walking = !!w.trip?.path && w.speed > 0.1
    const row = [...poseNumbers(w.hero.posed()), w.pos.x, w.pos.z, w.yaw, w.cam.pos.x, w.cam.pos.y, w.cam.pos.z, w.cam.look.x, w.cam.look.y, w.cam.look.z]
    const last = this.history[this.history.length - 1]
    this.history.push(row)
    this.walked.push(walking || !!w.trip?.path)
    if (this.history.length > FPS) {
      this.history.shift()
      this.walked.shift()
    }
    if (!last) return
    // the wipe's shut (or just was): the cut to the next place, its pose and its spot, is what it's for
    const dark = w.iris < 0.05 || this.shut
    this.shut = w.iris < 0.05
    if (dark) return
    const nj = JOINTS.length
    for (let j = 0; j < nj; j++) {
      const speed = Math.abs(row[j] - last[j]) * FPS
      if (j === nj - 1) continue // blinks are quick
      const legs = j >= 15 && j <= 20
      const limit = j === 0 ? 3 : j === nj - 1 ? 20 : walking && (legs || j <= 12) ? 26 : 9
      if (speed > limit) this.note(`${JOINTS[j]} snaps (${speed.toFixed(1)}/s)`)
    }
    // back and forth: direction changes of a joint within the last second, ignoring tiny ones
    if (this.history.length === FPS && !this.walked.some(Boolean)) {
      for (let j = 0; j < nj - 1; j++) {
        let turns = 0
        let dir = 0
        let range = 0
        for (let k = 1; k < FPS; k++) {
          const d = this.history[k][j] - this.history[k - 1][j]
          range = Math.max(range, Math.abs(this.history[k][j] - this.history[0][j]))
          if (Math.abs(d) < 0.002) continue
          const s = Math.sign(d)
          if (dir && s !== dir) turns++
          dir = s
        }
        if (turns >= 6 && range > 0.03) this.note(`${JOINTS[j]} shakes (${turns} turns a second)`)
      }
    }
    const moved = Math.hypot(row[nj] - last[nj], row[nj + 1] - last[nj + 1]) * FPS
    if (moved > 11) this.note(`jumps in place (${moved.toFixed(1)} m/s)`)
    let turned = Math.abs(row[nj + 2] - last[nj + 2]) % (Math.PI * 2)
    turned = Math.min(turned, Math.PI * 2 - turned) * FPS
    if (turned > 7) this.note(`turns too fast (${turned.toFixed(1)} rad/s)`)
    const cam = Math.hypot(row[nj + 3] - last[nj + 3], row[nj + 4] - last[nj + 4], row[nj + 5] - last[nj + 5]) * FPS
    if (cam > 25) this.note(`camera jumps (${cam.toFixed(1)} m/s)`)
    const aim = Math.hypot(row[nj + 6] - last[nj + 6], row[nj + 7] - last[nj + 7], row[nj + 8] - last[nj + 8]) * FPS
    if (aim > 30) this.note(`camera swings (${aim.toFixed(1)} m/s)`)
  }

  /** The body inside something; the camera inside something, or not seeing them, or seeing them off to the side. */
  private collisions(): void {
    const w = this.w
    if (w.iris < 0.05) return // nothing to see
    const near = this.nearSolids()
    const body: { p: THREE.Vector3; r: number }[] = w.hero.samples()
    const head = w.hero.head.localToWorld(new THREE.Vector3(0, 0.18, 0))
    body.push({ p: head, r: 0.2 })
    // as Character.samples gives them: the hips, the chest, the collar, the hips' sides, then each leg and arm
    const names = ["hips", ...Array(6).fill("chest"), "collar", "hips", "hips", ...[0, 1].flatMap((i) => [...Array(6).fill(i ? "right leg" : "left leg"), ...Array(3).fill(i ? "right arm" : "left arm"), i ? "right hand" : "left hand"]), "head"]
    const hit = new Set<string>()
    body.forEach((b, i) => {
      const inside = this.inside(b.p, near)
      if (inside) hit.add(`${names[i] ?? "body"} inside ${this.name(inside)}`)
      for (const post of w.posts) {
        if (b.p.y < post.h && Math.hypot(b.p.x - post.x, b.p.z - post.z) < post.r) hit.add(`${names[i] ?? "body"} inside a post or trunk`)
      }
    })
    for (const h of hit) this.note(h)
    // the camera
    const cam = w.camera.position.clone()
    const inCam = this.inside(cam, near)
    if (inCam) this.note(`camera inside ${this.name(inCam)}`)
    for (const post of w.posts) if (cam.y < post.h && Math.hypot(cam.x - post.x, cam.z - post.z) < post.r + 0.1) this.note("camera inside a post or trunk")
    // filling the picture with the back of their head (30 Oct: walking in under the camera by the door)
    const close = cam.distanceTo(w.hero.headAt())
    if (close < 2 && w.iris > 0.15) this.note(`camera too close (${close.toFixed(1)} m)`)
    const chest = w.hero.samples()[2].p
    const to = chest.clone().sub(cam)
    const far = to.length()
    this.ray.set(cam, to.normalize())
    this.ray.far = far - 0.35
    const seen = near.filter((m) => this.visible(m))
    const block = this.ray.intersectObjects(seen, false)[0]
    if (block) this.note(`hidden by ${this.name(block.object)}`)
    const ndc = chest.clone().project(w.camera)
    // the end looks out over the town, past them; going back from it, the camera comes down to them
    const crane = ["reveal", "start"].includes(w.step) || w.camera.position.distanceTo(chest) > 20
    if (crane) return
    if (Math.abs(ndc.x) > 0.95 || Math.abs(ndc.y) > 0.95 || ndc.z > 1) this.note("off the picture")
    else if (ndc.x > 2 * ((1080 - 32 - 440) / 1080) - 1) this.note("behind the question's box")
  }

  /** The meshes in the places near them and near the camera. */
  private nearSolids(): THREE.Mesh[] {
    const w = this.w
    const out: THREE.Mesh[] = []
    for (const site of w.sites.values()) {
      if (!site.group) continue
      const centre = site.group.position
      const close = (p: THREE.Vector3) => Math.hypot(p.x - centre.x, p.z - centre.z) < 22
      if (!close(w.pos) && !close(w.camera.position)) continue
      let list = this.solids.get(site.group)
      if (!list) {
        list = []
        site.group.traverse((o: THREE.Object3D) => {
          const m = o as THREE.Mesh
          if (!m.isMesh) return
          for (let p: THREE.Object3D | null = m; p; p = p.parent) if (p.userData.cloth) return
          const mat = m.material as THREE.Material
          if (Array.isArray(mat) || mat.transparent || (mat as Any).isShaderMaterial) return
          list?.push(m)
        })
        this.solids.set(site.group, list)
      }
      out.push(...list)
    }
    return out
  }

  /** Inside a closed solid: looking out along three ways, each first meets a face from behind. */
  private inside(p: THREE.Vector3, meshes: THREE.Mesh[]): THREE.Object3D | null {
    let first: THREE.Object3D | null = null
    for (const d of DIRS) {
      this.ray.set(p, d)
      this.ray.far = 6
      const hits = this.ray.intersectObjects(meshes.filter((m) => this.shown(m)), false)
      const h = hits[0]
      if (!h?.face) return null
      const n = h.face.normal.clone()
      if (h.instanceId !== undefined) {
        const m = new THREE.Matrix4()
        ;(h.object as THREE.InstancedMesh).getMatrixAt(h.instanceId, m)
        n.transformDirection(m)
      }
      n.transformDirection(h.object.matrixWorld)
      if (n.dot(d) <= 0.05) return null
      first ??= h.object
    }
    return first
  }

  /** There at all (a laptop put away isn't). */
  private shown(o: THREE.Object3D): boolean {
    for (let p: THREE.Object3D | null = o; p; p = p.parent) if (!p.visible) return false
    return true
  }

  /** There and drawn for the camera (what's cut away isn't). */
  private visible(o: THREE.Mesh): boolean {
    return this.shown(o) && o.layers.test(this.w.camera.layers)
  }

  private name(o: THREE.Object3D): string {
    const mat = (o as THREE.Mesh).material as THREE.MeshStandardMaterial
    const site = [...this.w.sites.values()].find((s: Any) => {
      for (let p: THREE.Object3D | null = o; p; p = p.parent) if (p === s.group) return true
      return false
    })
    const colour = mat?.color ? `#${mat.color.getHexString()}` : ""
    const what = (o as THREE.InstancedMesh).isInstancedMesh ? "books" : mat?.map ? "a textured surface" : "something"
    return `${what} ${colour} (${site?.place ?? "street"})`
  }

  private doubleSided(on: boolean): void {
    this.w.scene.traverse((o: THREE.Object3D) => {
      const m = (o as THREE.Mesh).material
      if (!m || Array.isArray(m)) return
      if (on) {
        if (!this.sides.has(m)) this.sides.set(m, m.side)
        m.side = THREE.DoubleSide
      } else if (this.sides.has(m)) m.side = this.sides.get(m) as THREE.Side
    })
  }

  /** The same finding over consecutive frames, once, with how long it held. */
  private merged(): Finding[] {
    const out: Finding[] = []
    for (const f of this.findings) {
      const last = out.find((o) => o.where === f.where && o.what.replace(/\(.*\)/, "") === f.what.replace(/\(.*\)/, ""))
      if (last) last.n = (last.n ?? 1) + 1
      else out.push({ ...f, n: 1 })
    }
    return out
  }
}
