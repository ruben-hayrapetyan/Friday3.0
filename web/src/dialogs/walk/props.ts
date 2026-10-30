// The walk's materials and building blocks (walk/World.ts): physically based materials on the surfaces of
// walk/textures.ts, shapes measured in metres with their textures mapped at true size, and `bake`, which merges a
// place's still parts into a few meshes so the town draws quickly.

import * as THREE from "three"
import { RoundedBoxGeometry } from "three/examples/jsm/geometries/RoundedBoxGeometry.js"
import { mergeGeometries } from "three/examples/jsm/utils/BufferGeometryUtils.js"
import { asphalt, bark, brick, carpet, concrete, cork, fabric, floorboards, lawn, plaster, shingles, siding, stone, type Surface, wood } from "./textures"

const made = new Map<string, THREE.MeshStandardMaterial>()

function material(key: string, make: () => THREE.MeshStandardMaterial): THREE.MeshStandardMaterial {
  const found = made.get(key)
  if (found) return found
  const m = make()
  made.set(key, m)
  return m
}

function textured(s: Surface, color = 0xffffff, inside = false, normal = 1): THREE.MeshStandardMaterial {
  return new THREE.MeshStandardMaterial({
    color,
    map: s.map,
    normalMap: s.normalMap,
    normalScale: new THREE.Vector2(normal, normal),
    roughnessMap: s.roughnessMap,
    envMapIntensity: inside ? 0.45 : 1,
  })
}

/** The town's materials, by what they are. Inside ones take less of the sky's light. */
export const M = {
  asphalt: () => material("asphalt", () => textured(asphalt())),
  concrete: () => material("concrete", () => textured(concrete())),
  lawn: () => material("lawn", () => textured(lawn())),
  brick: () => material("brick", () => textured(brick("red"))),
  brickPale: () => material("brickPale", () => textured(brick("pale"))),
  stone: () => material("stone", () => textured(stone())),
  shingles: (color = 0xffffff) => material(`shingles${color}`, () => textured(shingles(), color)),
  floor: (color = 0xffffff) => material(`floor${color}`, () => textured(floorboards(), color, true)),
  bark: () => material("bark", () => textured(bark())),
  cork: () => material("cork", () => textured(cork(), 0xffffff, true)),
  siding: (color: number) => material(`siding${color}`, () => textured(siding(), color)),
  plaster: (color = 0xf2efe8) => material(`plaster${color}`, () => textured(plaster(), color, true, 0.5)),
  fabric: (color: number) => material(`fabric${color}`, () => textured(fabric(), color, true)),
  carpet: (color: number) => material(`carpet${color}`, () => textured(carpet(), color, true)),
  wood: (color = 0xffffff) => material(`wood${color}`, () => textured(wood(), color, true)),
  /** Paint or plastic with no pattern. */
  paint: (color: number, rough = 0.6, inside = false) =>
    material(`paint${color}:${rough}:${inside}`, () => new THREE.MeshStandardMaterial({ color, roughness: rough, envMapIntensity: inside ? 0.45 : 1 })),
  metal: (color: number, rough = 0.35) => material(`metal${color}:${rough}`, () => new THREE.MeshStandardMaterial({ color, roughness: rough, metalness: 1 })),
  /** Clear glass: mostly the reflection of the sky. Doesn't cast a shadow. */
  glass: () =>
    material("glass", () => {
      const m = new THREE.MeshStandardMaterial({ color: 0x9fb4c4, roughness: 0.04, metalness: 0, transparent: true, opacity: 0.16, envMapIntensity: 1.6, depthWrite: false, side: THREE.DoubleSide })
      m.userData.noShadow = true
      return m
    }),
  /** A window into a room we never enter: dark, reflecting the sky. */
  window: () => material("window", () => new THREE.MeshStandardMaterial({ color: 0x141a22, roughness: 0.06, metalness: 0.4, envMapIntensity: 1.4 })),
  /** The same window with a lamp on inside, at night (World turns `emissiveIntensity` up as it gets dark). */
  windowLit: (tone: number) =>
    material(`windowLit${tone}`, () => {
      const m = new THREE.MeshStandardMaterial({ color: 0x141a22, roughness: 0.06, metalness: 0.4, envMapIntensity: 1.4, emissive: tone, emissiveIntensity: 0 })
      m.userData.night = 2.2
      return m
    }),
  /** A lamp's glass, glowing at night. */
  lamp: (tone = 0xffd8a0) =>
    material(`lamp${tone}`, () => {
      const m = new THREE.MeshStandardMaterial({ color: 0xf4efe6, roughness: 0.3, emissive: tone, emissiveIntensity: 0 })
      m.userData.night = 6
      return m
    }),
  /** A bulb that is on whenever you're there (indoors), brighter at night. */
  bulb: (tone = 0xffd29a, level = 4) =>
    material(`bulb${tone}:${level}`, () => {
      const m = new THREE.MeshStandardMaterial({ color: 0xf8f2e8, roughness: 0.4, emissive: tone, emissiveIntensity: level })
      m.userData.always = level
      return m
    }),
}

/** Texture coordinates in metres, projected from each face's direction, so a surface's pattern is its real size. */
export function meterUV(geo: THREE.BufferGeometry): THREE.BufferGeometry {
  const pos = geo.attributes.position
  const nor = geo.attributes.normal
  const uv = new Float32Array(pos.count * 2)
  for (let i = 0; i < pos.count; i++) {
    const x = pos.getX(i)
    const y = pos.getY(i)
    const z = pos.getZ(i)
    const ax = Math.abs(nor.getX(i))
    const ay = Math.abs(nor.getY(i))
    const az = Math.abs(nor.getZ(i))
    if (ax >= ay && ax >= az) {
      uv[i * 2] = nor.getX(i) > 0 ? -z : z
      uv[i * 2 + 1] = y
    } else if (ay >= az) {
      uv[i * 2] = x
      uv[i * 2 + 1] = nor.getY(i) > 0 ? -z : z
    } else {
      uv[i * 2] = nor.getZ(i) > 0 ? x : -x
      uv[i * 2 + 1] = y
    }
  }
  geo.setAttribute("uv", new THREE.BufferAttribute(uv, 2))
  return geo
}

function placed(geo: THREE.BufferGeometry, m: THREE.Material, x: number, y: number, z: number): THREE.Mesh {
  const mesh = new THREE.Mesh(geo, m)
  mesh.position.set(x, y, z)
  mesh.castShadow = !m.userData.noShadow
  mesh.receiveShadow = true
  return mesh
}

/** A box `w` wide (x), `h` high, `d` deep (z), standing on y, centred on x and z; its edges rounded by `round`. */
export function block(w: number, h: number, d: number, m: THREE.Material, x = 0, y = 0, z = 0, round = 0): THREE.Mesh {
  const r = Math.min(round, w / 2 - 0.001, h / 2 - 0.001, d / 2 - 0.001)
  const geo = r > 0 ? new RoundedBoxGeometry(w, h, d, 2, r) : new THREE.BoxGeometry(w, h, d)
  return placed(meterUV(geo), m, x, y + h / 2, z)
}

/** A box between two corners: x0..x1, y0..y1, z0..z1. */
export function span(x0: number, x1: number, y0: number, y1: number, z0: number, z1: number, m: THREE.Material): THREE.Mesh {
  return block(Math.abs(x1 - x0), Math.abs(y1 - y0), Math.abs(z1 - z0), m, (x0 + x1) / 2, Math.min(y0, y1), (z0 + z1) / 2)
}

/** A cylinder standing on y; its texture wraps around it at true size. */
export function cylinder(rTop: number, rBottom: number, h: number, m: THREE.Material, x = 0, y = 0, z = 0, segments = 16): THREE.Mesh {
  const geo = new THREE.CylinderGeometry(rTop, rBottom, h, segments, 1)
  const uv = geo.attributes.uv
  const around = Math.PI * (rTop + rBottom)
  for (let i = 0; i < uv.count; i++) uv.setXY(i, uv.getX(i) * around, uv.getY(i) * h)
  return placed(geo, m, x, y + h / 2, z)
}

/** A flat panel facing +z, its texture fitted to it once (a sign, a screen, a picture). */
export function panel(w: number, h: number, m: THREE.Material, x = 0, y = 0, z = 0): THREE.Mesh {
  const mesh = placed(new THREE.PlaneGeometry(w, h), m, x, y, z)
  mesh.castShadow = false
  return mesh
}

/** A sphere. */
export function ball(r: number, m: THREE.Material, x = 0, y = 0, z = 0, detail = 16): THREE.Mesh {
  return placed(meterUV(new THREE.SphereGeometry(r, detail, Math.max(6, detail / 2 + 2))), m, x, y, z)
}

/** A pitched roof over `w` by `d`, `h` high at the ridge (along x), its eaves at y. Shingled on both slopes, with
 * gable ends of `end`. */
export function gable(w: number, d: number, h: number, roof: THREE.Material, end: THREE.Material, x = 0, y = 0, z = 0, overhang = 0.35): THREE.Group {
  const g = new THREE.Group()
  const half = d / 2 + overhang
  const slope = Math.hypot(half, h)
  const angle = Math.atan2(h, half)
  for (const side of [-1, 1]) {
    const s = block(w + overhang * 2, 0.12, slope, roof, 0, 0, 0)
    s.position.set(0, h / 2 - 0.02, (side * half) / 2)
    s.rotation.x = side * angle
    g.add(s)
  }
  const shape = new THREE.Shape()
  shape.moveTo(-d / 2, 0)
  shape.lineTo(d / 2, 0)
  shape.lineTo(0, h)
  shape.closePath()
  for (const side of [-1, 1]) {
    const geo = new THREE.ShapeGeometry(shape)
    geo.rotateY(Math.PI / 2)
    meterUV(geo)
    const tri = placed(geo, end, (side * w) / 2, 0, 0)
    if (side < 0) tri.rotation.y = Math.PI
    g.add(tri)
  }
  g.position.set(x, y, z)
  return g
}

/** Merge a group's still meshes, material by material, into one mesh each (a place drawn in a few calls instead of
 * hundreds). Meshes marked `userData.live` keep moving and are left alone. */
export function bake(root: THREE.Object3D): void {
  root.updateMatrixWorld(true)
  const inverse = root.matrixWorld.clone().invert()
  const groups = new Map<THREE.Material, THREE.BufferGeometry[]>()
  const gone: THREE.Mesh[] = []
  const visit = (o: THREE.Object3D) => {
    if (o.userData.live) return // and everything in it
    for (const c of [...o.children]) visit(c)
    const mesh = o as THREE.Mesh
    if (!mesh.isMesh || (mesh as THREE.InstancedMesh).isInstancedMesh || Array.isArray(mesh.material)) return
    const geo = mesh.geometry.index ? mesh.geometry.toNonIndexed() : mesh.geometry.clone()
    geo.applyMatrix4(new THREE.Matrix4().multiplyMatrices(inverse, mesh.matrixWorld))
    for (const name of Object.keys(geo.attributes)) if (!["position", "normal", "uv"].includes(name)) geo.deleteAttribute(name)
    if (!geo.attributes.uv) geo.setAttribute("uv", new THREE.BufferAttribute(new Float32Array(geo.attributes.position.count * 2), 2))
    if (!geo.attributes.normal) geo.computeVertexNormals()
    const list = groups.get(mesh.material) ?? []
    list.push(geo)
    groups.set(mesh.material, list)
    gone.push(mesh)
  }
  for (const c of [...root.children]) visit(c) // the root's own `live` is for whoever holds it
  for (const mesh of gone) mesh.removeFromParent()
  for (const [mat, list] of groups) {
    const merged = mergeGeometries(list, false)
    if (!merged) continue
    const mesh = new THREE.Mesh(merged, mat)
    mesh.castShadow = !mat.userData.noShadow
    mesh.receiveShadow = true
    root.add(mesh)
  }
}
