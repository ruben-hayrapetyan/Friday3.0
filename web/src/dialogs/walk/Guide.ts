// The one who walked you through your week in setup, along the foot of the window afterwards, showing you round
// Friday (30 Oct: "when you are finished with the setup, make the welcome to friday be guided by the same character
// and make it more in depth"). The same body (character.ts), drawn the same way (pixels.ts): small, outlined and
// dithered, standing on the window's bottom edge over the page. They jog to below what each step of the tour is about
// and point up at it, open their arms to the calendar, think over the rules, read the inbox's letter. Loaded only for
// the tour (shell/Tour.tsx imports it when the tour opens).

import * as THREE from "three"
import { EffectComposer } from "three/examples/jsm/postprocessing/EffectComposer.js"
import { type Action, Character, ease, type GuideAction, type Reaction, Signs } from "./character"
import { PixelOut, Pixels } from "./pixels"
import { STRIP } from "./strip"

export type Gesture = "wave" | "point" | "present" | "think" | "mail" | "stand" | GuideAction
const TALL = 1.72 // metres, head to toe
const PIXEL = 3 // CSS pixels to one of theirs, as in setup's town
const RUN = 5 // metres a second at most: a run across the window takes about two seconds
const ACCEL = 9 // metres a second, a second
const HOP = 0.8 // seconds: down for it, up, and landing
const HIGH = 0.32 // metres off the floor at the top of a hop

export interface Cue {
  x: number // where to stand: CSS pixels from the window's left
  gesture: Gesture
  aim?: { x: number; y: number } | null // what to point at, in the window's CSS pixels
  jump?: boolean // a hop on getting there (30 Oct: "have the sprite do more (like jump and point to something)")
  cheer?: boolean // both arms up for it
  sweep?: { top: number; bottom: number } // the pointing runs up and down this, as a finger down a list
  sign?: string // over the head on getting there: "?", "z", "sweat", "!", "heart", "note" (character.ts Signs)
  after?: string // and once they've said their piece
  shades?: boolean // sunglasses on: the weekend
}

export class Guide {
  private renderer: THREE.WebGLRenderer
  private composer: EffectComposer
  private out = new PixelOut(true)
  private scene = new THREE.Scene()
  private camera = new THREE.PerspectiveCamera(12, 1, 1, 100)
  private hero = new Character()
  private width = 1
  private metres = TALL / 165 // a CSS pixel, in metres at their distance
  private x = -0.6 // metres from the middle of the window
  private goal = 0
  private v = 0
  private yaw = Math.PI / 2
  private weight = 0
  private gesture: Gesture = "wave"
  private before: Gesture | null = null
  private change = 1
  private aim: { x: number; y: number } | null = null
  private talk = 0
  private talking = false
  private arrived = false
  private leaving = 0 // which way off the window: -1, 1, or 0 not leaving
  private floor = 0 // the strip's foot, where they stand
  private hopNext: { cheer: boolean } | null = null // a hop to make on getting there
  private hopAt: number | null = null // when the hop under way began
  private cheering = false
  private glanceAt = 0
  private signs = new Signs()
  private sign: string | null = null
  private after: string | null = null
  private sweep: { top: number; bottom: number } | null = null
  private shades = false
  private noteAt = 0
  private spinAt: number | null = null // a twirl, poked
  private spins = 1
  private wobbleAt: number | null = null // dizzy, poked again and again
  private pokes: number[] = []
  private wasMoving = false
  /** Called once they're off the side of the window, leaving. */
  onGone: (() => void) | null = null
  private started = performance.now()
  private last = 0
  private frame = 0
  private reduced: boolean
  /** Called once they get to where a cue sent them. */
  onArrive: (() => void) | null = null

  constructor(canvas: HTMLCanvasElement, options: { reduced?: boolean } = {}) {
    this.reduced = !!options.reduced
    this.renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: false, powerPreference: "low-power", premultipliedAlpha: true })
    this.renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1))
    this.renderer.setClearColor(0x000000, 0)
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping
    this.renderer.toneMappingExposure = 0.75
    this.composer = new EffectComposer(this.renderer)
    this.composer.addPass(new Pixels(this.scene, this.camera))
    this.composer.addPass(this.out)
    // a late-October afternoon's light, from the front and above to one side
    const sun = new THREE.DirectionalLight(0xfff0d8, 2.6)
    sun.position.set(-3, 6, 8)
    this.scene.add(sun, new THREE.HemisphereLight(0xdfe8ff, 0x7a6a58, 1.5))
    this.hero.wearPack(true)
    this.scene.add(this.hero.root, this.signs.group)
    this.last = performance.now()
    this.loop = this.loop.bind(this)
    this.frame = requestAnimationFrame(this.loop)
  }

  /** The window's width changed (the strip is always the window's width and STRIP tall). */
  resize(width: number): void {
    this.width = Math.max(1, width)
    const px = PIXEL
    this.renderer.setSize(this.width, STRIP, false)
    this.composer.setPixelRatio(1)
    const low = [Math.max(1, Math.floor(this.width / px)), Math.max(1, Math.floor(STRIP / px))]
    this.composer.setSize(low[0], low[1])
    this.out.low.set(low[0], low[1])
    // far off with a narrow lens, so walking along the strip they barely change in perspective; the strip's height
    // at their distance is set so they come out about 165 pixels tall
    const high = STRIP * this.metres
    const away = 14
    this.camera.aspect = this.width / STRIP
    this.camera.fov = THREE.MathUtils.radToDeg(2 * Math.atan(high / 2 / away))
    this.camera.position.set(0, high / 2 + 0.25, away)
    this.camera.lookAt(0, high / 2, 0)
    this.camera.updateProjectionMatrix()
    // feet on the bottom edge, a few pixels up (the shoes reach below the soles)
    const ray = new THREE.Raycaster()
    ray.setFromCamera(new THREE.Vector2(0, -1 + (2 * 9) / STRIP), this.camera)
    const hit = new THREE.Vector3()
    ray.ray.intersectPlane(new THREE.Plane(new THREE.Vector3(0, 0, 1), 0), hit)
    this.floor = hit.y
    this.hero.root.position.y = hit.y
  }

  /** Go to a spot and do something there: point at what the step's about, open their arms, think, wave. */
  cue(cue: Cue): void {
    this.goal = this.toMetres(cue.x)
    this.aim = cue.aim ?? null
    this.arrived = false
    this.leaving = 0
    this.hopNext = cue.jump && !this.reduced ? { cheer: !!cue.cheer } : null
    this.sign = cue.sign ?? null
    this.after = cue.after ?? null
    this.sweep = cue.sweep ?? null
    this.shades = !!cue.shades
    if (cue.gesture !== this.gesture) {
      this.before = this.gesture
      this.change = 0
      this.gesture = cue.gesture
    }
    if (this.reduced) {
      this.x = this.goal
      this.v = 0
    }
  }

  /** Saying something (the box's words still coming): the head moves with them. */
  say(on: boolean): void {
    this.talking = on
  }

  /** A moment's reaction over what they're doing: a nod, a glance at you. */
  react(kind: Reaction): void {
    this.hero.react(kind, this.seconds())
  }

  /** They've said their piece: a nod, and the sign for it ("!" once the rules make sense). */
  said(): void {
    if (this.gesture !== "dance" && this.gesture !== "yawn") this.react("nod")
    if (this.after) this.emit(this.after)
    this.after = null
  }

  private emit(kind: string): void {
    this.signs.emit(kind, this.hero.headAt().add(new THREE.Vector3(0.22, 0.05, 0.2)), this.seconds(), 0.34)
  }

  /** Something else to do where they stand, now (the end's tearing off Friday, then dancing). */
  act(gesture: Gesture, options: { shades?: boolean } = {}): void {
    if (gesture !== this.gesture) {
      this.before = this.gesture
      this.change = 0
      this.gesture = gesture
    }
    if (options.shades !== undefined) this.shades = options.shades
  }

  /** Poked (a click on them): a twirl and a hop, a star; poked three times quickly, dizzy. */
  poke(): void {
    if (this.reduced || this.leaving) return
    const t = this.seconds()
    this.pokes = [...this.pokes.filter((at) => t - at < 4), t]
    const dizzy = this.pokes.length >= 3
    this.spinAt = t
    this.spins = dizzy ? 2 : 1
    this.hop(false)
    this.emit(dizzy ? "dizzy" : this.pokes.length === 2 ? "note" : "star")
    if (dizzy) {
      this.wobbleAt = t + 0.7
      this.pokes = []
    }
  }

  /** Where they stand on the page, for a click on them: the middle of them, in the window's CSS pixels. */
  box(): { x: number; width: number; height: number } {
    return { x: this.at(), width: 0.7 / this.metres, height: (TALL + 0.1) / this.metres }
  }

  /** Something done (a quest): a jump for joy and a star. */
  celebrate(): void {
    if (this.reduced) return
    this.hop(true)
    this.emit("star")
  }

  /** A hop where they stand, now. */
  hop(cheer = false): void {
    if (this.reduced) return
    this.hopAt = this.seconds()
    this.cheering = cheer
  }

  /** Off the side of the window: the way they face, or (`right`) skipping off that way, to the weekend. */
  leave(right = false): void {
    this.leaving = right || this.x > 0 ? 1 : -1
    this.goal = this.leaving * (this.width / 2 + 80) * this.metres
    this.arrived = false
    this.skipping = right
    this.gesture = "stand"
    this.before = null
  }
  private skipping = false

  /** Where they are now, in the window's CSS pixels from its left. */
  at(): number {
    return this.x / this.metres + this.width / 2
  }

  dispose(): void {
    cancelAnimationFrame(this.frame)
    this.composer.dispose()
    this.renderer.dispose()
    this.renderer.forceContextLoss()
  }

  private toMetres(x: number): number {
    return (x - this.width / 2) * this.metres
  }

  private seconds(): number {
    return (performance.now() - this.started) / 1000
  }

  private loop(time: number): void {
    this.frame = requestAnimationFrame(this.loop)
    const dt = Math.max(0, Math.min(0.05, (time - this.last) / 1000))
    this.last = time
    const t = this.seconds()
    // along the bottom: speeding up, then slowing to stop on the spot
    const left = this.goal - this.x
    const far = Math.abs(left)
    if (far > 0.01) {
      const most = Math.min(RUN, Math.sqrt(2 * ACCEL * far))
      this.v = Math.min(most, this.v + ACCEL * dt)
      const step = Math.min(far, this.v * dt)
      this.x += Math.sign(left) * step
    } else {
      this.x = this.goal
      this.v = 0
      if (!this.arrived) {
        this.arrived = true
        if (this.hopNext) this.hop(this.hopNext.cheer)
        this.hopNext = null
        this.glanceAt = t + 7
        if (this.sign && !this.leaving) this.emit(this.sign)
        this.sign = null
        if (this.leaving) this.onGone?.()
        else this.onArrive?.()
      }
    }
    const moving = this.v > 0.05
    // a puff of dust off the floor setting off, and skidding to a stop
    if (moving !== this.wasMoving && Math.abs(left) + this.v > 0.2) {
      const back = -Math.sign(left || 1)
      this.signs.emit("dust", new THREE.Vector3(this.x + back * 0.25, this.floor + 0.08, 0.2), t, 0.3, back)
      this.signs.emit("dust", new THREE.Vector3(this.x + back * 0.05, this.floor + 0.05, 0.25), t, 0.22, back)
    }
    this.wasMoving = moving
    // turned along the way while going; to you once there
    const facing = moving ? Math.sign(left || 1) * (Math.PI / 2) : 0
    const k = 1 - Math.pow(0.0001, dt)
    this.yaw += Math.max(-9 * dt, Math.min(9 * dt, (facing - this.yaw) * k))
    this.weight = moving ? Math.max(0, this.weight - dt * 5) : Math.min(1, this.weight + dt * 2.6)
    this.change = Math.min(1, this.change + dt / 0.6)
    this.talk += ((this.talking && !moving ? 1 : 0) - this.talk) * Math.min(1, dt * 6)
    // a hop: bending for it, up with the legs tucked a little (and the arms up, cheering), and landing on bent knees
    let crouch = 0
    let cheer = 0
    let lift = 0
    if (this.hopAt !== null) {
      const u = (t - this.hopAt) / HOP
      if (u >= 1) this.hopAt = null
      else if (u < 0.25) crouch = ease(u / 0.25)
      else if (u < 0.7) {
        const v = (u - 0.25) / 0.45
        lift = HIGH * 4 * v * (1 - v)
        crouch = 0.25
      } else crouch = 0.8 * Math.sin((Math.PI * (u - 0.7)) / 0.3)
      if (this.cheering) cheer = Math.max(0, Math.sin(Math.PI * Math.min(1, Math.max(0, (u - 0.1) / 0.8))))
    }
    // skipping off to the weekend: a hop in every other step, an arm up
    if (this.skipping && moving) {
      lift = Math.max(lift, 0.1 * Math.abs(Math.sin(t * 7.5)))
      cheer = Math.max(cheer, 0.45)
    }
    // dancing: music
    if (this.gesture === "dance" && this.arrived && t > this.noteAt) {
      this.emit("note")
      this.noteAt = t + 1.3
    }
    // now and then, while you read, a look at you
    if (this.arrived && !moving && !this.talking && this.hopAt === null && t > this.glanceAt && this.gesture !== "think") {
      this.hero.react("glance", t)
      this.glanceAt = t + 7 + Math.random() * 4
    }
    // a twirl, poked; dizzy after, swaying
    let spin = 0
    if (this.spinAt !== null) {
      const u = (t - this.spinAt) / (0.55 * this.spins)
      if (u >= 1) this.spinAt = null
      else spin = Math.PI * 2 * this.spins * ease(u)
    }
    let sway = 0
    if (this.wobbleAt !== null && t >= this.wobbleAt) {
      const u = (t - this.wobbleAt) / 1.6
      if (u >= 1) this.wobbleAt = null
      else sway = Math.sin(u * Math.PI * 6) * 0.12 * (1 - u)
    }
    this.hero.root.position.set(this.x, this.floor + lift, 0)
    this.hero.root.rotation.set(0, this.yaw + spin, sway)
    this.hero.update(dt, t, {
      speed: this.v,
      action: this.gesture as Action,
      weight: this.weight,
      before: this.before && this.change < 1 ? (this.before as Action) : undefined,
      change: this.change,
      mood: { aim: this.pointing(), talk: this.talk, crouch, cheer, shades: this.shades },
    })
    this.signs.update(t, dt)
    this.composer.render(dt)
  }

  /** Which way to point, from their shoulder to what the step's about, facing you: from straight down, toward their
   * left (the window's right) positive. */
  private pointing(): number {
    if (!this.aim) return 2.4
    // down a list and back up, as a finger runs down it
    const y = this.sweep ? this.sweep.top + (this.sweep.bottom - this.sweep.top) * (0.5 - 0.5 * Math.cos(this.seconds() * 1.4)) : this.aim.y
    const shoulder = new THREE.Vector3(this.x, this.hero.root.position.y + 1.25, 0).project(this.camera)
    const sx = ((shoulder.x + 1) / 2) * this.width
    const sy = window.innerHeight - STRIP + ((1 - shoulder.y) / 2) * STRIP
    return Math.atan2(this.aim.x - sx, y - sy)
  }
}
