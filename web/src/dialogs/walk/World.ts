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
import { UnrealBloomPass } from "three/examples/jsm/postprocessing/UnrealBloomPass.js"
import type { Schemas } from "@/api/client"
import { type Action, BED, Character, type Mood, type Pose, poseFrom, poseNumbers, type Reaction, SEATED, Signs } from "./character"
import { fallen, forest, type Planting, woods } from "./nature"
import { PixelOut, Pixels } from "./pixels"
import { type Built, buildPlace, type Duvet, type Extra, FLOOR, FRONT, type Scene, SIDEWALK, type Socket, sittingFor } from "./places"
import { SEASON, snows } from "./season"
import { hazeColor, type Light, lightAt, timeStep, useDaylight } from "./sky"
import { Snowfall } from "./snow"
import { type Place, placeZ, ROUTE, STOPS } from "./stops"
import { moonFace } from "./textures"
import { type Lot, type Post, street } from "./town"

type Answers = Schemas["SetupInput"]

const LAMPS = 6 // lights moved to wherever you are
const V = (x: number, y: number, z: number) => new THREE.Vector3(x, y, z)

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
  front?: THREE.Vector3 // seated: where they stand before sitting down (and stand up to), in front of the seat
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
  stand: [THREE.Vector3, THREE.Vector3] | null // from the seat to in front of it, while standing up
  out: Script | null // or getting out of bed
  walk: number // seconds walking (0: staying where they are)
  glide: number // staying where they are: seconds the camera takes to its new place (longer the further it goes)
  cruise: number // metres a second, once going
  wipe: Wipe | null // to another place: a few steps out while the iris closes, then in at the next as it opens
  fixed: boolean // stepping in after the wipe: the camera already where it'll be, on them
  from: { minutes: number; cam: { pos: THREE.Vector3; look: THREE.Vector3 }; act: Act | null }
  to: Act
  minutes: number
  delta: number
}

/** The way between places (30 Oct: "the walking as a transition takes too long - please come up with a new way"):
 * instead of the whole way up the street, a few steps toward the door while an iris closes on them, as a game moves
 * between scenes, then it opens on them stepping in at the next place. About two seconds instead of five or six. */
interface Wipe {
  exit: THREE.CatmullRomCurve3 | null // the way out, of which they walk the first steps
  exitLength: number
  enter: THREE.Vector3[] // the way in, from the next place's door to the spot
  jumped: boolean
}

const EXIT = 0.95 // seconds stepping out while the iris closes
const HOLD = 0.12 // shut
const OPEN = 0.6 // opening
const ENTER = 1.8 // metres walked in after the wipe
const EXIT_PACE = 1.9 // metres a second, stepping out
const ENTER_PACE = 2.2 // and stepping in

const SPEED_UP = 0.4 // seconds getting going
const SLOW_DOWN = 0.5 // and stopping

/** How far along a walk of `length` metres they are `t` seconds in: speeding up to `cruise`, steady, slowing down. */
export function along(t: number, length: number, cruise: number, rolling = false): number {
  const up = rolling ? 0 : SPEED_UP // already walking (in after the wipe): no getting going
  const total = length / cruise + (up + SLOW_DOWN) / 2
  if (t <= 0) return 0
  if (t >= total) return length
  if (t < up) return 0.5 * (cruise / up) * t * t
  if (t > total - SLOW_DOWN) {
    const left = total - t
    return length - 0.5 * (cruise / SLOW_DOWN) * left * left
  }
  return 0.5 * cruise * up + cruise * (t - up)
}

/** A walk's pace (30 Oct: "make the walking animations faster - like make it walk less"): a few steps across a
 * room, a jog over the street; about three seconds at most. */
export function paceFor(length: number): number {
  const cruise = Math.max(2.4, Math.min(7.5, length / 2.6))
  return Math.min(cruise, length / ((SPEED_UP + SLOW_DOWN) / 2) - 0.001)
}

/** The nearest way round the clock from one time to another, in minutes (30 Oct: changing bedtime from 12am to
 * 11:30pm went the long way, through a whole day, and the sky flashed white). */
export function shortest(d: number): number {
  return ((((d + 720) % 1440) + 1440) % 1440) - 720
}

/** What they do when an answer changes, where it's asked, and only what it means (30 Oct: "why do the arms randomly
 * go up when you click - that's a bad reaction because it doesn't mean anything"): a look at the alarm clock when the
 * alarm moves, a book onto the day's pile (or off it), one onto the heavy day's, the timer turned, the note moved
 * along the week. Answers shown some other way (the TV or the laptop, the blanket or the bench, the paper or the
 * phone) need nothing more. Whether you're in school: a nod at the desk's things, swapped (places.ts dorm). `aim` is
 * which way: along the board, or toward the clock. */
export function reactionTo(was: Answers, now: Answers): { kind: Reaction; aim?: number } | null {
  if (now.school !== was.school) return { kind: "nod" } // a nod at what's by the desk now (C97)
  if (now.wake !== was.wake) return { kind: "clock", aim: -1 }
  if (now.normal_hours !== was.normal_hours) return { kind: "stackRight" }
  if (now.most_hours !== was.most_hours) return { kind: "stackLeft" }
  if (now.focus_hours !== was.focus_hours) return { kind: "timer" }
  if (now.finish_early_days !== was.finish_early_days) {
    const day = 4 - Math.max(0, Math.min(4, now.finish_early_days))
    return { kind: "pin", aim: (-0.448 + day * 0.224) / 0.45 }
  }
  return null
}

/** What they do now and then while you decide: a glance up at you, not often. */
const FIDGETS: Partial<Record<Action, Reaction[]>> = {
  stand: ["glance"],
  wave: ["glance"],
  study: ["glance"],
  read: ["glance"],
  tv: ["glance"],
  laptop: ["glance"],
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
  private snow: Snowfall | null = snows(SEASON) ? new Snowfall() : null // the season outside (walk/season.ts)
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
  private extra: Extra = { ai: null, reading: false }
  private fidgetAt = 6 // seconds: when they next do something while you decide
  private rings = -1 // the focus timer's rings so far
  private ringsFor = -1 // for which length of sitting
  private ringsFrom = 0 // since when (seconds)
  private covered: Duvet | null = null // the covers over them now
  private forceEnv = false // the sky's light refreshed on the next frame (after a wipe)
  private mailing = 0 // when the letter's in hand, to turn and read it
  private posted = false // a letter came while they were on their way to the boxes
  private mailUntil = 0 // reading it till then
  private iris = 1 // the wipe: 1 open, 0 shut
  private lockOn = 0 // how much the camera's on them exactly (walking), eased so it never snaps
  private view = V(0, 1, 0) // where the camera looks this frame
  posts: Post[] = [] // trunks, lamps, poles and hydrants (walk/audit.ts checks them)
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
    useDaylight(SEASON) // winter's short, low days; summer's long ones
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
      const front = outside ?? (built ? toWorld(built.scene(0, this.sample(), this.extra).walk) : V(0, 0, z))
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
    if (this.snow) this.scene.add(this.snow.points)
    this.posts = [...town.posts, ...trees.map((t) => ({ x: t.x, z: t.z, r: 0.12 + 0.2 * t.size, h: 3 }))]
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

    // every material compiled now, so the first sight of something (a room, the laptop) never holds a frame
    this.renderer.compile(this.scene, this.camera)

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
    if (step !== this.step) this.posted = false
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
      if (this.script.t >= 1.4 && (act.site !== this.script.site || !act.bed)) out = this.keysOut(this.script.bed, this.script.site)
    } else if (this.act?.bed && (act.site !== this.act.site || !act.bed) && !this.trip?.path) out = this.keysOut(this.act.bed, this.act.site)
    // (11 Nov: from bed to the desk in the same room they walked out through the mattress: out of bed first there too)
    this.script = null
    const seated = !out && this.act && !this.act.bed && this.act.front && this.weight > 0.3 ? this.act : null
    const from = out ? out.keys[out.keys.length - 1].pos : seated?.front ? seated.front : this.pos
    const points = this.route(act, from)
    const curve = points.length > 1 ? new THREE.CatmullRomCurve3(points, false, "centripetal", 0.5) : null
    // to another place: the wipe; within this one, the few steps across it
    const here = this.trip?.wipe?.jumped ? this.trip.to.site : (this.act?.site ?? this.siteAt(from) ?? (this.trip ? this.trip.from.act?.site : null))
    const crossing = here !== act.site
    const wipe: Wipe | null = crossing ? { exit: curve, exitLength: curve?.getLength() ?? 0, enter: this.entry(act), jumped: false } : null
    if (out && crossing) out.fast = 1.4 // getting out of bed a little briskly on the way somewhere
    const path = crossing ? null : curve
    const length = path ? path.getLength() : 0
    const walking = !!path && length > 0.25
    this.trip = {
      path: walking ? path : null,
      length: walking ? length : 0,
      clock: 0,
      fast: this.options.still ? 1000 : 1,
      rise: (walking || crossing) && seated ? 0.55 : 0,
      stand: (walking || crossing) && seated?.front ? [this.pos.clone(), seated.front.clone()] : null,
      out,
      walk: walking ? length / paceFor(length) + (SPEED_UP + SLOW_DOWN) / 2 : 0,
      glide: Math.max(1.1, Math.min(4, this.cam.pos.distanceTo(act.cam.pos) / 6)),
      cruise: walking ? paceFor(length) : 1,
      wipe,
      fixed: false,
      from: { minutes: this.minutes, cam: { pos: this.cam.pos.clone(), look: this.cam.look.clone() }, act: this.act },
      to: act,
      minutes,
      delta: timeStep(this.minutes, minutes, back),
    }
    if (!walking && !out && !crossing) this.change(act)
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
      this.trip = { path: null, length: 0, clock: 0, fast: this.options.still ? 1000 : 1, rise: 0, stand: null, out: null, walk: 0, glide: 1.1, wipe: null, fixed: false, cruise: 1, from: { minutes: this.minutes, cam: { pos: this.cam.pos.clone(), look: this.cam.look.clone() }, act: this.act }, to: this.act, minutes, delta: d }
    }
  }

  /** What setup knows besides the answers: the AI you chose (on the post office's screen), and whether something
   * you brought in is being read (they take a letter from a box and read it). */
  setExtra(extra: Extra): void {
    const was = this.extra
    this.extra = { ...extra }
    for (const site of this.sites.values()) site.built?.extra?.(extra)
    const now = (performance.now() - this.started) / 1000
    // something brought in (an upload, a calendar, an account), or something being read: a letter in their box
    // (30 Oct: "make him interact with the cabinet when anything gets uploaded/connected"); one that comes while
    // they're still on their way waits for them to get there
    const more = (extra.brought ?? 0) > (was.brought ?? 0) && was.brought !== undefined
    const post = this.step === "bring" && (more || (extra.reading && !was.reading))
    if (this.trip || this.script || !this.act) {
      if (post) this.posted = true
      return
    }
    if (extra.ai?.provider !== was.ai?.provider && was.ai && this.step === "ai") this.hero.react("typing", now)
    if (post) this.letter(now)
    else if (this.step === "bring" && !extra.reading && was.reading && now > this.mailUntil) this.mailDone()
  }

  /** A letter in their box: the box opens, they reach in and take it, turn, and read it a while. */
  private letter(now: number): void {
    if (this.mailing > 0) return // reaching in for one already
    this.hero.react("fetch", now)
    this.act?.site.built?.cue?.("open", now)
    this.mailing = now + 1.45
  }

  /** Read it: back to the boxes. */
  private mailDone(): void {
    this.mailUntil = 0
    const stop = STOPS[this.step]
    const act = this.answers && this.actFor(stop.place, stop.spot, this.answers)
    if (act) this.change(act)
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
    // the town's materials and their pictures too, and the GL context given back: a setup opened again (Settings →
    // Fit Friday to your week again) starts a fresh one, and browsers keep only a handful at a time
    const textures = new Set<THREE.Texture>()
    this.scene.traverse((o) => {
      const mesh = o as THREE.Mesh
      mesh.geometry?.dispose?.()
      for (const m of ([] as THREE.Material[]).concat(mesh.material ?? [])) {
        for (const v of Object.values(m)) if (v instanceof THREE.Texture) textures.add(v)
        m.dispose()
      }
    })
    for (const t of textures) t.dispose()
    this.renderer.dispose()
    this.renderer.forceContextLoss()
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
      // down the middle of the road behind them, then up over the treetops (never in among them) looking back over
      // the town at dusk
      const cams = [
        { look: V(0.4, 1.1, z + 4), pos: V(0.9, 3.2, z - 6.5) },
        { look: V(0, 4, z + 55), pos: V(0, 32, z - 26) },
        { look: V(0, 4, z + 80), pos: V(0, 48, z - 40) },
      ]
      return { site, walk: at, at, yaw: Math.PI, action: "wave", cam: cams[Math.min(spot, 2)] }
    }
    if (!site.built || !site.group) return null
    const seconds = (performance.now() - this.started) / 1000
    const s: Scene = site.built.scene(spot, a, { ...this.extra, reading: this.extra.reading || seconds < this.mailUntil })
    const group = site.group
    const w = (v: THREE.Vector3) => group.localToWorld(v.clone())
    const turned = (yaw: number) => yaw - site.side * (Math.PI / 2)
    const bed = s.bed && { ...s.bed, side: w(s.bed.side), edge: w(s.bed.edge), lie: w(s.bed.lie), up: w(s.bed.up), yawEdge: turned(s.bed.yawEdge), yawIn: turned(s.bed.yawIn) }
    const yaw = turned(s.yaw)
    const at = w(s.at)
    // sitting: they stand in front of the seat, turned round, and sit back onto it (and stand up to there)
    const seated = !bed && (s.seat !== undefined || SEATED[s.action] !== undefined)
    const front = !seated ? undefined : s.front instanceof THREE.Vector3 ? w(s.front) : at.clone().add(V(Math.sin(yaw), 0, Math.cos(yaw)).multiplyScalar(s.front ?? 0.36))
    return {
      site,
      walk: w(s.walk),
      at,
      yaw,
      action: s.action,
      seat: s.seat,
      front,
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

  /** The way in at a place after the wipe: the last couple of steps of the way from its door (or the curb, or along
   * the road at the start and the end) round the furniture to the spot, or to in front of the seat. Only the last of
   * it, so the iris opens on them nearly there, never passing under the camera by the door. */
  private entry(to: Act): THREE.Vector3[] {
    const place = to.site.place
    const start = to.site.inside?.clone() ?? (place === "start" ? to.walk.clone().add(V(0.6, 0, -2.6)) : place === "end" ? to.walk.clone().add(V(0, 0, 2.8)) : to.site.street.clone())
    const points = [start, ...(to.via ?? []).map((v) => v.clone()), to.walk.clone()]
    if (to.front) points.push(to.front.clone())
    const way = points.filter((p, i) => i === 0 || p.distanceTo(points[i - 1]) > 0.3)
    if (way.length < 2) return way
    const curve = new THREE.CatmullRomCurve3(way, false, "centripetal", 0.5)
    const length = curve.getLength()
    let from = Math.max(0, (length - ENTER) / length)
    // and far enough from the camera that the iris doesn't open on the back of their head
    const head = (u: number) => curve.getPointAt(u).add(V(0, 1.5, 0))
    while (from < 0.85 && head(from).distanceTo(to.cam.pos) < 2.6) from += 0.05
    if (from === 0) return way
    return Array.from({ length: 6 }, (_, i) => curve.getPointAt(from + ((1 - from) * i) / 5))
  }

  /** The iris shut: they're at the next place, at its door, the camera where its scene has it. */
  private jump(trip: Trip): void {
    const w = trip.wipe as Wipe
    w.jumped = true
    this.hero.cut() // a new shot: in whatever pose it opens on at once, not swung into it on screen
    const points = w.enter
    const path = points.length > 1 ? new THREE.CatmullRomCurve3(points, false, "centripetal", 0.5) : null
    const length = path?.getLength() ?? 0
    this.pos.set(points[0].x, 0, points[0].z)
    if (points.length > 1) this.yaw = Math.atan2(points[1].x - points[0].x, points[1].z - points[0].z)
    this.ground = this.groundAt(this.pos.x, this.pos.z)
    this.minutes = trip.minutes
    this.forceEnv = true
    this.act = null
    this.weight = 0
    trip.from = { minutes: trip.minutes, cam: { pos: trip.to.cam.pos.clone(), look: trip.to.cam.look.clone() }, act: null }
    trip.delta = 0
    trip.path = length > 0.25 ? path : null
    trip.length = trip.path ? length : 0
    trip.cruise = Math.min(ENTER_PACE, Math.max(0.8, length / 1.2))
    trip.walk = trip.path ? length / trip.cruise + SLOW_DOWN / 2 : 0 // in mid-stride, as they went out
    trip.glide = 0.3
    trip.rise = trip.clock // walking on in the dark; the iris opens once it's been shut a moment
    trip.stand = null
    trip.fixed = true
    const bed = trip.to.bed
    if (bed) {
      // getting into bed is the scene, so the iris opens on them at its side; for the alarm, asleep in it
      const wake = trip.to.action === "wake"
      this.pos.set((wake ? bed.lie : bed.side).x, 0, (wake ? bed.lie : bed.side).z)
      this.yaw = wake ? bed.yawIn : bed.yawEdge + Math.PI
      this.act = trip.to
      this.script = this.keysIn(bed, trip.to.site, wake)
      this.script.t = wake ? 6.9 : 0.45
      trip.path = null
      trip.length = 0
      trip.walk = 0
      trip.glide = 0
    }
    // the camera's there already, on them
    this.cam.pos.copy(trip.to.cam.pos)
    this.cam.vPos.set(0, 0, 0)
    this.cam.look.set(this.pos.x, this.ground + 0.9, this.pos.z)
    this.cam.vLook.set(0, 0, 0)
    this.view.copy(this.cam.look)
  }

  /** The way on foot from `from` to what's next: out this door the way they came in (round the furniture), down the
   * path, straight across the street, up the other path, in that door, round the furniture to the seat or the spot. */
  private route(to: Act, from: THREE.Vector3): THREE.Vector3[] {
    const points = [from.clone()]
    const end = to.front ?? to.walk
    const here = this.act?.site ?? this.siteAt(from)
    if (here && here === to.site) {
      // staying put (the library's three questions), or across the room
      if (!(this.act && this.act.at.distanceTo(to.at) < 0.1) && from.distanceTo(end) > 0.2) {
        if (to.front && to.walk.distanceTo(from) > 0.3) points.push(to.walk.clone())
        points.push(end.clone())
      }
      return points.filter((p, i) => i === 0 || p.distanceTo(points[i - 1]) > 0.25)
    }
    if (here) {
      if (this.act && !this.act.bed) {
        if (this.act.walk.distanceTo(from) > 0.3) points.push(this.act.walk.clone())
        for (const v of [...(this.act.via ?? [])].reverse()) points.push(v.clone())
      }
      if (here.inside && here.room?.containsPoint(new THREE.Vector2(from.x, from.z))) points.push(here.inside.clone())
      if (here.outside) points.push(here.outside.clone())
      points.push(here.street.clone())
    } else if (Math.abs(from.x) > 3) points.push(V(Math.sign(from.x) * 4.0, 0, from.z))
    points.push(to.site.street.clone())
    if (to.site.outside && to.site.inside) points.push(to.site.outside.clone(), to.site.inside.clone())
    for (const v of to.via ?? []) points.push(v.clone())
    points.push(to.walk.clone())
    if (to.front) points.push(to.front.clone())
    return points.filter((p, i) => i === 0 || p.distanceTo(points[i - 1]) > 0.3)
  }

  private show(a: Answers): void {
    for (const site of this.sites.values()) site.built?.show(a)
  }

  /** The floor under a point: a room's (or its doorstep's), the road's, or the ground's. */
  private groundAt(x: number, z: number): number {
    for (const site of this.sites.values()) {
      if (site.room?.containsPoint(new THREE.Vector2(x, z))) return FLOOR
      const door = site.built?.door
      if (door && site.group) {
        const local = site.group.worldToLocal(V(x, 0, z))
        if (local.z > -0.4 && local.z < 0.62 && Math.abs(local.x - door.inside.x) < 1.2) return FLOOR
      }
    }
    return Math.abs(x) < 3.5 ? 0 : 0.15
  }

  // ---- in and out of bed ---------------------------------------------------------------------------------------------

  /** Into bed (30 Oct: "make the covers open, him get in and then tuck himself in to the covers"): up to it, the
   * covers thrown back, turning and sitting on its edge, the legs lifted straight out and swung round up onto it
   * (over the mattress, never through it), shuffling over, lying back, taking the covers' edge and pulling them up
   * to the chin. For the alarm's scene: asleep a moment, the alarm, a look, and sitting up with the covers at the
   * waist. */
  private keysIn(bed: BedHere, site: Site, wake: boolean): Script {
    const top = bed.top
    const facing = bed.yawEdge + Math.PI
    const shuffle = bed.edge.clone().lerp(bed.lie, 0.35)
    const lifted = turn(bed.yawEdge, bed.yawIn, 0.12)
    const asleep = { ...BED.lie(top), eyes: 0 }
    const keys: Key[] = [
      { at: 0, pose: this.hero.posed(), pos: this.pos.clone(), yaw: this.yaw, fold: bed.duvet.fold },
      { at: 0.45, pose: BED.stand(), pos: bed.side, yaw: facing, fold: bed.duvet.fold },
      { at: 1.0, pose: BED.reach(), pos: bed.side, yaw: facing, fold: bed.open },
      { at: 1.4, pose: BED.stand(), pos: bed.side, yaw: facing, fold: bed.open },
      { at: 2.2, pose: BED.stand(), pos: bed.side.clone().lerp(bed.edge, 0.4), yaw: bed.yawEdge, fold: bed.open },
      { at: 2.7, pose: BED.edge(top), pos: bed.edge, yaw: bed.yawEdge, fold: bed.open },
      { at: 3.3, pose: BED.lift(top), pos: bed.edge, yaw: lifted, fold: bed.open },
      { at: 4.1, pose: BED.up(top), pos: shuffle, yaw: bed.yawIn, fold: bed.open },
      { at: 4.55, pose: BED.up(top), pos: bed.lie, yaw: bed.yawIn, fold: bed.open },
      { at: 5.25, pose: BED.take(top), pos: bed.lie, yaw: bed.yawIn, fold: bed.open },
      { at: 6.0, pose: BED.tuck(top), pos: bed.lie, yaw: bed.yawIn, fold: bed.closed },
      { at: 6.6, pose: wake ? BED.lie(top) : asleep, pos: bed.lie, yaw: bed.yawIn, fold: bed.closed },
    ]
    if (wake) {
      keys.push({ at: 7.2, pose: asleep, pos: bed.lie, yaw: bed.yawIn, fold: bed.closed })
      keys.push({ at: 7.8, pose: asleep, pos: bed.lie, yaw: bed.yawIn, fold: bed.closed, cue: "alarm" })
      keys.push({ at: 8.3, pose: { ...asleep, eyes: 1, headY: -0.6 }, pos: bed.lie, yaw: bed.yawIn, fold: bed.closed })
      keys.push({ at: 9.2, pose: BED.up(top), pos: bed.up, yaw: bed.yawIn, fold: bed.waist })
    }
    return { keys, t: 0, bed, site, cued: new Set(), fast: 1 }
  }

  /** Out of bed, the same way back: the covers thrown back, shuffling to the edge, the legs swung round off it
   * (lifted clear, then down), standing. */
  private keysOut(bed: BedHere, site: Site): Script {
    const top = bed.top
    const shuffle = bed.edge.clone().lerp(bed.lie, 0.35)
    const lifted = turn(bed.yawEdge, bed.yawIn, 0.12)
    const away = bed.edge.clone().lerp(bed.side, 0.75)
    const keys: Key[] = [
      { at: 0, pose: this.hero.posed(), pos: this.pos.clone(), yaw: this.yaw, fold: bed.duvet.fold },
      { at: 0.55, pose: BED.up(top), pos: bed.lie, yaw: bed.yawIn, fold: bed.open },
      { at: 0.95, pose: BED.up(top), pos: shuffle, yaw: bed.yawIn, fold: bed.open },
      { at: 1.6, pose: BED.lift(top), pos: bed.edge, yaw: lifted, fold: bed.open },
      { at: 2.0, pose: BED.edge(top), pos: bed.edge, yaw: bed.yawEdge, fold: bed.open },
      { at: 2.55, pose: BED.stand(), pos: away, yaw: bed.yawEdge, fold: bed.open },
    ]
    return { keys, t: 0, bed, site, cued: new Set(), fast: 1 }
  }

  /** Where a scene has them at its time: a smooth curve through its keys (moving on through each, not stopping at
   * each), for the pose, place, heading and covers; true when it's over. */
  private play(script: Script, seconds: number): { pose: Pose; done: boolean } {
    const keys = script.keys
    const n = keys.length
    const last = keys[n - 1]
    const t = Math.min(script.t, last.at)
    for (const key of keys) {
      if (key.cue && script.t >= key.at && !script.cued.has(key.cue)) {
        script.cued.add(key.cue)
        script.site.built?.cue?.(key.cue, seconds)
        if (key.cue === "alarm") this.signs.emit("!", this.hero.headAt().add(V(0.1, 0.1, 0)), seconds, 0.4)
      }
    }
    // each key as a row of numbers, its heading unwound from the one before
    const rows: number[][] = []
    let yaw = keys[0].yaw
    for (const key of keys) {
      yaw = turn(yaw, key.yaw, 1)
      rows.push([...poseNumbers(key.pose), key.pos.x, key.pos.z, yaw, key.fold])
    }
    let i = 0
    while (i < n - 2 && keys[i + 1].at <= t) i++
    const j = Math.min(n - 1, i + 1)
    const span = keys[j].at - keys[i].at
    const u = span > 0 ? Math.max(0, Math.min(1, (t - keys[i].at) / span)) : 1
    const tension = 0.75
    const slope = (a: number, b: number, c: number) => {
      // the tangent at key b, from its neighbors, in this segment's time; none at the ends (they ease in and out)
      if (a === b || c === b) return () => 0
      const dt = keys[c].at - keys[a].at
      return (k: number) => (dt > 0 ? ((rows[c][k] - rows[a][k]) / dt) * span * tension : 0)
    }
    const m1 = slope(Math.max(0, i - 1), i, j)
    const m2 = slope(i, j, Math.min(n - 1, j + 1))
    const u2 = u * u
    const u3 = u2 * u
    const out = rows[i].map((p0, k) => {
      const p1 = rows[j][k]
      return (2 * u3 - 3 * u2 + 1) * p0 + (u3 - 2 * u2 + u) * m1(k) + (-2 * u3 + 3 * u2) * p1 + (u3 - u2) * m2(k)
    })
    const npose = poseNumbers(keys[0].pose).length
    this.pos.set(out[npose], 0, out[npose + 1])
    this.yaw = out[npose + 2]
    script.bed.duvet.set(out[npose + 3])
    return { pose: poseFrom(out.slice(0, npose)), done: script.t >= last.at }
  }

  // ---- each frame ----------------------------------------------------------------------------------------------------

  private loop(time: number): void {
    this.raf = requestAnimationFrame(this.loop)
    const dt = Math.max(0, Math.min(0.05, (time - this.last) / 1000)) // never backward, never a big leap
    this.last = time
    const seconds = (time - this.started) / 1000
    const trip = this.trip
    let walking = false
    let follow: { pos: THREE.Vector3; look: THREE.Vector3 } | null = null
    let scripted: Pose | null = null
    let centered = false
    if (trip) {
      const step = dt * trip.fast
      // first out of bed, or up off a seat
      if (trip.out && trip.out.t < trip.out.keys[trip.out.keys.length - 1].at) {
        trip.out.t += step
        scripted = this.play(trip.out, seconds).pose
        follow = trip.from.cam
      } else {
        // walking, the clock runs slower while they're turned from the way (going slower round a corner until they
        // face it), so the feet keep pace with the ground
        let slow = 1
        if (trip.path && trip.clock >= trip.rise && trip.clock - trip.rise < trip.walk) {
          const now = Math.min(1, along(trip.clock - trip.rise, trip.length, trip.cruise, trip.fixed) / trip.length)
          const way = trip.path.getTangentAt(Math.min(1, now + 0.02))
          slow = Math.max(0.35, Math.cos(Math.min(Math.PI / 2, Math.abs(turn(0, Math.atan2(way.x, way.z) - this.yaw, 1)))))
        }
        const before = trip.clock - trip.rise
        trip.clock += step * slow
        const going = trip.rise + trip.walk
        if (!trip.wipe) this.minutes = trip.from.minutes + trip.delta * ease(going ? trip.clock / going : trip.clock / trip.glide)
        // staying where they are: the camera glides to the new view, as slowly as the distance needs
        if (!trip.path && !trip.wipe && trip.clock >= trip.rise) {
          const k = ease(trip.clock / trip.glide)
          follow = { pos: trip.from.cam.pos.clone().lerp(trip.to.cam.pos, k), look: trip.from.cam.look.clone().lerp(trip.to.cam.look, k) }
        }
        if (trip.clock < trip.rise) {
          // standing up out of the seat, to in front of it
          this.weight = Math.max(0, 1 - trip.clock / trip.rise)
          if (trip.stand) this.pos.copy(trip.stand[1]).lerp(trip.stand[0], ease(Math.min(1, this.weight * 1.6)))
          follow = trip.from.cam
        } else if (trip.wipe && !trip.wipe.jumped) {
          // a few steps toward the door while the iris closes on them; the hours pass as it does
          const w = trip.wipe
          const t = trip.clock - trip.rise
          walking = true
          centered = true
          this.act = null
          this.weight = 0
          if (w.exit && w.exitLength > 0.2) {
            const s = along(t, w.exitLength, EXIT_PACE)
            this.speed = dt > 0 ? Math.max(0, (s - along(Math.max(0, t - step), w.exitLength, EXIT_PACE)) / dt) : 0
            const at = w.exit.getPointAt(Math.min(1, s / w.exitLength))
            const toward = w.exit.getTangentAt(Math.min(1, s / w.exitLength + 0.02))
            this.pos.set(at.x, 0, at.z)
            const off = turn(0, Math.atan2(toward.x, toward.z) - this.yaw, 1)
            const most = 6 * dt * trip.fast
            this.yaw += Math.max(-most, Math.min(most, off * (1 - Math.pow(0.0005, dt))))
          }
          this.iris = 1 - ease((t - 0.2) / (EXIT - 0.2))
          this.minutes = trip.from.minutes + trip.delta * ease(t / EXIT)
          follow = { pos: trip.from.cam.pos, look: V(this.pos.x, this.ground + 0.9, this.pos.z) }
          if (t >= EXIT) this.jump(trip)
        } else if (trip.path && trip.clock - trip.rise < trip.walk) {
          walking = true
          centered = true
          this.act = null
          this.weight = 0
          const t = trip.clock - trip.rise
          const s = along(t, trip.length, trip.cruise, trip.fixed)
          const at = trip.path.getPointAt(Math.min(1, s / trip.length))
          this.speed = dt > 0 ? Math.max(0, (s - along(Math.max(0, before), trip.length, trip.cruise, trip.fixed)) / dt) : 0
          const toward = trip.path.getTangentAt(Math.min(1, s / trip.length + 0.02))
          this.pos.set(at.x, 0, at.z)
          // turning as a person turns: at most about a turn a second
          const off = turn(0, Math.atan2(toward.x, toward.z) - this.yaw, 1)
          const most = 6 * dt * trip.fast
          this.yaw += Math.max(-most, Math.min(most, off * (1 - Math.pow(0.0005, dt))))
          const p = s / trip.length
          const look = V(this.pos.x, this.ground + 0.9, this.pos.z)
          if (trip.fixed) {
            // stepping in: the camera where the scene has it, on them, coming round to the scene as they get there
            this.iris = ease((trip.clock - trip.rise - HOLD) / OPEN)
            follow = { pos: trip.to.cam.pos, look: look.lerp(trip.to.cam.look, smooth(0.7, 1, p)) }
          } else {
            // across the room: the camera swings round them from this scene's view to the next one's (30 Oct: it
            // used to drop in behind them, looking at the floor)
            const pos = orbit(look, trip.from.cam.pos, trip.to.cam.pos, smooth(0.1, 0.95, p))
            const on = trip.from.cam.look.clone().lerp(look, smooth(0, 0.35, p))
            follow = { pos, look: on.lerp(trip.to.cam.look, smooth(0.65, 1, p)) }
          }
        } else if ((!trip.wipe || trip.wipe.jumped) && trip.clock - trip.rise >= (trip.path ? trip.walk : trip.glide)) {
          // there: into bed, or into what they came to do. Arrived at the path's end (a walk skipped in one frame
          // never moved them along it), or, with reduced motion, straight into place
          this.trip = null
          this.minutes = trip.minutes
          this.speed = 0
          if (trip.path) {
            const end = trip.path.getPointAt(1)
            this.pos.set(end.x, 0, end.z)
            this.weight = 0
          }
          if (this.options.still && !trip.to.bed) {
            this.pos.set(trip.to.at.x, 0, trip.to.at.z)
            this.yaw = trip.to.yaw
            this.weight = 1
          }
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
    // doing what they came for: into place, then the action. To a seat: turned round in front of it first, then
    // sitting back onto it (30 Oct: "his legs phase through the sofa")
    if (!walking && !scripted && this.act && (!this.trip || this.trip.clock >= this.trip.rise)) {
      this.speed = 0
      const act = this.act
      if (act.front && this.weight < 1) {
        const left = Math.abs(turn(0, act.yaw - this.yaw, 1))
        this.yaw = toward(this.yaw, act.yaw, 1 - Math.pow(0.0004, dt), 5 * dt)
        if (left < 0.4 || this.weight > 0) this.weight = Math.min(1, this.weight + dt * 1.5)
        this.pos.copy(act.front).lerp(V(act.at.x, 0, act.at.z), ease(Math.min(1, this.weight * 1.6)))
      } else {
        this.weight = Math.min(1, this.weight + dt * 2.2)
        const k = 1 - Math.pow(0.004, dt)
        this.pos.lerp(V(act.at.x, 0, act.at.z), k)
        this.yaw = toward(this.yaw, act.yaw, k, 5 * dt)
      }
      follow ??= act.cam
    }
    follow ??= { pos: this.cam.pos, look: this.cam.look }
    if (!this.trip?.wipe) this.iris = Math.min(1, this.iris + dt / OPEN)
    if (this.options.still) this.iris = 1
    // their feet on the floor they're over
    const floor = this.act && this.weight > 0.5 && !this.act.bed ? this.act.at.y : this.groundAt(this.pos.x, this.pos.z)
    this.ground = floor > this.ground ? floor : this.ground + (floor - this.ground) * Math.min(1, dt * 12)
    this.hero.root.position.set(this.pos.x, this.ground, this.pos.z)
    this.hero.root.rotation.y = this.yaw
    // going somewhere, as against only the hours passing where they are (an answer moving the time)
    const moving = !!this.trip && (!!this.trip.path || !!this.trip.out || !!this.trip.wipe)
    // the backpack off in bed and sitting back in a seat
    const inBed = !!this.script || !!(this.trip?.out && this.trip.clock === 0) || (!!this.act?.bed && !moving)
    this.hero.wearPack(!inBed && !(this.act?.front && this.weight > 0.45))
    // now and then, while you decide, they do something small: look up at you, scratch their head, yawn
    const settled = !this.trip && !this.script && this.act && this.weight > 0.95
    if (settled && this.act && seconds > this.fidgetAt && !this.hero.busy(seconds) && !this.options.still) {
      const choices = FIDGETS[this.act.action] ?? []
      if (choices.length) this.hero.react(choices[Math.floor(Math.random() * choices.length)], seconds)
      this.fidgetAt = seconds + 10 + Math.random() * 6
    }
    // a letter that came on the way, once they're at the boxes
    if (this.posted && settled && this.step === "bring") {
      this.posted = false
      this.letter(seconds)
    }
    // the letter in hand: turn and read it; read: back to the boxes
    if (this.mailing && seconds >= this.mailing) {
      this.mailing = 0
      this.mailUntil = seconds + 4.5
      const stop = STOPS[this.step]
      const act = this.answers && this.actFor(stop.place, stop.spot, this.answers)
      if (act && this.step === "bring") this.change(act)
    }
    if (this.mailUntil && seconds > this.mailUntil && !this.extra.reading && !this.trip) this.mailDone()
    // the timer for a sitting rings: they stretch
    if (settled && this.step === "focus" && this.answers) {
      // counted from when the timer was last set, so changing the length (turning the timer) isn't a ring
      if (this.ringsFor !== this.answers.focus_hours) {
        this.ringsFor = this.answers.focus_hours
        this.ringsFrom = seconds
        this.rings = 0
      }
      const ring = Math.floor((seconds - this.ringsFrom) / sittingFor(this.answers.focus_hours))
      if (ring !== this.rings) {
        if (this.rings >= 0) {
          this.hero.react("restBack", seconds)
          this.act?.site.built?.cue?.("ring", seconds)
          this.signs.emit("!", this.hero.headAt().add(V(0.25, -0.3, 0.2)), seconds, 0.32)
        }
        this.rings = ring
      }
    } else {
      this.rings = -1
      this.ringsFor = -1
    }
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
    // the covers over whoever's in the bed, as they lie (30 Oct: "i want the bedsheets to bend around his legs")
    const bed = this.script?.bed ?? (this.trip?.out && this.trip.clock === 0 ? this.trip.out.bed : null) ?? (this.act?.bed && !moving ? this.act.bed : null)
    if (bed) bed.duvet.over(this.hero.samples())
    if (this.covered && this.covered !== bed?.duvet) this.covered.over([])
    this.covered = bed?.duvet ?? null
    this.signs.every(action, this.act && !this.script && !moving ? this.weight : 0, this.hero.headAt(), seconds)
    this.signs.update(seconds, dt)
    // the camera eases after where it should be; walking, it keeps them dead center
    this.chase(follow, dt, centered)
    this.camera.position.copy(this.cam.pos)
    this.camera.lookAt(this.view)
    this.camera.updateMatrixWorld()
    this.snow?.update(dt, seconds, this.camera.position)
    const middle = this.hero.headAt().add(V(0, -0.5, 0)).project(this.camera)
    this.out.iris.value = this.iris
    this.out.irisAt.value.set(Math.max(0.08, Math.min(0.92, (middle.x + 1) / 2)), Math.max(0.08, Math.min(0.92, (middle.y + 1) / 2)))
    this.cut()
    this.light(lightAt(this.minutes), time)
    for (const site of this.sites.values()) site.built?.tick?.(seconds, this.minutes, this.step)
    this.composer.render(dt)
    this.measure(time)
  }

  private chase(to: { pos: THREE.Vector3; look: THREE.Vector3 }, dt: number, centered: boolean): void {
    const c = this.cam
    if (this.options.still || !this.ready) {
      c.pos.copy(to.pos)
      c.look.copy(to.look)
      this.view.copy(to.look)
      return
    }
    // on them exactly while they walk, but coming onto them (and off) over half a second, never at once (30 Oct:
    // "theres random frame cuts (eg when he starts walking)")
    this.lockOn = centered ? Math.min(1, this.lockOn + dt / 0.5) : Math.max(0, this.lockOn - dt / 0.5)
    const spring = (x: THREE.Vector3, v: THREE.Vector3, target: THREE.Vector3, w: number) => {
      const accel = target.clone().sub(x).multiplyScalar(w * w).addScaledVector(v, -2 * w)
      v.addScaledVector(accel, dt)
      x.addScaledVector(v, dt)
    }
    spring(c.pos, c.vPos, to.pos, centered ? 5 : 4.5)
    spring(c.look, c.vLook, to.look, 5.5)
    this.view.copy(c.look).lerp(to.look, ease(this.lockOn))
  }

  /** Cut away the front of the house they're in (or going into), so you can see in. What's cut still casts shadows. */
  private cut(): void {
    // cut away while they're anywhere in it or on its front path, and while they're headed into it
    const near = this.siteAt(this.pos)
    const target = near?.built?.cut ? near : null
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
    if (!this.env || this.forceEnv || (sunDir.angleTo(this.envSun) > 0.05 && time - this.envAt > 700) || (!this.trip && sunDir.angleTo(this.envSun) > 0.004)) {
      this.forceEnv = false
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

/** Turn toward a heading the short way round, `k` of the way but at most `most` radians. */
function toward(from: number, to: number, k: number, most: number): number {
  const d = turn(0, to - from, 1) * Math.min(1, k)
  return from + Math.max(-most, Math.min(most, d))
}

/** Turn from one heading toward another the short way round, `k` of the way. */
function turn(from: number, to: number, k: number): number {
  let d = (to - from) % (Math.PI * 2)
  if (d > Math.PI) d -= Math.PI * 2
  if (d < -Math.PI) d += Math.PI * 2
  return from + d * Math.min(1, k)
}

/** A camera position `t` of the way from `a` to `b`, swung round `center` at a height and distance between theirs,
 * the way round that passes the street's side of it (toward x = 0), not the buildings'. */
function orbit(center: THREE.Vector3, a: THREE.Vector3, b: THREE.Vector3, t: number): THREE.Vector3 {
  if (t <= 0) return a.clone()
  if (t >= 1) return b.clone()
  const polar = (v: THREE.Vector3) => {
    const o = v.clone().sub(center)
    const flat = Math.hypot(o.x, o.z)
    return { yaw: Math.atan2(o.x, o.z), up: o.y, flat: Math.max(0.01, flat) }
  }
  const pa = polar(a)
  const pb = polar(b)
  let d = (pb.yaw - pa.yaw) % (Math.PI * 2)
  if (d > Math.PI) d -= Math.PI * 2
  if (d < -Math.PI) d += Math.PI * 2
  const road = -Math.sign(center.x)
  if (road && Math.abs(d) > 0.6) {
    // of the two ways round, the one whose middle is over the street
    const other = d - Math.sign(d) * Math.PI * 2
    const side = (delta: number) => Math.sin(pa.yaw + delta / 2) * road
    if (side(other) > side(d)) d = other
  }
  const yaw = pa.yaw + d * t
  const flat = pa.flat + (pb.flat - pa.flat) * t
  const up = pa.up + (pb.up - pa.up) * t
  return new THREE.Vector3(center.x + Math.sin(yaw) * flat, center.y + up, center.z + Math.cos(yaw) * flat)
}
