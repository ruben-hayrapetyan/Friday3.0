// The one who walked you through your week in setup, along the foot of the window afterwards, showing you round
// Friday (30 Oct: "when you are finished with the setup, make the welcome to friday be guided by the same character
// and make it more in depth"). The same body (character.ts), drawn the same way (pixels.ts): small, outlined and
// dithered, standing on the window's bottom edge over the page. They jog to below what each step of the tour is about
// and point up at it, open their arms to the calendar, think over the rules, read the inbox's letter. Loaded only for
// the tour (shell/Tour.tsx imports it when the tour opens).

import * as THREE from "three"
import { EffectComposer } from "three/examples/jsm/postprocessing/EffectComposer.js"
import { type Action, Character, type Reaction } from "./character"
import { PixelOut, Pixels } from "./pixels"
import { STRIP } from "./strip"

export type Gesture = "wave" | "point" | "present" | "think" | "mail" | "stand"
const TALL = 1.72 // metres, head to toe
const PIXEL = 3 // CSS pixels to one of theirs, as in setup's town
const RUN = 5 // metres a second at most: a run across the window takes about two seconds
const ACCEL = 9 // metres a second, a second

export interface Cue {
  x: number // where to stand: CSS pixels from the window's left
  gesture: Gesture
  aim?: { x: number; y: number } | null // what to point at, in the window's CSS pixels
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
    this.scene.add(this.hero.root)
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
    this.hero.root.position.y = hit.y
  }

  /** Go to a spot and do something there: point at what the step's about, open their arms, think, wave. */
  cue(cue: Cue): void {
    this.goal = this.toMetres(cue.x)
    this.aim = cue.aim ?? null
    this.arrived = false
    this.leaving = 0
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

  /** A wave and off the side of the window. */
  leave(): void {
    this.leaving = this.x > 0 ? 1 : -1
    this.goal = this.leaving * (this.width / 2 + 80) * this.metres
    this.arrived = false
    this.gesture = "stand"
    this.before = null
  }

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
        if (!this.leaving) this.onArrive?.()
      }
    }
    const moving = this.v > 0.05
    // turned along the way while going; to you once there
    const facing = moving ? Math.sign(left || 1) * (Math.PI / 2) : 0
    const k = 1 - Math.pow(0.0001, dt)
    this.yaw += Math.max(-9 * dt, Math.min(9 * dt, (facing - this.yaw) * k))
    this.weight = moving ? Math.max(0, this.weight - dt * 5) : Math.min(1, this.weight + dt * 2.6)
    this.change = Math.min(1, this.change + dt / 0.6)
    this.talk += ((this.talking && !moving ? 1 : 0) - this.talk) * Math.min(1, dt * 6)
    this.hero.root.position.x = this.x
    this.hero.root.rotation.y = this.yaw
    this.hero.update(dt, t, {
      speed: this.v,
      action: this.gesture as Action,
      weight: this.weight,
      before: this.before && this.change < 1 ? (this.before as Action) : undefined,
      change: this.change,
      mood: { aim: this.pointing(), talk: this.talk },
    })
    this.composer.render(dt)
  }

  /** Which way to point, from their shoulder to what the step's about, facing you: from straight down, toward their
   * left (the window's right) positive. */
  private pointing(): number {
    if (!this.aim) return 2.4
    const shoulder = new THREE.Vector3(this.x, this.hero.root.position.y + 1.25, 0).project(this.camera)
    const sx = ((shoulder.x + 1) / 2) * this.width
    const sy = window.innerHeight - STRIP + ((1 - shoulder.y) / 2) * STRIP
    return Math.atan2(this.aim.x - sx, this.aim.y - sy)
  }
}
