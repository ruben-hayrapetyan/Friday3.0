// The street the walk goes up (walk/World.ts): asphalt with its painted lines, curbs, the grass strip with its trees and
// lamps, sidewalks, houses with porches between the places, a second row behind, power lines along one side.

import * as THREE from "three"
import type { Clear, Planting } from "./nature"
import { FRONT, SIDEWALK, type Socket } from "./places"
import { bake, ball, block, cylinder, gable, M, panel, span } from "./props"
import { random } from "./textures"

export interface Lot {
  z: number // where along the street
  side: number // 1 east, -1 west
  w: number // its width along the street
  d: number // and depth back from the front
  paths: number[] // where paths cross the grass strip to it (z)
}

export interface Town {
  group: THREE.Group
  clear: Clear[]
  sockets: Socket[]
  trees: Planting[]
  leaves: [number, number][]
}

const CURB = 3.5
const STRIP = 3.65

const SIDINGS = [0xf1ede4, 0xb9c8d6, 0xc9d3b4, 0xe8d8b0, 0xa9b0b8, 0xd9b8a8, 0x8fa6a0]
const ROOFS = [0x5a5a5e, 0x7a6a62, 0x6a7a80, 0x4e4a48]
const DOORS = [0x8a2f2a, 0x23364a, 0x2f4a3a, 0x1d1d1d, 0x6a4a2a]

/** A house: two storeys of siding, a porch, a gabled roof, windows and a door, facing +z. */
function house(seed: number): { group: THREE.Group; w: number; d: number; door: number } {
  const rnd = random(seed)
  const g = new THREE.Group()
  const w = 7 + rnd() * 2.5
  const d = 7.5 + rnd() * 2
  const floors = rnd() > 0.3 ? 2 : 1
  const wall = M.siding(SIDINGS[Math.floor(rnd() * SIDINGS.length)])
  const trim = M.paint(0xf3f0e8, 0.5)
  const top = 0.6 + floors * 2.9
  g.add(span(-w / 2, w / 2, 0, 0.6, -d, 0, M.brickPale()))
  g.add(span(-w / 2, w / 2, 0.6, top, -d, 0, wall))
  for (const x of [-w / 2, w / 2]) g.add(span(x - 0.08, x + 0.08, 0.6, top, -0.08, 0.02, trim))
  g.add(gable(w, d, 2.6 + rnd() * 1.2, M.shingles(ROOFS[Math.floor(rnd() * ROOFS.length)]), wall, 0, top, -d / 2, 0.45))
  const glass = M.window()
  const lit = M.windowLit(0xffc98a)
  const windowAt = (x: number, y: number) => {
    const on = rnd() > 0.55
    g.add(panel(0.9, 1.3, on ? lit : glass, x, y + 0.65, 0.025))
    g.add(span(x - 0.52, x + 0.52, y - 0.08, y, 0, 0.1, trim), span(x - 0.52, x + 0.52, y + 1.3, y + 1.42, 0, 0.06, trim))
    g.add(span(x - 0.52, x - 0.45, y, y + 1.3, 0, 0.06, trim), span(x + 0.45, x + 0.52, y, y + 1.3, 0, 0.06, trim))
    g.add(span(x - 0.02, x + 0.02, y, y + 1.3, 0, 0.04, trim))
    if (rnd() > 0.5) for (const s of [-1, 1]) g.add(span(x + s * 0.55, x + s * 0.95, y, y + 1.3, 0, 0.05, M.paint(DOORS[Math.floor(rnd() * DOORS.length)], 0.55)))
  }
  const doorX = (rnd() > 0.5 ? 1 : -1) * (w / 2 - 1.6)
  for (let f = 0; f < floors; f++) {
    const y = 0.6 + f * 2.9 + 0.85
    for (const x of [-w / 2 + 1.6, 0, w / 2 - 1.6]) if (f > 0 || Math.abs(x - doorX) > 0.9) windowAt(x, y)
  }
  g.add(span(doorX - 0.5, doorX + 0.5, 0.6, 2.75, 0, 0.03, M.paint(DOORS[Math.floor(rnd() * DOORS.length)], 0.45)))
  g.add(span(doorX - 0.62, doorX + 0.62, 0.6, 2.87, -0.01, 0.06, trim))
  // the porch: a deck, posts, a roof
  if (rnd() > 0.35) {
    g.add(span(-w / 2 + 0.3, w / 2 - 0.3, 0, 0.6, 0, 2.2, M.wood(0x9a8a78)))
    for (const x of [-w / 2 + 0.45, -w / 6, w / 6, w / 2 - 0.45]) g.add(block(0.14, 2.4, 0.14, trim, x, 0.6, 2.05))
    g.add(span(-w / 2 + 0.2, w / 2 - 0.2, 3.0, 3.12, -0.1, 2.35, trim))
    const porchRoof = span(-w / 2 + 0.1, w / 2 - 0.1, 3.12, 3.2, -0.1, 2.45, M.shingles(ROOFS[1]))
    g.add(porchRoof)
    g.add(span(-w / 2 + 0.4, w / 2 - 0.4, 1.4, 1.46, 2.0, 2.1, trim))
  }
  g.add(span(doorX - 0.7, doorX + 0.7, 0, 0.6, 2.2, 2.9, M.concrete()))
  return { group: g, w, d, door: doorX }
}

/** The street from `from` to `to` (z), with the places' lots kept free. */
export function street(from: number, to: number, lots: Lot[]): Town {
  const group = new THREE.Group()
  const clear: Clear[] = []
  const sockets: Socket[] = []
  const trees: Planting[] = []
  const leaves: [number, number][] = []
  const length = from - to
  const mid = (from + to) / 2
  const rnd = random(2026)
  // the road, its lines, the curbs
  const road = span(-CURB, CURB, -0.3, 0, to, from, M.asphalt())
  road.castShadow = false
  group.add(road)
  const paint = (color: number) => {
    const m = new THREE.MeshStandardMaterial({ color, roughness: 0.75, polygonOffset: true, polygonOffsetFactor: -1 })
    return m
  }
  for (const x of [-0.09, 0.09]) group.add(flat(0.1, length, paint(0xd9a826), x, 0.002, mid))
  for (const x of [-3.15, 3.15]) group.add(flat(0.12, length, paint(0xe9e6de), x, 0.002, mid))
  for (const z of [4, to + 30]) for (let i = -3; i <= 3; i++) group.add(flat(0.5, 2.8, paint(0xeceae2), i * 0.95, 0.003, z))
  for (const side of [-1, 1]) {
    group.add(span(side * CURB, side * STRIP, -0.3, 0.15, to, from, M.concrete()))
    // the grass, from the curb outward, a little below the sidewalk
    const lawn = new THREE.Mesh(new THREE.PlaneGeometry(600, length + 400).rotateX(-Math.PI / 2), M.lawn())
    const uv = lawn.geometry.attributes.uv
    for (let i = 0; i < uv.count; i++) uv.setXY(i, uv.getX(i) * 600, uv.getY(i) * (length + 400))
    lawn.position.set(side * (STRIP + 300), 0.12, mid)
    lawn.receiveShadow = true
    group.add(lawn)
    group.add(span(side * SIDEWALK[0], side * SIDEWALK[1], 0, 0.16, to, from, M.concrete()))
    clear.push(side > 0 ? [SIDEWALK[0] - 0.05, to, SIDEWALK[1] + 0.05, from] : [-SIDEWALK[1] - 0.05, to, -SIDEWALK[0] + 0.05, from])
  }
  clear.push([-STRIP, to, STRIP, from])
  const near = (z: number, side: number, room: number) => lots.some((l) => l.side === side && Math.abs(l.z - z) < l.w / 2 + room)
  const onPath = (z: number, side: number) => lots.some((l) => l.side === side && l.paths.some((p) => Math.abs(l.z + p - z) < 2.2))
  // houses in the gaps, and a row behind
  let seed = 1
  for (const side of [-1, 1]) {
    let z = from - 6
    while (z > to + 6) {
      const h = house(seed++)
      if (!near(z - h.w / 2, side, h.w / 2 + 2)) {
        const x = side * (FRONT + 1.5 + rnd() * 1.5)
        h.group.position.set(x, 0.12, z - h.w / 2)
        h.group.rotation.y = -side * (Math.PI / 2)
        group.add(h.group)
        const ax = Math.abs(x)
        const doorZ = z - h.w / 2 + side * h.door
        clear.push(side > 0 ? [ax - 3, z - h.w - 0.2, ax + h.d + 0.2, z + 0.2] : [-ax - h.d - 0.2, z - h.w - 0.2, -ax + 3, z + 0.2])
        clear.push(side > 0 ? [SIDEWALK[1], doorZ - 0.8, ax, doorZ + 0.8] : [-ax, doorZ - 0.8, -SIDEWALK[1], doorZ + 0.8])
        group.add(span(side * SIDEWALK[1], side * (ax - 2.8), 0, 0.15, doorZ - 0.6, doorZ + 0.6, M.concrete()))
        if (rnd() > 0.4) trees.push({ x: side * (Math.abs(x) + h.d + 3 + rnd() * 3), z: z - rnd() * h.w, size: 0.9 + rnd() * 0.4 })
      }
      z -= h.w + 3 + rnd() * 4
    }
    z = from - 2
    while (z > to + 6) {
      const h = house(seed++)
      const x = side * (34 + rnd() * 6)
      if (!lots.some((l) => l.side === side && Math.abs(l.z - z) < l.w / 2 + h.w && FRONT + l.d > Math.abs(x) - 2)) {
        h.group.position.set(x, 0.12, z - h.w / 2)
        h.group.rotation.y = -side * (Math.PI / 2)
        group.add(h.group)
      }
      z -= h.w + 6 + rnd() * 6
    }
  }
  // street trees in the grass strip, lamps, hydrants
  for (const side of [-1, 1]) {
    for (let z = from - 4; z > to + 4; z -= 9 + rnd() * 3) {
      if (onPath(z, side) || (side < 0 && Math.min(((((from - 2 - z) % 36) + 36) % 36), 36 - ((((from - 2 - z) % 36) + 36) % 36)) < 2)) continue
      trees.push({ x: side * 4.4, z, size: 0.85 + rnd() * 0.35 })
      for (let k = 0; k < 14; k++) leaves.push([side * (3.4 + rnd() * 4), z + (rnd() - 0.5) * 9])
    }
    for (let z = from - 14 + (side > 0 ? 0 : 13); z > to; z -= 26) {
      if (onPath(z, side)) continue
      const lamp = new THREE.Group()
      lamp.add(cylinder(0.14, 0.18, 0.5, M.metal(0x1c241f, 0.55), 0, 0, 0, 12))
      lamp.add(cylinder(0.06, 0.08, 3.4, M.metal(0x1c241f, 0.55), 0, 0.5, 0, 12))
      lamp.add(cylinder(0.12, 0.08, 0.16, M.metal(0x1c241f, 0.55), 0, 3.9, 0, 12))
      lamp.add(ball(0.22, M.lamp(), 0, 4.3, 0, 18))
      lamp.add(cylinder(0.04, 0.18, 0.16, M.metal(0x1c241f, 0.55), 0, 4.48, 0, 12))
      lamp.position.set(side * 5.0, 0.12, z)
      group.add(lamp)
      sockets.push({ at: new THREE.Vector3(side * 5.0, 4.2, z), color: 0xffcf8f, power: 22, range: 16, night: true })
    }
    for (let z = from - 30; z > to; z -= 70) {
      if (onPath(z, side)) continue
      const hydrant = new THREE.Group()
      const red = M.paint(0xb3261e, 0.45)
      hydrant.add(cylinder(0.13, 0.13, 0.55, red, 0, 0, 0, 14), ball(0.13, red, 0, 0.55, 0, 12), cylinder(0.05, 0.05, 0.32, red, 0, 0.32, 0, 10).rotateZ(Math.PI / 2))
      hydrant.position.set(side * 4.0, 0.12, z)
      group.add(hydrant)
    }
  }
  // gutters full of leaves
  for (let i = 0; i < 900; i++) leaves.push([(rnd() > 0.5 ? 1 : -1) * (3.0 + rnd() * 0.45), to + rnd() * length])
  for (let i = 0; i < 700; i++) leaves.push([(rnd() > 0.5 ? 1 : -1) * (5.1 + rnd() * 1.8), to + rnd() * length])
  // power lines down the west side
  const poles: THREE.Vector3[] = []
  for (let z = from - 2; z > to; z -= 36) {
    const pole = new THREE.Group()
    const wood = M.wood(0x6a5a4a)
    pole.add(cylinder(0.12, 0.16, 9, wood, 0, 0, 0, 10))
    pole.add(block(2.4, 0.12, 0.12, wood, 0, 8.2, 0))
    for (const x of [-1.0, 0, 1.0]) pole.add(cylinder(0.04, 0.05, 0.16, M.paint(0x3a5a4a, 0.3), x, 8.32, 0, 8))
    pole.position.set(-4.6, 0.12, z)
    group.add(pole)
    poles.push(new THREE.Vector3(-4.6, 8.62, z))
  }
  const wire = new THREE.LineBasicMaterial({ color: 0x1a1a1a })
  for (const dx of [-1.0, 0, 1.0]) {
    for (let i = 1; i < poles.length; i++) {
      const a = poles[i - 1].clone().setX(-4.6 + dx)
      const b = poles[i].clone().setX(-4.6 + dx)
      const points: THREE.Vector3[] = []
      for (let k = 0; k <= 16; k++) {
        const t = k / 16
        points.push(a.clone().lerp(b, t).setY(a.y - Math.sin(Math.PI * t) * 0.9))
      }
      group.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(points), wire))
    }
  }
  bakeHouses(group)
  return { group, clear, sockets, trees, leaves }
}

/** Paint on the road: a strip `w` wide and `l` long, lying flat. */
function flat(w: number, l: number, m: THREE.Material, x: number, y: number, z: number): THREE.Mesh {
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(w, l).rotateX(-Math.PI / 2), m)
  mesh.position.set(x, y, z)
  mesh.receiveShadow = true
  return mesh
}

/** Everything still on the street merged, material by material. */
function bakeHouses(group: THREE.Group): void {
  bake(group)
}
