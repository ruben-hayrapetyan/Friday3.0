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
import { type Action, Character, type Mood, type Reaction, SEATED, Signs } from "./character"
import { fallen, forest, type Planting, woods } from "./nature"
import { type Built, buildPlace, FLOOR, FRONT, type Scene, SIDEWALK, type Socket } from "./places"
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
  street: THREE.Vector3 // on the sidewalk in front of it
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
  cam: { pos: THREE.Vector3; look: THREE.Vector3 }
}

/** Going from one thing to the next: getting up first if they were sitting or lying, walking the path (speeding up,
 * going steadily, slowing down), then settling into what's next while the camera arrives. */
interface Trip {
  path: THREE.CatmullRomCurve3 | null
  length: number
  clock: number // seconds into it
  fast: number // how much quicker than life (Return again hurries it)
  rise: number // seconds getting up
  walk: number // seconds walking (0: staying where they are)
  cruise: number // metres a second, once going
  dir: THREE.Vector3 // the way it goes overall: the camera swings to in front of them on it
  from: { minutes: number; cam: { pos: THREE.Vector3; look: THREE.Vector3 }; act: Act | null }
  to: Act
  minutes: number
  delta: number
}

const SPEED_UP = 0.55 // seconds getting going
const SLOW_DOWN = 0.7 // and stopping
const ARRIVE = 0.7 // the camera's last stretch, while they settle

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

/** A walk's pace: a stroll across a room, a quick walk up the street, a jog for a long way; never much over five
 * seconds. */
export function paceFor(length: number): number {
  const cruise = Math.max(1.4, Math.min(5.2, length / 4))
  return Math.min(cruise, length / ((SPEED_UP + SLOW_DOWN) / 2) - 0.001)
}

/** What they do when an answer changes: glad of more time, a gulp at more work, a yawn at an early alarm. */
export function reactionTo(was: Answers, now: Answers): Reaction | null {
  const after = (t: string) => (minutesOf(t) + 1440 - 12 * 60) % 1440 // a bedtime's lateness, from noon
  const more = (k: keyof Answers, yes: Reaction, no: Reaction) => ((now[k] as number) > (was[k] as number) ? yes : no)
  if (now.wake !== was.wake) return minutesOf(now.wake) < minutesOf(was.wake) ? "yawn" : "cheer"
  if (now.bedtime !== was.bedtime) return after(now.bedtime) > after(was.bedtime) ? "yawn" : "nod"
  if (now.weekend_wake !== was.weekend_wake || now.weekend_bedtime !== was.weekend_bedtime) return "nod"
  if (now.normal_hours !== was.normal_hours) return more("normal_hours", "gulp", "relief")
  if (now.most_hours !== was.most_hours) return more("most_hours", "gulp", "relief")
  if (now.focus_hours !== was.focus_hours) return more("focus_hours", "flex", "nod")
  if (now.finish_early_days !== was.finish_early_days) return more("finish_early_days", "cheer", "gulp")
  if (now.evening_free !== was.evening_free) return more("evening_free", "cheer", "gulp")
  if (now.evening_from !== was.evening_from) return "nod"
  if (now.weekend_free !== was.weekend_free) return more("weekend_free", "cheer", "gulp")
  if (now.brief !== was.brief) return now.brief ? "cheer" : "shrug"
  if (JSON.stringify(now.calendars ?? []) !== JSON.stringify(was.calendars ?? [])) return "nod"
  return null
}

const SIGN_FOR: Partial<Record<Reaction, string>> = { cheer: "note", gulp: "sweat", yawn: "z", relief: "heart", shrug: "?", flex: "!", scratch: "?" }

/** What they do now and then while you decide, by what they're doing. */
const FIDGETS: Partial<Record<Action, Reaction[]>> = {
  stand: ["glance", "scratch"],
  wave: ["glance"],
  stretch: ["yawn", "glance"],
  type: ["glance", "scratch"],
  focus: ["glance"],
  stress: ["scratch", "gulp"],
  look: ["scratch", "glance"],
  tv: ["glance", "relief"],
  laptop: ["scratch", "glance"],
  picnic: ["glance", "relief"],
  coffee: ["glance"],
  counter: ["glance", "scratch"],
  boxes: ["glance"],
  calendar: ["glance", "nod"],
}

const smooth = (a: number, b: number, x: number) => {
  const t = Math.max(0, Math.min(1, (x - a) / (b - a)))
  return t * t * (3 - 2 * t)
}
const ease = (t: number) => -(Math.cos(Math.PI * t) - 1) / 2

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
  private answers: Answers | null = null
  private fidgetAt = 6 // seconds: when they next do something while you decide
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
      // up the street they walk the near side of the road, clear of the trees and poles along the curb, so the
      // camera ahead of them over the road always sees them
      const walkway = side === 0 ? V(place === "end" ? 0 : -1.6, 0, z) : V(side * 1.6, 0, front.z)
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
    const points = this.route(act)
    const path = points.length > 1 ? new THREE.CatmullRomCurve3(points, false, "centripetal", 0.5) : null
    const length = path ? path.getLength() : 0
    const walking = !!path && length > 0.2
    const cruise = walking ? paceFor(length) : 1
    // sitting or lying down: up first
    const seated = this.act && (this.act.seat !== undefined || SEATED[this.act.action] !== undefined) && this.weight > 0.3
    const dir = walking && path ? path.getPointAt(1).sub(path.getPointAt(0)).setY(0) : V(0, 0, -1)
    if (dir.lengthSq() < 0.01) dir.set(Math.sin(this.yaw), 0, Math.cos(this.yaw))
    this.trip = {
      path: walking ? path : null,
      length: walking ? length : 0,
      clock: 0,
      fast: this.options.still ? 1000 : 1,
      rise: walking && seated ? 0.5 : 0,
      walk: walking ? length / cruise + (SPEED_UP + SLOW_DOWN) / 2 : 0,
      cruise,
      dir: dir.normalize(),
      from: { minutes: this.minutes, cam: { pos: this.cam.pos.clone(), look: this.cam.look.clone() }, act: this.act },
      to: act,
      minutes,
      delta: timeStep(this.minutes, minutes, back),
    }
    if (!walking) this.change(act)
  }

  /** The same place, something else to do: from one pose into the other. */
  private change(act: Act): void {
    if (this.act && this.act.action !== act.action) {
      this.before = this.act.action
      this.changed = 0
    }
    this.act = act
  }

  /** Answers changed where you are: the place shows them, they react, the sky follows the time, and what they do
   * there follows what you chose. */
  update(a: Answers): void {
    this.show(a)
    const was = this.answers
    this.answers = { ...a }
    const now = (performance.now() - this.started) / 1000
    const reaction = was ? reactionTo(was, a) : null
    if (reaction && !this.trip) {
      this.hero.react(reaction, now)
      const sign = SIGN_FOR[reaction]
      if (sign) this.signs.emit(sign, this.hero.headAt().add(V(0.15, 0.05, 0)), now, 0.34)
      this.fidgetAt = now + 8
    }
    const stop = STOPS[this.step] ?? STOPS.hello
    const minutes = stop.at(a)
    const act = this.actFor(stop.place, stop.spot, a)
    if (this.trip) {
      this.trip.minutes = minutes
      this.trip.delta = timeStep(this.trip.from.minutes, minutes, false)
      if (act) this.trip.to = act
      return
    }
    if (act && this.act && act.at.distanceTo(this.act.at) > 0.1) return this.go(this.step, a) // elsewhere in the same place now (the park: the blanket, or the bench)
    if (act) this.change(act) // the same place, done another way (TV or the laptop; how hard they're working)
    if (Math.abs(this.minutes - minutes) > 0.5 && this.act) {
      this.trip = { path: null, length: 0, clock: 0, fast: this.options.still ? 1000 : 1, rise: 0, walk: 0, cruise: 1, dir: V(0, 0, -1), from: { minutes: this.minutes, cam: { pos: this.cam.pos.clone(), look: this.cam.look.clone() }, act: this.act }, to: this.act, minutes, delta: minutes - this.minutes }
    }
  }

  /** Get there now (another Return while walking): the rest of the way four times as fast. */
  hurry(): void {
    if (this.trip) this.trip.fast = 4
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
    const w = (v: THREE.Vector3) => (site.group as THREE.Group).localToWorld(v.clone())
    if (s.bedding) this.hero.bedding(s.bedding)
    return {
      site,
      walk: w(s.walk),
      at: w(s.at),
      yaw: s.yaw - site.side * (Math.PI / 2),
      action: s.action,
      seat: s.seat,
      mood: s.mood,
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

  /** The way on foot from where they are to what's next: out this door, along and across the street, in that one. */
  private route(to: Act): THREE.Vector3[] {
    const points = [this.pos.clone()]
    const here = this.act?.site ?? this.siteAt(this.pos)
    if (here && here === to.site) {
      // staying put (the library's three questions), or across the room
      if (!(this.act && this.act.at.distanceTo(to.at) < 0.1) && this.pos.distanceTo(to.walk) > 0.2) points.push(to.walk.clone())
      return points
    }
    if (here) {
      if (this.act?.at && this.act.walk.distanceTo(this.pos) > 0.3) points.push(this.act.walk.clone())
      if (here.inside && here.room?.containsPoint(new THREE.Vector2(this.pos.x, this.pos.z))) points.push(here.inside.clone())
      if (here.outside) points.push(here.outside.clone())
      points.push(here.street.clone())
    } else points.push(V(Math.sign(this.pos.x || -1) * 1.6, 0, this.pos.z))
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

  // ---- each frame ----------------------------------------------------------------------------------------------------

  private loop(time: number): void {
    this.raf = requestAnimationFrame(this.loop)
    const dt = Math.min(0.05, (time - this.last) / 1000)
    this.last = time
    const seconds = (time - this.started) / 1000
    const trip = this.trip
    let walking = false
    let follow: { pos: THREE.Vector3; look: THREE.Vector3 } | null = null
    if (trip) {
      trip.clock += dt * trip.fast
      const going = trip.rise + trip.walk
      const total = going + ARRIVE
      const p = Math.min(1, trip.clock / Math.max(total, 0.001))
      this.minutes = trip.from.minutes + trip.delta * ease(Math.min(1, trip.clock / Math.max(going || 1, 0.001)))
      if (trip.path) {
        const t = trip.clock - trip.rise
        if (t < 0) {
          // getting up from where they were
          this.weight = Math.max(0, this.weight - (dt * trip.fast) / trip.rise)
          this.speed = 0
        } else if (t < trip.walk) {
          walking = true
          this.act = null
          this.weight = 0
          const s = along(t, trip.length, trip.cruise)
          const at = trip.path.getPointAt(Math.min(1, s / trip.length))
          const step = s - along(t - dt * trip.fast, trip.length, trip.cruise)
          this.speed = dt > 0 ? Math.max(0, step / dt) : 0
          const ahead = trip.path.getTangentAt(Math.min(1, s / trip.length + 0.02))
          this.pos.set(at.x, 0, at.z)
          this.yaw = turn(this.yaw, Math.atan2(ahead.x, ahead.z), 1 - Math.pow(0.0005, dt))
        } else if (this.act !== trip.to) {
          this.change(trip.to)
          this.fidgetAt = seconds + 5
        }
        // the camera: from the last scene's to ahead of them over the road, looking back as they come up the street,
        // then to the next scene's, in front of the room they go into (never round through its walls)
        const ahead = Math.sign(trip.dir.z) || -1
        const look = V(this.pos.x, this.ground + 0.85, this.pos.z)
        const lead = { look, pos: V(Math.max(-2, Math.min(2, this.pos.x * 0.35)), this.ground + 5.8, this.pos.z + ahead * 8.5) }
        follow = blend(blend(trip.from.cam, lead, smooth(0, 0.3, p)), trip.to.cam, smooth(0.6, 1, p))
      } else follow = blend(trip.from.cam, trip.to.cam, ease(p))
      if (p >= 1) this.arrive(trip)
    }
    // doing what they came for: into place, then the action
    if (!walking && this.act && (!trip || trip.clock >= trip.rise)) {
      this.speed = 0
      this.weight = Math.min(1, this.weight + dt * 2.2)
      const k = 1 - Math.pow(0.004, dt)
      this.pos.lerp(V(this.act.at.x, 0, this.act.at.z), k)
      this.yaw = turn(this.yaw, this.act.yaw, k)
      follow ??= this.act.cam
    }
    follow ??= { pos: this.cam.pos, look: this.cam.look }
    // their feet on the floor they're over
    const floor = this.act && this.weight > 0.5 ? this.act.at.y : this.groundAt(this.pos.x, this.pos.z)
    this.ground += (floor - this.ground) * Math.min(1, dt * 12)
    this.hero.root.position.set(this.pos.x, this.ground, this.pos.z)
    this.hero.root.rotation.y = this.yaw
    // now and then, while you decide, they do something: look up at you, scratch their head, yawn
    const settled = !this.trip && this.act && this.weight > 0.95
    if (settled && this.act && seconds > this.fidgetAt && !this.hero.busy(seconds) && !this.options.still) {
      const choices = FIDGETS[this.act.action] ?? []
      if (choices.length) this.hero.react(choices[Math.floor(Math.random() * choices.length)], seconds)
      this.fidgetAt = seconds + 7 + Math.random() * 5
    }
    const action = this.act?.action ?? "stand"
    this.changed = Math.min(1, this.changed + dt * 2.5)
    const toYou = Math.atan2(this.camera.position.x - this.pos.x, this.camera.position.z - this.pos.z)
    const look = Math.max(-1.1, Math.min(1.1, turn(0, toYou - this.yaw, 1)))
    this.hero.update(dt, seconds, walking ? this.speed : 0, action, this.act ? this.weight : 0, this.act?.seat ?? SEATED[action], this.changed < 1 ? (this.before ?? undefined) : undefined, this.changed, this.act?.mood ?? {}, look)
    this.signs.every(action, this.act ? this.weight : 0, this.hero.headAt(), seconds)
    this.signs.update(seconds, dt)
    // the camera eases after where it should be
    this.chase(follow, dt)
    this.camera.position.copy(this.cam.pos)
    this.camera.lookAt(this.cam.look)
    this.camera.updateMatrixWorld()
    this.cut()
    this.light(lightAt(this.minutes), time)
    for (const site of this.sites.values()) site.built?.tick?.(seconds, this.minutes, this.step)
    this.composer.render(dt)
    this.measure(time)
  }

  private arrive(trip: Trip): void {
    this.trip = null
    this.minutes = trip.minutes
    if (this.act !== trip.to) this.change(trip.to)
  }

  private chase(to: { pos: THREE.Vector3; look: THREE.Vector3 }, dt: number): void {
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
    spring(c.pos, c.vPos, to.pos, 6.5)
    spring(c.look, c.vLook, to.look, 13)
  }

  /** Cut away the front of the house they're in (or going into), so you can see in. What's cut still casts shadows. */
  private cut(): void {
    const near = this.siteAt(this.pos)
    const target = near?.built?.cut && (this.act?.site === near || (this.trip && this.trip.to.site === near) || near.room?.containsPoint(new THREE.Vector2(this.pos.x, this.pos.z))) ? near : null
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

function blend(a: { pos: THREE.Vector3; look: THREE.Vector3 }, b: { pos: THREE.Vector3; look: THREE.Vector3 }, t: number) {
  return { pos: a.pos.clone().lerp(b.pos, t), look: a.look.clone().lerp(b.look, t) }
}
