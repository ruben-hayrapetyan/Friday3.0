// The walk through your week (29 Oct: "i want it to be like very well animated, similar to
// https://c-nell-portfolio.vercel.app/", then realistic, then "make it a little less realistic... revert back to doing
// some pixel sprite thing but make it more engaging not just a sprite going from left to right - make the sprite a lot
// better"). A college town in late October, built in 3D and drawn as pixel art: rendered at a third of the screen's
// resolution, outlined where things stand in front of others, a few shades fewer with a fine ordered dither, then
// scaled up crisp. The light is still real (a sky and sun that move with the hours, shadows, lamps at night), and the
// one who walks you through (walk/character.ts) goes from place to place with a camera that follows: out of one door,
// across the street, in at the next, where the front of the house is cut away so you can see them at it.
// Loaded only for setup (Setup.tsx imports it when it opens).

import * as THREE from "three"
import { Sky } from "three/examples/jsm/objects/Sky.js"
import { EffectComposer } from "three/examples/jsm/postprocessing/EffectComposer.js"
import { OutputPass } from "three/examples/jsm/postprocessing/OutputPass.js"
import { FullScreenQuad, Pass } from "three/examples/jsm/postprocessing/Pass.js"
import { UnrealBloomPass } from "three/examples/jsm/postprocessing/UnrealBloomPass.js"
import type { Schemas } from "@/api/client"
import { type Action, BED, Character, type Mood, mixPose, type Pose, type Reaction, SEATED, Signs } from "./character"
import { fallen, forest, type Planting, woods } from "./nature"
import { type Built, buildPlace, type Duvet, FLOOR, FRONT, type Scene, SIDEWALK, type Socket, sittingFor } from "./places"
import { hazeColor, type Light, lightAt, timeStep } from "./sky"
import { minutesOf, type Place, placeZ, ROUTE, STOPS } from "./stops"
import { moonFace } from "./textures"
import { type Lot, street } from "./town"

type Answers = Schemas["SetupInput"]

const LAMPS = 6 // lights moved to wherever you are
const V = (x: number, y: number, z: number) => new THREE.Vector3(x, y, z)

/** The town drawn small, with dark edges where something stands in front of what's behind it, the way pixel art is
 * outlined. (Its own target, for its own depth: the composer's two share one depth texture.) */
class Pixels extends Pass {
  private quad: FullScreenQuad
  private material: THREE.ShaderMaterial
  private camera: THREE.PerspectiveCamera
  private scene: THREE.Scene
  private beauty = new THREE.WebGLRenderTarget(1, 1, { type: THREE.HalfFloatType, minFilter: THREE.NearestFilter, magFilter: THREE.NearestFilter, depthTexture: new THREE.DepthTexture(1, 1) })

  constructor(scene: THREE.Scene, camera: THREE.PerspectiveCamera) {
    super()
    this.scene = scene
    this.camera = camera
    this.material = new THREE.ShaderMaterial({
      uniforms: { tDiffuse: { value: null }, tDepth: { value: null }, texel: { value: new THREE.Vector2() }, near: { value: 0.1 }, far: { value: 1600 } },
      vertexShader: "varying vec2 vUv; void main() { vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }",
      fragmentShader: `
        #include <packing>
        uniform sampler2D tDiffuse;
        uniform sampler2D tDepth;
        uniform vec2 texel;
        uniform float near;
        uniform float far;
        varying vec2 vUv;
        float away(vec2 uv) { return -perspectiveDepthToViewZ(texture2D(tDepth, uv).x, near, far); }
        void main() {
          vec4 c = texture2D(tDiffuse, vUv);
          float z = away(vUv);
          float gap = max(0.22, z * 0.045);
          float edge = 0.0;
          edge = max(edge, step(gap, away(vUv + vec2(texel.x, 0.0)) - z));
          edge = max(edge, step(gap, away(vUv - vec2(texel.x, 0.0)) - z));
          edge = max(edge, step(gap, away(vUv + vec2(0.0, texel.y)) - z));
          edge = max(edge, step(gap, away(vUv - vec2(0.0, texel.y)) - z));
          edge *= 1.0 - smoothstep(60.0, 160.0, z);
          gl_FragColor = vec4(mix(c.rgb, c.rgb * vec3(0.32, 0.3, 0.38), edge * 0.9), c.a);
        }`,
    })
    this.quad = new FullScreenQuad(this.material)
  }

  setSize(width: number, height: number): void {
    this.beauty.setSize(width, height)
    ;(this.material.uniforms.texel.value as THREE.Vector2).set(1 / width, 1 / height)
  }

  render(renderer: THREE.WebGLRenderer, writeBuffer: THREE.WebGLRenderTarget): void {
    renderer.setRenderTarget(this.beauty)
    renderer.clear()
    renderer.render(this.scene, this.camera)
    const u = this.material.uniforms
    u.tDiffuse.value = this.beauty.texture
    u.tDepth.value = this.beauty.depthTexture
    u.near.value = this.camera.near
    u.far.value = this.camera.far
    renderer.setRenderTarget(this.renderToScreen ? null : writeBuffer)
    this.quad.render(renderer)
  }
}

/** The film curve and colour, then fewer shades with an ordered dither, at the pixels' own size. */
class PixelOut extends OutputPass {
  readonly low: THREE.Vector2
  constructor() {
    super()
    const self = this as unknown as { uniforms: Record<string, THREE.IUniform>; material: THREE.RawShaderMaterial }
    this.low = new THREE.Vector2(1, 1)
    self.uniforms.uLow = { value: this.low }
    self.material.fragmentShader = self.material.fragmentShader.replace("varying vec2 vUv;", "varying vec2 vUv;\nuniform vec2 uLow;\nfloat bayer2(vec2 a) { a = floor(a); return fract(a.x / 2.0 + a.y * a.y * 0.75); }\nfloat bayer4(vec2 a) { return bayer2(0.5 * a) * 0.25 + bayer2(a); }").replace(
      /}\s*$/,
      `  float levels = 22.0;
        float d = bayer4(floor(vUv * uLow)) - 0.5;
        gl_FragColor.rgb = floor(gl_FragColor.rgb * levels + 0.5 + d * 0.9) / levels;
      }`,
    )
  }
}

interface Site {
  place: Place
  side: number
  built: Built | null
  group: THREE.Group | null
  street: THREE.Vector3 // at the curb in front of it
  inside: THREE.Vector3 | null
  outside: THREE.Vector3 | null
  room: THREE.Box2 | null // indoors, in the world
}

interface Act {
  site: Site
  via?: THREE.Vector3[]
  walk: THREE.Vector3
  at: THREE.Vector3
  yaw: number
  action: Action
  seat?: number
  mood?: Mood
  bed?: BedHere
  cam: { pos: THREE.Vector3; look: THREE.Vector3 }
}

/** A bed in the world: where they stand by it, sit on its edge, lie and sit up, facing which way; its duvet. */
interface BedHere {
  side: THREE.Vector3
  edge: THREE.Vector3
  lie: THREE.Vector3
  up: THREE.Vector3
  yawEdge: number
  yawIn: number
  top: number
  duvet: Duvet
  closed: number
  waist: number
  open: number
}

/** One moment of a scene that moves them by hand: their pose, where, facing which way, and the duvet. */
interface Key {
  at: number
  pose: Pose
  pos: THREE.Vector3
  yaw: number
  fold: number
  full: number
  cue?: string
}

/** Getting into bed (and, for the alarm, sitting up), or out of it, key by key. */
interface Script {
  keys: Key[]
  t: number
  bed: BedHere
  site: Site
  cued: Set<string>
  fast: number
}

/** Going from one thing to the next: out of bed or up from a seat first, walking the path (speeding up, going
 * steadily, slowing down), then into what's next. */
interface Trip {
  path: THREE.CatmullRomCurve3 | null
  length: number
  clock: number // seconds into the walk (after getting up)
  fast: number // how much quicker than life (Return again hurries it)
  rise: number // seconds standing up from a seat
  out: Script | null // or getting out of bed
  walk: number // seconds walking (0: staying where they are)
  cruise: number // metres a second, once going
  ahead: number // which way up the street: the camera goes ahead of them
  from: { minutes: number; cam: { pos: THREE.Vector3; look: THREE.Vector3 }; act: Act | null }
  to: Act
  minutes: number
  delta: number
}

const SPEED_UP = 0.4 // seconds getting going
const SLOW_DOWN = 0.5 // and stopping

/** How far along a walk of `length` metres they are `t` seconds in: speeding up to `cruise`, steady, slowing down. */
export function along(t: number, length: number, cruise: number): number {
  const total = length / cruise + (SPEED_UP + SLOW_DOWN) / 2
  if (t <= 0) return 0
  if (t >= total) return length
  if (t < SPEED_UP) return 0.5 * (cruise / SPEED_UP) * t * t
  if (t > total - SLOW_DOWN) {
    const left = total - t
    return length - 0.5 * (cruise / SLOW_DOWN) * left * left
  }
  return 0.5 * cruise * SPEED_UP + cruise * (t - SPEED_UP)
}

/** A walk's pace (30 Oct: "make the walking animations faster - like make it walk less"): a few steps across a
 * room, a jog over the street; about three seconds at most. */
export function paceFor(length: number): number {
  const cruise = Math.max(2.4, Math.min(9, length / 2.4))
  return Math.min(cruise, length / ((SPEED_UP + SLOW_DOWN) / 2) - 0.001)
}

/** The nearest way round the clock from one time to another, in minutes (30 Oct: changing bedtime from 12am to
 * 11:30pm went the long way, through a whole day, and the sky flashed white). */
export function shortest(d: number): number {
  return ((((d + 720) % 1440) + 1440) % 1440) - 720
}

/** What they do when an answer changes: the answer acted out where it's asked (a book onto the day's pile, the
 * timer set, the note moved along the week), or a moment's feeling about it (a yawn at an earlier alarm, hands
 * behind the head at more time of their own). `aim` is where along the board, for the note. */
export function reactionTo(was: Answers, now: Answers): { kind: Reaction; aim?: number } | null {
  if (now.wake !== was.wake) return { kind: minutesOf(now.wake) < minutesOf(was.wake) ? "yawn" : "cheer" }
  if (now.bedtime !== was.bedtime || now.weekend_wake !== was.weekend_wake || now.weekend_bedtime !== was.weekend_bedtime) return { kind: "nod" }
  if (now.normal_hours !== was.normal_hours) return { kind: "stackRight" }
  if (now.most_hours !== was.most_hours) return { kind: "stackLeft" }
  if (now.focus_hours !== was.focus_hours) return { kind: "timer" }
  if (now.finish_early_days !== was.finish_early_days) {
    const day = 4 - Math.max(0, Math.min(4, now.finish_early_days))
    return { kind: "pin", aim: (-0.448 + day * 0.224) / 0.45 }
  }
  if (now.evening_free !== was.evening_free) return now.evening_free > was.evening_free && was.evening_free > 0 ? { kind: "relax" } : null
  if (now.evening_from !== was.evening_from) return { kind: "nod" }
  if (now.weekend_free !== was.weekend_free) return now.weekend_free > was.weekend_free && was.weekend_free > 0 ? { kind: "relax" } : null
  if (JSON.stringify(now.calendars ?? []) !== JSON.stringify(was.calendars ?? [])) return { kind: "nod" }
  return null
}

const SIGN_FOR: Partial<Record<Reaction, string>> = { cheer: "note", yawn: "z", relax: "heart" }

/** What they do now and then while you decide, by what they're doing: small, and not often. */
const FIDGETS: Partial<Record<Action, Reaction[]>> = {
  stand: ["glance"],
  wave: ["glance"],
  wake: ["yawn", "glance"],
  study: ["glance", "scratch"],
  read: ["glance", "scratch"],
  tv: ["glance", "relax"],
  laptop: ["scratch", "glance"],
  picnic: ["glance"],
  coffee: ["glance"],
  counter: ["glance"],
  boxes: ["glance"],
  calendar: ["glance"],
}

const smooth = (a: number, b: number, x: number) => {
  const t = Math.max(0, Math.min(1, (x - a) / (b - a)))
  return t * t * (3 - 2 * t)
}
const ease = (t: number) => -(Math.cos(Math.PI * Math.max(0, Math.min(1, t))) - 1) / 2

export class World {
  private renderer: THREE.WebGLRenderer
  private composer: EffectComposer
  private out: PixelOut
  private scene = new THREE.Scene()
  private camera = new THREE.PerspectiveCamera(30, 1, 0.1, 1600)
  private sky: THREE.Mesh
  private skyMat: THREE.ShaderMaterial
  private envScene = new THREE.Scene()
  private pmrem: THREE.PMREMGenerator
  private env: THREE.WebGLRenderTarget | null = null
  private envSun = V(0, -2, 0)
  private envAt = 0
  private sun = new THREE.DirectionalLight(0xffffff, 3)
  private moonLight = new THREE.DirectionalLight(0x9fb3ff, 0)
  private fill = new THREE.HemisphereLight(0xbfd6ff, 0x6b5a45, 0.5)
  private pool: THREE.PointLight[] = []
  private sockets: Socket[] = []
  private stars: THREE.Points
  private moon: THREE.Mesh
  private fog = new THREE.FogExp2(0xc9d6e3, 0.007)
  private glowing: THREE.MeshStandardMaterial[] = []
  private sites = new Map<Place, Site>()
  private hero = new Character()
  private signs = new Signs()
  private raf = 0
  private last = performance.now()
  private started = performance.now()
  private trip: Trip | null = null
  private script: Script | null = null // into bed, now
  private release: { pose: Pose; t: number } | null = null // easing from a scene's last pose into the action
  private answers: Answers | null = null
  private fidgetAt = 6 // seconds: when they next do something while you decide
  private rings = -1 // the focus timer's rings so far
  private act: Act | null = null // what they're doing now (null while walking)
  private weight = 0 // how far into it
  private before: Action | null = null // what they were doing at the same place, fading out
  private changed = 1
  private pos = V(-5.9, 0.15, 6) // their feet
  private yaw = 0
  private ground = 0.15
  private speed = 0
  private minutes = 400
  private cam = { pos: V(0, 3, 16), look: V(-5.9, 1, 6), vPos: V(0, 0, 0), vLook: V(0, 0, 0) }
  private step = "hello"
  private cutaway: Site | null = null
  private shift: [number, number] = [0, 0]
  private size = { w: 1, h: 1 }
  private frames: number[] = []
  private ready = false
  private options: { still: boolean; onReady?: () => void }

  constructor(canvas: HTMLCanvasElement, options: { still: boolean; onReady?: () => void }) {
    this.options = options
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: false, powerPreference: "high-performance" })
    this.renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1))
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping
    this.renderer.toneMappingExposure = 0.6
    this.renderer.shadowMap.enabled = true
    this.renderer.shadowMap.type = THREE.PCFShadowMap
    this.pmrem = new THREE.PMREMGenerator(this.renderer)
    this.scene.fog = this.fog

    // the sky, and a copy of it alone for the light it gives
    const shader = Sky.SkyShader as { uniforms: Record<string, THREE.IUniform>; vertexShader: string; fragmentShader: string }
    this.skyMat = new THREE.ShaderMaterial({
      name: "WalkSky",
      uniforms: { ...THREE.UniformsUtils.clone(shader.uniforms), uGlow: { value: V(0, 0, 0) } },
      vertexShader: shader.vertexShader,
      fragmentShader: shader.fragmentShader
        .replace("uniform vec3 up;", "uniform vec3 up;\nuniform vec3 uGlow;")
        .replace("gl_FragColor = vec4( retColor, 1.0 );", "gl_FragColor = vec4( retColor + uGlow * ( 1.0 - 0.6 * clamp( direction.y, 0.0, 1.0 ) ), 1.0 );"),
      side: THREE.BackSide,
      depthWrite: false,
    })
    this.sky = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), this.skyMat)
    this.sky.scale.setScalar(1000)
    this.sky.frustumCulled = false
    this.sky.renderOrder = -2
    this.scene.add(this.sky)
    const envSky = new THREE.Mesh(this.sky.geometry, this.skyMat)
    envSky.scale.setScalar(1000)
    this.envScene.add(envSky)

    const starPos: number[] = []
    for (let i = 0; i < 1800; i++) {
      const y = Math.random() * 0.98 + 0.02
      const a = Math.random() * Math.PI * 2
      const r = Math.sqrt(1 - y * y)
      starPos.push(Math.cos(a) * r * 1200, y * 1200, Math.sin(a) * r * 1200)
    }
    const starGeo = new THREE.BufferGeometry()
    starGeo.setAttribute("position", new THREE.Float32BufferAttribute(starPos, 3))
    this.stars = new THREE.Points(starGeo, new THREE.PointsMaterial({ color: 0xffffff, size: 1, sizeAttenuation: false, transparent: true, opacity: 0, fog: false, depthWrite: false }))
    this.stars.frustumCulled = false
    this.stars.renderOrder = -1
    this.scene.add(this.stars)
    const moonMat = new THREE.MeshBasicMaterial({ map: moonFace(), transparent: true, fog: false, depthWrite: false })
    moonMat.color.setRGB(2.2, 2.2, 2.3)
    this.moon = new THREE.Mesh(new THREE.CircleGeometry(30, 32), moonMat)
    this.moon.renderOrder = -1
    this.scene.add(this.moon)

    // the sun casts the shadows (also of what's cut away); the moon and the sky's fill don't
    this.sun.castShadow = true
    this.sun.shadow.mapSize.set(2048, 2048)
    const sc = this.sun.shadow.camera
    sc.left = -22
    sc.right = 22
    sc.top = 22
    sc.bottom = -22
    sc.near = 1
    sc.far = 200
    sc.layers.enable(1)
    this.sun.shadow.bias = -0.0004
    this.sun.shadow.normalBias = 0.03
    this.scene.add(this.sun, this.sun.target, this.moonLight, this.moonLight.target, this.fill)
    for (let i = 0; i < LAMPS; i++) {
      const lamp = new THREE.PointLight(0xffd29a, 0, 10, 2)
      this.pool.push(lamp)
      this.scene.add(lamp)
    }

    // the street and its places
    const lots: Lot[] = []
    const trees: Planting[] = []
    const leaves: [number, number][] = []
    for (const [place, side] of ROUTE) {
      const z = placeZ(place)
      const built = buildPlace(place)
      const group = built?.group ?? null
      const toWorld = (v: THREE.Vector3) => (group ? group.localToWorld(v.clone()) : v.clone())
      let room: THREE.Box2 | null = null
      if (built && group) {
        group.position.set(side * FRONT, 0, z)
        group.rotation.y = -side * (Math.PI / 2)
        group.updateMatrixWorld(true)
        this.scene.add(group)
        for (const s of built.sockets) this.sockets.push({ ...s, at: toWorld(s.at) })
        const paths: number[] = []
        for (const [x0, , x1, z1] of built.clear) if (z1 >= 2.5) paths.push(side * ((x0 + x1) / 2))
        lots.push({ z, side, w: built.size.w, d: built.size.d, paths })
        if (built.room) {
          const [x0, z0, x1, z1] = built.room
          const a = toWorld(V(x0, 0, z0))
          const b = toWorld(V(x1, 0, z1))
          room = new THREE.Box2(new THREE.Vector2(Math.min(a.x, b.x), Math.min(a.z, b.z)), new THREE.Vector2(Math.max(a.x, b.x), Math.max(a.z, b.z)))
        }
      }
      const inside = built?.door ? toWorld(built.door.inside) : null
      const outside = built?.door ? toWorld(built.door.outside) : null
      const front = outside ?? (built ? toWorld(built.scene(0, this.sample()).walk) : V(0, 0, z))
      // where they step off the curb, in front of its path (the trees along the curb leave the paths clear); the
      // street is crossed straight from one to the next
      const walkway = place === "start" ? V(-4.0, 0, 6) : place === "end" ? V(0.4, 0, z + 3) : V(side * 4.0, 0, front.z)
      this.sites.set(place, { place, side, built, group, street: walkway, inside, outside, room })
    }
    const end = placeZ("end")
    const town = street(40, end - 60, lots)
    this.scene.add(town.group)
    this.sockets.push(...town.sockets)
    trees.push(...town.trees)
    leaves.push(...town.leaves)
    // the park's big trees
    const park = this.sites.get("park")
    if (park?.group) {
      for (const [x, z, s] of [[-6, -4, 1.35], [5.5, -12.5, 1.5], [-6.5, -13, 1.2], [6.5, -3.5, 1.25], [0, -15.5, 1.4]] as const) {
        const at = park.group.localToWorld(V(x, 0, z))
        trees.push({ x: at.x, z: at.z, size: s })
        for (let k = 0; k < 40; k++) leaves.push([at.x + (Math.random() - 0.5) * 9, at.z + (Math.random() - 0.5) * 9])
      }
    }
    this.scene.add(forest(trees), fallen(leaves), woods([40, end - 60]))
    this.scene.add(this.hero.root, this.signs.group)
    this.hero.root.position.copy(this.pos)

    this.scene.traverse((o) => {
      const mesh = o as THREE.Mesh
      if (!mesh.isMesh) return
      for (const m of Array.isArray(mesh.material) ? mesh.material : [mesh.material]) {
        const std = m as THREE.MeshStandardMaterial
        if (std.userData?.night !== undefined && !this.glowing.includes(std)) this.glowing.push(std)
      }
    })

    // rendering: the scene small, its outlines, bloom on what's bright, then the film curve and the dither, scaled up
    const target = new THREE.WebGLRenderTarget(1, 1, { type: THREE.HalfFloatType, minFilter: THREE.NearestFilter, magFilter: THREE.NearestFilter })
    this.composer = new EffectComposer(this.renderer, target)
    this.composer.addPass(new Pixels(this.scene, this.camera))
    this.composer.addPass(new UnrealBloomPass(new THREE.Vector2(256, 256), 0.5, 0.45, 3.2))
    this.out = new PixelOut()
    this.composer.addPass(this.out)

    this.loop = this.loop.bind(this)
    this.raf = requestAnimationFrame(this.loop)
  }

  /** The drawing area's size in CSS pixels; the town is drawn about a third of that. */
  resize(w: number, h: number): void {
    this.size = { w: Math.max(1, w), h: Math.max(1, h) }
    const px = Math.max(2, Math.round(Math.min(this.size.h, this.size.w * 0.62) / 240))
    const low = [Math.max(1, Math.floor(this.size.w / px)), Math.max(1, Math.floor(this.size.h / px))]
    this.renderer.setSize(this.size.w, this.size.h, false)
    this.composer.setPixelRatio(1)
    this.composer.setSize(low[0], low[1])
    this.out.low.set(low[0], low[1])
    this.camera.aspect = this.size.w / this.size.h
    // at least about 50° across, so a tall, narrow window shows as much of the scene as a wide one
    const across = Math.tan(THREE.MathUtils.degToRad(25)) / this.camera.aspect
    this.camera.fov = Math.max(30, THREE.MathUtils.radToDeg(2 * Math.atan(across)))
    this.setShift(...this.shift)
  }

  /** Move the picture's middle left by `across` of the width (beside a box on the right), or up by `up` of the height
   * (above one along the bottom). */
  setShift(across: number, up = 0): void {
    this.shift = [across, up]
    const { w, h } = this.size
    if (across || up) this.camera.setViewOffset(w, h, w * across, h * up, w, h)
    else this.camera.clearViewOffset()
    this.camera.updateProjectionMatrix()
  }

  /** Go to a step's place (back through the week when going back), and show your answers there. */
  go(step: string, a: Answers, back = false): void {
    this.step = step
    this.answers = { ...a }
    this.show(a)
    const stop = STOPS[step] ?? STOPS.hello
    const act = this.actFor(stop.place, stop.spot, a)
    if (!act) return
    const minutes = stop.at(a)
    // out of bed first, if they're in one (getting in, past standing beside it), or still getting out
    let out: Script | null = null
    const running = this.trip?.out
    if (running && running.t < running.keys[running.keys.length - 1].at) out = running
    else if (this.script) {
      if (this.script.t >= 1.4 && act.site !== this.script.site) out = this.keysOut(this.script.bed, this.script.site)
    } else if (this.act?.bed && act.site !== this.act.site && !this.trip?.path) out = this.keysOut(this.act.bed, this.act.site)
    this.script = null
    const from = out ? out.keys[out.keys.length - 1].pos : this.pos
    const points = this.route(act, from)
    const path = points.length > 1 ? new THREE.CatmullRomCurve3(points, false, "centripetal", 0.5) : null
    const length = path ? path.getLength() : 0
    const walking = !!path && length > 0.25
    const cruise = walking ? paceFor(length) : 1
    const seated = !out && this.act && !this.act.bed && (this.act.seat !== undefined || SEATED[this.act.action] !== undefined) && this.weight > 0.3
    const ahead = walking && path ? Math.sign(path.getPointAt(1).z - path.getPointAt(0).z) || -1 : -1
    this.trip = {
      path: walking ? path : null,
      length: walking ? length : 0,
      clock: 0,
      fast: this.options.still ? 1000 : 1,
      rise: walking && seated ? 0.45 : 0,
      out,
      walk: walking ? length / cruise + (SPEED_UP + SLOW_DOWN) / 2 : 0,
      cruise,
      ahead,
      from: { minutes: this.minutes, cam: { pos: this.cam.pos.clone(), look: this.cam.look.clone() }, act: this.act },
      to: act,
      minutes,
      delta: timeStep(this.minutes, minutes, back),
    }
    if (!walking && !out) this.change(act)
  }

  /** The same place, something else to do: from one pose into the other. */
  private change(act: Act): void {
    if (this.act && this.act.action !== act.action) {
      this.before = this.act.action
      this.changed = 0
    }
    this.act = act
  }

  /** Answers changed where you are: the place shows them, they act the answer out, the sky follows the time the near
   * way round the clock, and what they do there follows what you chose. */
  update(a: Answers): void {
    this.show(a)
    const was = this.answers
    this.answers = { ...a }
    const now = (performance.now() - this.started) / 1000
    const reaction = was ? reactionTo(was, a) : null
    const settled = !this.trip && !this.script && this.act && this.act.action !== "sleep"
    if (reaction && settled) {
      this.hero.react(reaction.kind, now, reaction.aim ?? 0)
      const sign = SIGN_FOR[reaction.kind]
      if (sign) this.signs.emit(sign, this.hero.headAt().add(V(0.15, 0.05, 0)), now, 0.34)
      this.fidgetAt = now + 10
    }
    const stop = STOPS[this.step] ?? STOPS.hello
    const minutes = stop.at(a)
    const act = this.actFor(stop.place, stop.spot, a)
    if (this.trip) {
      this.trip.delta += shortest(minutes - this.trip.minutes)
      this.trip.minutes = minutes
      if (act) this.trip.to = act
      return
    }
    if (act && this.act && act.at.distanceTo(this.act.at) > 0.1) return this.go(this.step, a) // elsewhere in the same place now (the park: the blanket, or the bench)
    if (act && !this.script) this.change(act) // the same place, done another way (the TV or the laptop)
    else if (act && this.script) this.act = act
    const d = shortest(minutes - this.minutes)
    if (Math.abs(d) > 0.5 && this.act) {
      this.trip = { path: null, length: 0, clock: 0, fast: this.options.still ? 1000 : 1, rise: 0, out: null, walk: 0, cruise: 1, ahead: -1, from: { minutes: this.minutes, cam: { pos: this.cam.pos.clone(), look: this.cam.look.clone() }, act: this.act }, to: this.act, minutes, delta: d }
    }
  }

  /** Get there now (another Return while walking): the rest of the way four times as fast. */
  hurry(): void {
    if (this.trip) this.trip.fast = 4
    if (this.script) this.script.fast = 4
  }

  dispose(): void {
    cancelAnimationFrame(this.raf)
    this.env?.dispose()
    this.pmrem.dispose()
    this.composer.dispose()
    this.scene.traverse((o) => (o as THREE.Mesh).geometry?.dispose?.())
    this.renderer.dispose()
  }

  // ---- where things are --------------------------------------------------------------------------------------------

  private sample(): Answers {
    return { wake: "07:30", bedtime: "23:30", weekend_wake: "09:00", weekend_bedtime: "00:30", normal_hours: 6, most_hours: 9, focus_hours: 1.5, evening_free: 2, evening_from: "19:00", weekend_free: 4, finish_early_days: 1, brief: true, calendars: [] }
  }

  /** What's done at a place for a step, in the world. The start and the end are out on the street. */
  private actFor(place: Place, spot: number, a: Answers): Act | null {
    const site = this.sites.get(place)
    if (!site) return null
    if (place === "start") {
      const at = V(-5.9, 0.15, 6)
      const look = at.clone().add(V(0, 0.95, 0))
      return { site, walk: at, at, yaw: 0.55, action: "wave", cam: { look, pos: look.clone().add(V(2.8, 2.3, 7.2)) } }
    }
    if (place === "end") {
      const z = placeZ("end")
      const at = V(0.4, 0, z + 3)
      // down the middle of the road, clear of the trees: behind them, then rising over the town at dusk
      const cams = [
        { look: V(0.4, 1.1, z + 4), pos: V(0.9, 3.2, z - 6.5) },
        { look: V(0, 0, z + 30), pos: V(0.4, 17, z - 12) },
        { look: V(0, 0, z + 55), pos: V(0.4, 30, z - 22) },
      ]
      return { site, walk: at, at, yaw: Math.PI, action: "wave", cam: cams[Math.min(spot, 2)] }
    }
    if (!site.built || !site.group) return null
    const s: Scene = site.built.scene(spot, a)
    const group = site.group
    const w = (v: THREE.Vector3) => group.localToWorld(v.clone())
    const turned = (yaw: number) => yaw - site.side * (Math.PI / 2)
    const bed = s.bed && { ...s.bed, side: w(s.bed.side), edge: w(s.bed.edge), lie: w(s.bed.lie), up: w(s.bed.up), yawEdge: turned(s.bed.yawEdge), yawIn: turned(s.bed.yawIn) }
    return {
      site,
      walk: w(s.walk),
      at: w(s.at),
      yaw: turned(s.yaw),
      action: s.action,
      seat: s.seat,
      mood: s.mood,
      bed,
      cam: { pos: w(s.cam.pos), look: w(s.cam.look) },
      via: s.via?.map(w),
    }
  }

  /** Which place they're at: in its room or on its front path; null out on the street. */
  private siteAt(pos: THREE.Vector3): Site | null {
    for (const site of this.sites.values()) {
      if (!site.group || !site.built) continue
      const local = site.group.worldToLocal(pos.clone())
      if (local.z < FRONT - SIDEWALK[1] - 0.2 && local.z > -site.built.size.d - 1 && Math.abs(local.x) < site.built.size.w / 2 + 0.5) return site
    }
    return null
  }

  /** The way on foot from `from` to what's next: out this door, down the path, straight across the street, up the
   * other path, in that door. */
  private route(to: Act, from: THREE.Vector3): THREE.Vector3[] {
    const points = [from.clone()]
    const here = this.act?.site ?? this.siteAt(from)
    if (here && here === to.site) {
      // staying put (the library's three questions), or across the room
      if (!(this.act && this.act.at.distanceTo(to.at) < 0.1) && from.distanceTo(to.walk) > 0.2) points.push(to.walk.clone())
      return points
    }
    if (here) {
      if (this.act && !this.act.bed && this.act.walk.distanceTo(from) > 0.3) points.push(this.act.walk.clone())
      if (here.inside && here.room?.containsPoint(new THREE.Vector2(from.x, from.z))) points.push(here.inside.clone())
      if (here.outside) points.push(here.outside.clone())
      points.push(here.street.clone())
    } else if (Math.abs(from.x) > 3) points.push(V(Math.sign(from.x) * 4.0, 0, from.z))
    points.push(to.site.street.clone())
    if (to.site.outside && to.site.inside) points.push(to.site.outside.clone(), to.site.inside.clone())
    for (const v of to.via ?? []) points.push(v.clone())
    points.push(to.walk.clone())
    return points.filter((p, i) => i === 0 || p.distanceTo(points[i - 1]) > 0.35)
  }

  private show(a: Answers): void {
    for (const site of this.sites.values()) site.built?.show(a)
  }

  /** The floor under a point: a room's, the road's, or the ground's. */
  private groundAt(x: number, z: number): number {
    for (const site of this.sites.values()) if (site.room?.containsPoint(new THREE.Vector2(x, z))) return FLOOR
    return Math.abs(x) < 3.5 ? 0 : 0.15
  }

  // ---- in and out of bed ---------------------------------------------------------------------------------------------

  /** Into bed: up to it, the covers thrown back, sitting on its edge, legs up and round, lying back, the covers pulled
   * up; when it's the alarm's scene, asleep a moment, the alarm, and sitting up with the covers at the waist. */
  private keysIn(bed: BedHere, site: Site, wake: boolean): Script {
    const top = bed.top
    const face = bed.yawEdge + Math.PI
    const rest = BED.lie(top)
    const asleep = { ...BED.lie(top), eyes: 0 }
    const keys: Key[] = [
      { at: 0, pose: this.hero.posed(), pos: this.pos.clone(), yaw: this.yaw, fold: bed.duvet.fold, full: bed.duvet.full },
      { at: 0.4, pose: BED.stand(), pos: bed.side, yaw: face, fold: bed.duvet.fold, full: 0 },
      { at: 1.0, pose: BED.reach(), pos: bed.side, yaw: face, fold: bed.open, full: 0 },
      { at: 1.5, pose: BED.stand(), pos: bed.side, yaw: bed.yawEdge, fold: bed.open, full: 0 },
      { at: 2.0, pose: BED.edge(top), pos: bed.edge, yaw: bed.yawEdge, fold: bed.open, full: 0 },
      { at: 2.45, pose: BED.lift(top), pos: bed.edge, yaw: bed.yawEdge, fold: bed.open, full: 0 },
      { at: 3.35, pose: BED.lie(top), pos: bed.lie, yaw: bed.yawIn, fold: bed.open, full: 0.15 },
      { at: 4.0, pose: BED.tuck(top), pos: bed.lie, yaw: bed.yawIn, fold: bed.closed, full: 1 },
      { at: 4.5, pose: wake ? rest : asleep, pos: bed.lie, yaw: bed.yawIn, fold: bed.closed, full: 1 },
    ]
    if (wake) {
      keys.push({ at: 5.0, pose: asleep, pos: bed.lie, yaw: bed.yawIn, fold: bed.closed, full: 1 })
      keys.push({ at: 6.1, pose: asleep, pos: bed.lie, yaw: bed.yawIn, fold: bed.closed, full: 1, cue: "alarm" })
      keys.push({ at: 6.6, pose: { ...asleep, eyes: 1, headY: 0.35 }, pos: bed.lie, yaw: bed.yawIn, fold: bed.closed, full: 1 })
      keys.push({ at: 7.6, pose: BED.up(top), pos: bed.up, yaw: bed.yawIn, fold: bed.waist, full: 0.45 })
    }
    return { keys, t: 0, bed, site, cued: new Set(), fast: 1 }
  }

  /** Out of bed: sitting up with the covers thrown back, legs swung round over the edge (above the mattress, not
   * through it), feet down, standing. */
  private keysOut(bed: BedHere, site: Site): Script {
    const top = bed.top
    const keys: Key[] = [
      { at: 0, pose: this.hero.posed(), pos: this.pos.clone(), yaw: this.yaw, fold: bed.duvet.fold, full: bed.duvet.full },
      { at: 0.5, pose: BED.up(top), pos: bed.up, yaw: bed.yawIn, fold: bed.open, full: 0.3 },
      { at: 1.1, pose: BED.lift(top), pos: bed.edge, yaw: bed.yawEdge, fold: bed.open, full: 0.35 },
      { at: 1.45, pose: BED.edge(top), pos: bed.edge, yaw: bed.yawEdge, fold: bed.open, full: 0 },
      { at: 1.85, pose: BED.stand(), pos: bed.side, yaw: bed.yawEdge, fold: bed.open, full: 0 },
    ]
    return { keys, t: 0, bed, site, cued: new Set(), fast: 1 }
  }

  /** Where a scene has them at its time: the pose, place, heading and duvet between its keys; true when it's over. */
  private play(script: Script, seconds: number): { pose: Pose; done: boolean } {
    const keys = script.keys
    const last = keys[keys.length - 1]
    const t = Math.min(script.t, last.at)
    let i = 0
    while (i < keys.length - 2 && keys[i + 1].at <= t) i++
    const a = keys[i]
    const b = keys[i + 1] ?? a
    const k = b.at > a.at ? ease((t - a.at) / (b.at - a.at)) : 1
    for (const key of keys) {
      if (key.cue && script.t >= key.at && !script.cued.has(key.cue)) {
        script.cued.add(key.cue)
        script.site.built?.cue?.(key.cue, seconds)
        if (key.cue === "alarm") this.signs.emit("!", this.hero.headAt().add(V(0.1, 0.1, 0)), seconds, 0.4)
      }
    }
    this.pos.lerpVectors(a.pos, b.pos, k).setY(0)
    this.yaw = turn(a.yaw, b.yaw, k)
    script.bed.duvet.set(a.fold + (b.fold - a.fold) * k, a.full + (b.full - a.full) * k)
    return { pose: mixPose(a.pose, b.pose, k), done: script.t >= last.at }
  }

  // ---- each frame ----------------------------------------------------------------------------------------------------

  private loop(time: number): void {
    this.raf = requestAnimationFrame(this.loop)
    const dt = Math.min(0.05, (time - this.last) / 1000)
    this.last = time
    const seconds = (time - this.started) / 1000
    const trip = this.trip
    let walking = false
    let follow: { pos: THREE.Vector3; look: THREE.Vector3 } | null = null
    let scripted: Pose | null = null
    let centred = false
    if (trip) {
      const step = dt * trip.fast
      // first out of bed, or up off a seat
      if (trip.out && trip.out.t < trip.out.keys[trip.out.keys.length - 1].at) {
        trip.out.t += step
        scripted = this.play(trip.out, seconds).pose
        follow = trip.from.cam
      } else {
        trip.clock += step
        const going = trip.rise + trip.walk
        this.minutes = trip.from.minutes + trip.delta * ease(going ? trip.clock / going : trip.clock / 1.1)
        if (trip.clock < trip.rise) {
          this.weight = Math.max(0, this.weight - step / trip.rise)
          follow = trip.from.cam
        } else if (trip.path && trip.clock - trip.rise < trip.walk) {
          walking = true
          centred = true
          this.act = null
          this.weight = 0
          const t = trip.clock - trip.rise
          const s = along(t, trip.length, trip.cruise)
          const at = trip.path.getPointAt(Math.min(1, s / trip.length))
          this.speed = dt > 0 ? Math.max(0, (s - along(t - step, trip.length, trip.cruise)) / dt) : 0
          const toward = trip.path.getTangentAt(Math.min(1, s / trip.length + 0.02))
          this.pos.set(at.x, 0, at.z)
          this.yaw = turn(this.yaw, Math.atan2(toward.x, toward.z), 1 - Math.pow(0.0003, dt))
          // the camera keeps them in the middle of the picture: from the last scene's place, to ahead of them over the
          // street looking back as they come, to the next scene's place
          // swinging round them (never over their head), on the street's side of them
          const p = s / trip.length
          const look = V(this.pos.x, this.ground + 0.9, this.pos.z)
          const lead = V(Math.max(-2.5, Math.min(2.5, this.pos.x * 0.5)), this.ground + 4.6, this.pos.z + trip.ahead * 7)
          const pos = orbit(look, orbit(look, trip.from.cam.pos, lead, smooth(0, 0.3, p)), trip.to.cam.pos, smooth(0.62, 1, p))
          follow = { pos, look: look.lerp(trip.to.cam.look, smooth(0.8, 1, p)) }
        } else if (trip.clock - trip.rise >= (trip.path ? trip.walk : 1.1)) {
          // there: into bed, or into what they came to do
          this.trip = null
          this.minutes = trip.minutes
          this.speed = 0
          if (trip.to.bed && (!this.act || this.act.site !== trip.to.site || trip.path)) {
            this.act = trip.to
            this.script = this.keysIn(trip.to.bed, trip.to.site, trip.to.action === "wake")
          } else if (this.act !== trip.to) this.change(trip.to)
        }
      }
    }
    // a scene moving them by hand: into bed
    if (this.script) {
      this.script.t += dt * (this.options.still ? 1000 : this.script.fast)
      const played = this.play(this.script, seconds)
      scripted = played.pose
      follow = this.act?.cam ?? follow
      if (played.done) {
        this.release = { pose: played.pose, t: 0 }
        this.script = null
        this.weight = 1
        this.fidgetAt = seconds + 8
      }
    }
    // doing what they came for: into place, then the action
    if (!walking && !scripted && this.act && (!this.trip || this.trip.clock >= this.trip.rise)) {
      this.speed = 0
      this.weight = Math.min(1, this.weight + dt * 2.2)
      const k = 1 - Math.pow(0.004, dt)
      this.pos.lerp(V(this.act.at.x, 0, this.act.at.z), k)
      this.yaw = turn(this.yaw, this.act.yaw, k)
      follow ??= this.act.cam
    }
    follow ??= { pos: this.cam.pos, look: this.cam.look }
    // their feet on the floor they're over
    const floor = this.act && this.weight > 0.5 && !this.act.bed ? this.act.at.y : this.groundAt(this.pos.x, this.pos.z)
    this.ground += (floor - this.ground) * Math.min(1, dt * 12)
    this.hero.root.position.set(this.pos.x, this.ground, this.pos.z)
    this.hero.root.rotation.y = this.yaw
    // now and then, while you decide, they do something small: look up at you, scratch their head, yawn
    const settled = !this.trip && !this.script && this.act && this.weight > 0.95
    if (settled && this.act && seconds > this.fidgetAt && !this.hero.busy(seconds) && !this.options.still) {
      const choices = FIDGETS[this.act.action] ?? []
      if (choices.length) this.hero.react(choices[Math.floor(Math.random() * choices.length)], seconds)
      this.fidgetAt = seconds + 10 + Math.random() * 6
    }
    // the timer for a sitting rings: they stretch
    if (settled && this.step === "focus" && this.answers) {
      const ring = Math.floor(seconds / sittingFor(this.answers.focus_hours))
      if (ring !== this.rings) {
        if (this.rings >= 0) {
          this.hero.react("deskStretch", seconds)
          this.signs.emit("!", this.hero.headAt().add(V(0.25, -0.3, 0.2)), seconds, 0.32)
        }
        this.rings = ring
      }
    } else this.rings = -1
    const action = this.act?.action ?? "stand"
    this.changed = Math.min(1, this.changed + dt * 1.6)
    const toYou = Math.atan2(this.camera.position.x - this.pos.x, this.camera.position.z - this.pos.z)
    const look = Math.max(-1.0, Math.min(1.0, turn(0, toYou - this.yaw, 1)))
    let from: Pose | undefined
    let into = 1
    if (this.release) {
      this.release.t += dt
      from = this.release.pose
      into = ease(this.release.t / 0.6)
      if (this.release.t >= 0.6) this.release = null
    }
    this.hero.update(dt, seconds, { speed: walking ? this.speed : 0, action, weight: this.act ? this.weight : 0, seat: this.act?.seat ?? SEATED[action], before: this.changed < 1 ? (this.before ?? undefined) : undefined, change: this.changed, mood: this.act?.mood ?? {}, look, pose: scripted ?? undefined, from, into })
    this.signs.every(action, this.act && !this.script && !this.trip ? this.weight : 0, this.hero.headAt(), seconds)
    this.signs.update(seconds, dt)
    // the camera eases after where it should be; walking, it keeps them dead centre
    this.chase(follow, dt, centred)
    this.camera.position.copy(this.cam.pos)
    this.camera.lookAt(this.cam.look)
    this.camera.updateMatrixWorld()
    this.cut()
    this.light(lightAt(this.minutes), time)
    for (const site of this.sites.values()) site.built?.tick?.(seconds, this.minutes, this.step)
    this.composer.render(dt)
    this.measure(time)
  }

  private chase(to: { pos: THREE.Vector3; look: THREE.Vector3 }, dt: number, centred: boolean): void {
    const c = this.cam
    if (this.options.still || !this.ready) {
      c.pos.copy(to.pos)
      c.look.copy(to.look)
      return
    }
    const spring = (x: THREE.Vector3, v: THREE.Vector3, target: THREE.Vector3, w: number) => {
      const accel = target.clone().sub(x).multiplyScalar(w * w).addScaledVector(v, -2 * w)
      v.addScaledVector(accel, dt)
      x.addScaledVector(v, dt)
    }
    if (centred) {
      // walking, the camera is where the walk puts it, already smooth (it eases with their pace), and on them exactly
      c.pos.copy(to.pos)
      c.look.copy(to.look)
      c.vPos.set(0, 0, 0)
      c.vLook.set(0, 0, 0)
      return
    }
    spring(c.pos, c.vPos, to.pos, 4.5)
    spring(c.look, c.vLook, to.look, 5.5)
  }

  /** Cut away the front of the house they're in (or going into), so you can see in. What's cut still casts shadows. */
  private cut(): void {
    // cut away while they're anywhere in it or on its front path, and while they're headed into it
    const near = this.siteAt(this.pos)
    const going = this.trip && this.trip.to.site.built?.cut && this.trip.clock - this.trip.rise > this.trip.walk * 0.55 ? this.trip.to.site : null
    const target = near?.built?.cut ? near : going
    if (target === this.cutaway) return
    for (const site of [this.cutaway, target]) {
      if (!site?.built?.cut) continue
      const on = site === target
      site.built.cut.traverse((o) => o.layers.set(on ? 1 : 0))
      if (site.built.stub) site.built.stub.visible = on
    }
    this.cutaway = target
  }

  private light(l: Light, time: number): void {
    const sunDir = V(...l.sun)
    const u = this.skyMat.uniforms
    u.sunPosition.value.copy(sunDir)
    u.turbidity.value = l.air.turbidity
    u.rayleigh.value = l.air.rayleigh
    u.mieCoefficient.value = l.air.mie
    u.mieDirectionalG.value = l.air.mieG
    ;(u.uGlow.value as THREE.Vector3).set(...l.glow)
    this.sky.position.copy(this.camera.position)
    this.stars.position.copy(this.camera.position)
    ;(this.stars.material as THREE.PointsMaterial).opacity = Math.pow(1 - l.day, 2) * 0.9
    const moonDir = V(...l.moon)
    this.moon.position.copy(this.camera.position).addScaledVector(moonDir, 1150)
    this.moon.lookAt(this.camera.position)
    this.moon.visible = moonDir.y > -0.03
    ;(this.moon.material as THREE.MeshBasicMaterial).opacity = 0.3 + 0.7 * (1 - l.day)
    if (!this.env || (sunDir.angleTo(this.envSun) > 0.012 && time - this.envAt > 120)) {
      this.envSun.copy(sunDir)
      this.envAt = time
      this.env?.dispose()
      this.env = this.pmrem.fromScene(this.envScene, 0, 1, 2000)
      this.scene.environment = this.env.texture
      const haze = hazeColor(l)
      this.fog.color.setRGB(haze[0], haze[1], haze[2], THREE.LinearSRGBColorSpace)
    }
    this.fog.density = l.haze * 0.8
    // the sun's shadows follow them, snapped so they don't shimmer
    const focus = V(Math.round(this.pos.x * 2) / 2, 0, Math.round(this.pos.z * 2) / 2)
    this.sun.target.position.copy(focus)
    this.sun.position.copy(focus).addScaledVector(sunDir, 90)
    this.sun.color.setHex(l.sunColor)
    this.sun.intensity = l.sunLevel
    this.moonLight.target.position.copy(focus)
    this.moonLight.position.copy(focus).addScaledVector(moonDir, 90)
    this.moonLight.intensity = l.moonLevel * 1.6
    this.fill.color.setHex(l.skyFill)
    this.fill.groundColor.setHex(l.groundFill)
    this.fill.intensity = 0.25 + l.fillLevel * 0.6
    for (const mat of this.glowing) mat.emissiveIntensity = l.lamps * (mat.userData.night as number)
    this.renderer.toneMappingExposure = l.exposure * 0.95
    this.lamps(l)
  }

  /** The nearest lamps that are on get the real lights. */
  private lamps(l: Light): void {
    const at = this.pos
    const lit = this.sockets
      .map((s) => ({ s, level: s.night ? l.lamps : 1 }))
      .filter((x) => x.level > 0.02 && x.s.at.distanceTo(at) < x.s.range + 16)
      .sort((a, b) => a.s.at.distanceToSquared(at) - b.s.at.distanceToSquared(at))
      .slice(0, LAMPS)
    this.pool.forEach((lamp, i) => {
      const x = lit[i]
      if (!x) {
        lamp.intensity = 0
        return
      }
      lamp.position.copy(x.s.at)
      lamp.color.setHex(x.s.color)
      lamp.distance = x.s.range
      lamp.intensity = x.s.power * x.level
    })
  }

  private measure(time: number): void {
    this.frames.push(time)
    if (this.frames.length > 90) this.frames.shift()
    if (!this.ready && this.frames.length > 3) {
      this.ready = true
      this.options.onReady?.()
    }
  }
}

/** Turn from one heading toward another the short way round, `k` of the way. */
function turn(from: number, to: number, k: number): number {
  let d = (to - from) % (Math.PI * 2)
  if (d > Math.PI) d -= Math.PI * 2
  if (d < -Math.PI) d += Math.PI * 2
  return from + d * Math.min(1, k)
}

/** A camera position `t` of the way from `a` to `b`, swung round `centre` at a height and distance between theirs,
 * the way round that passes the street's side of it (toward x = 0), not the buildings'. */
function orbit(centre: THREE.Vector3, a: THREE.Vector3, b: THREE.Vector3, t: number): THREE.Vector3 {
  if (t <= 0) return a.clone()
  if (t >= 1) return b.clone()
  const polar = (v: THREE.Vector3) => {
    const o = v.clone().sub(centre)
    const flat = Math.hypot(o.x, o.z)
    return { yaw: Math.atan2(o.x, o.z), up: o.y, flat: Math.max(0.01, flat) }
  }
  const pa = polar(a)
  const pb = polar(b)
  let d = (pb.yaw - pa.yaw) % (Math.PI * 2)
  if (d > Math.PI) d -= Math.PI * 2
  if (d < -Math.PI) d += Math.PI * 2
  const road = -Math.sign(centre.x)
  if (road && Math.abs(d) > 0.6) {
    // of the two ways round, the one whose middle is over the street
    const other = d - Math.sign(d) * Math.PI * 2
    const side = (delta: number) => Math.sin(pa.yaw + delta / 2) * road
    if (side(other) > side(d)) d = other
  }
  const yaw = pa.yaw + d * t
  const flat = pa.flat + (pb.flat - pa.flat) * t
  const up = pa.up + (pb.up - pa.up) * t
  return new THREE.Vector3(centre.x + Math.sin(yaw) * flat, centre.y + up, centre.z + Math.cos(yaw) * flat)
}
