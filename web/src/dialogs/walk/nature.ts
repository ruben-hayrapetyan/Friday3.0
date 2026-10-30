// Trees and fallen leaves for the walk (walk/World.ts): late October in a college town. Trees are grown from a seed
// (a trunk, limbs, branches, and cards of leaves at their ends, lit as one round crown), then repeated with
// instancing; the leaves on the ground are scattered cards.

import * as THREE from "three"
import { mergeGeometries } from "three/examples/jsm/utils/BufferGeometryUtils.js"
import { M } from "./props"
import { leaves, type Palette, random } from "./textures"

/** The wind, shared by every swaying thing: seconds. */
export const wind = { value: 0 }

/** A two-sided card lit by its own normal on both faces (a leaf, a blade), not turned dark on its back. */
export const BOTH_SIDES = THREE.ShaderChunk.normal_fragment_begin.replace("normal *= faceDirection;", "")

function swaying(m: THREE.MeshStandardMaterial, strength: number): void {
  m.onBeforeCompile = (shader) => {
    shader.uniforms.uTime = wind
    shader.fragmentShader = shader.fragmentShader.replace("#include <normal_fragment_begin>", BOTH_SIDES)
    shader.vertexShader = shader.vertexShader.replace("#include <common>", "#include <common>\nuniform float uTime;").replace(
      "#include <begin_vertex>",
      `#include <begin_vertex>
      #ifdef USE_INSTANCING
        vec3 rootAt = instanceMatrix[3].xyz;
      #else
        vec3 rootAt = vec3(0.0);
      #endif
      float sway = max(0.0, position.y - 1.5) * ${strength.toFixed(4)};
      float phase = rootAt.x * 0.21 + rootAt.z * 0.17;
      transformed.x += sin(uTime * 1.1 + phase) * sway + sin(uTime * 4.7 + position.z * 3.0 + phase) * sway * 0.25;
      transformed.z += cos(uTime * 0.9 + phase * 1.3) * sway * 0.7;`,
    )
  }
}

interface Tree {
  bark: THREE.BufferGeometry
  leaves: THREE.BufferGeometry
}

/** One tree, grown from `seed`: about `height` metres, its crown `spread` wide. */
function grow(seed: number, height: number, spread: number, cards: number): Tree {
  const rnd = random(seed)
  const bark: THREE.BufferGeometry[] = []
  const tips: THREE.Vector3[] = []
  const up = new THREE.Vector3(0, 1, 0)
  const limb = (from: THREE.Vector3, dir: THREE.Vector3, length: number, radius: number, depth: number) => {
    const to = from.clone().addScaledVector(dir, length)
    const geo = new THREE.CylinderGeometry(radius * 0.62, radius, length, depth === 0 ? 10 : 6, 1, true)
    const uv = geo.attributes.uv
    for (let i = 0; i < uv.count; i++) uv.setXY(i, uv.getX(i) * Math.PI * radius * 1.6, uv.getY(i) * length)
    geo.translate(0, length / 2, 0)
    geo.applyQuaternion(new THREE.Quaternion().setFromUnitVectors(up, dir.clone().normalize()))
    geo.translate(from.x, from.y, from.z)
    bark.push(geo)
    if (depth >= 3) {
      tips.push(to)
      return
    }
    const kids = depth === 0 ? 4 : 3
    for (let k = 0; k < kids; k++) {
      const turn = (k / kids) * Math.PI * 2 + rnd() * 1.2
      const lean = (depth === 0 ? 0.55 : 0.75) + rnd() * 0.35
      const d = new THREE.Vector3(Math.cos(turn) * Math.sin(lean), Math.cos(lean), Math.sin(turn) * Math.sin(lean)).lerp(dir, 0.3).normalize()
      limb(to, d, length * (0.62 + rnd() * 0.2), radius * 0.58, depth + 1)
    }
    if (depth >= 1) tips.push(to)
  }
  limb(new THREE.Vector3(0, 0, 0), new THREE.Vector3((rnd() - 0.5) * 0.08, 1, (rnd() - 0.5) * 0.08).normalize(), height * 0.36, 0.05 * height * 0.6 + 0.08, 0)
  // the crown: cards of leaves round the branch ends, their normals pointing out from the crown's middle
  const centre = new THREE.Vector3()
  for (const t of tips) centre.add(t)
  centre.divideScalar(tips.length)
  centre.y -= 0.6
  const cardsGeo: THREE.BufferGeometry[] = []
  const size = spread * 0.2
  for (let c = 0; c < cards; c++) {
    const tip = tips[Math.floor(rnd() * tips.length)]
    const at = tip.clone().add(new THREE.Vector3((rnd() - 0.5) * spread * 0.32, (rnd() - 0.4) * spread * 0.24, (rnd() - 0.5) * spread * 0.32))
    const geo = new THREE.PlaneGeometry(size * (0.8 + rnd() * 0.5), size * (0.8 + rnd() * 0.5))
    geo.rotateX(rnd() * Math.PI)
    geo.rotateY(rnd() * Math.PI * 2)
    geo.rotateZ((rnd() - 0.5) * 1.2)
    geo.translate(at.x, at.y, at.z)
    const out = at.clone().sub(centre).normalize().lerp(up, 0.25).normalize()
    const nor = geo.attributes.normal
    for (let i = 0; i < nor.count; i++) nor.setXYZ(i, out.x, out.y, out.z)
    cardsGeo.push(geo)
  }
  return { bark: mergeGeometries(bark.map((g) => g.toNonIndexed())) as THREE.BufferGeometry, leaves: mergeGeometries(cardsGeo) as THREE.BufferGeometry }
}

const PALETTES: Palette[] = ["maple", "birch", "oak"]

export interface Planting {
  x: number
  z: number
  size: number
  kind?: number // which of the three trees: maple, birch, oak
}

/** The trees, three kinds repeated: bark and leaves, each kind in two draws. */
export function forest(plantings: Planting[]): THREE.Group {
  const group = new THREE.Group()
  const kinds = PALETTES.map((_, i) => grow(1000 + i * 77, [9, 11, 10][i], [6.5, 5, 7][i], [420, 340, 460][i]))
  const barkMat = M.bark()
  PALETTES.forEach((palette, k) => {
    const mine = plantings.filter((p, i) => (p.kind ?? i % 3) === k)
    if (!mine.length) return
    const tex = leaves(palette)
    const leafMat = new THREE.MeshStandardMaterial({ map: tex, alphaTest: 0.45, side: THREE.DoubleSide, roughness: 0.75, envMapIntensity: 0.8 })
    swaying(leafMat, 0.012)
    const trunks = new THREE.InstancedMesh(kinds[k].bark, barkMat, mine.length)
    const crowns = new THREE.InstancedMesh(kinds[k].leaves, leafMat, mine.length)
    crowns.customDepthMaterial = new THREE.MeshDepthMaterial({ depthPacking: THREE.RGBADepthPacking, map: tex, alphaTest: 0.45 })
    const m = new THREE.Matrix4()
    const q = new THREE.Quaternion()
    const tint = new THREE.Color()
    mine.forEach((p, i) => {
      q.setFromAxisAngle(new THREE.Vector3(0, 1, 0), (p.x * 13.7 + p.z * 7.3) % (Math.PI * 2))
      m.compose(new THREE.Vector3(p.x, 0.1, p.z), q, new THREE.Vector3(p.size, p.size, p.size))
      trunks.setMatrixAt(i, m)
      crowns.setMatrixAt(i, m)
      const v = 0.86 + (((p.x * 31 + p.z * 17) % 7) + 7) / 7 / 4
      crowns.setColorAt(i, tint.setRGB(v, v, v))
    })
    for (const mesh of [trunks, crowns]) {
      mesh.castShadow = true
      mesh.receiveShadow = true
      mesh.computeBoundingSphere()
      group.add(mesh)
    }
    crowns.userData.noAO = true
  })
  return group
}

/** Far woods and hills, in the haze: low, round, autumn-coloured. */
export function woods(along: [number, number]): THREE.Group {
  const group = new THREE.Group()
  const rnd = random(4242)
  const geo = new THREE.IcosahedronGeometry(1, 2)
  const pos = geo.attributes.position
  for (let i = 0; i < pos.count; i++) {
    const v = new THREE.Vector3().fromBufferAttribute(pos, i)
    v.multiplyScalar(0.85 + 0.3 * Math.abs(Math.sin(v.x * 5.1 + v.y * 3.7) * Math.cos(v.z * 4.3)))
    pos.setXYZ(i, v.x, v.y, v.z)
  }
  geo.computeVertexNormals()
  const mat = new THREE.MeshStandardMaterial({ roughness: 1, envMapIntensity: 0.6 })
  const count = 520
  const crowns = new THREE.InstancedMesh(geo, mat, count)
  const colors = [0x9c3b1e, 0xb8641e, 0xc99a2a, 0x6d6a24, 0x8a4a1c, 0x5f6b2c, 0xa8501c]
  const m = new THREE.Matrix4()
  const c = new THREE.Color()
  for (let i = 0; i < count; i++) {
    const side = i % 2 ? 1 : -1
    const x = side * (40 + rnd() * 120)
    const z = along[0] + 60 - rnd() * (along[0] - along[1] + 160)
    const s = 4 + rnd() * 4
    m.compose(new THREE.Vector3(x, s * 0.9, z), new THREE.Quaternion(), new THREE.Vector3(s, s * 1.15, s))
    crowns.setMatrixAt(i, m)
    crowns.setColorAt(i, c.setHex(colors[Math.floor(rnd() * colors.length)]))
  }
  crowns.userData.noAO = true
  group.add(crowns)
  // the hills round the valley
  const hillMat = new THREE.MeshStandardMaterial({ color: 0x5d5a2e, roughness: 1, envMapIntensity: 0.5 })
  for (let i = 0; i < 14; i++) {
    const side = i % 2 ? 1 : -1
    const hill = new THREE.Mesh(new THREE.SphereGeometry(1, 24, 12), hillMat)
    hill.scale.set(140 + rnd() * 90, 40 + rnd() * 30, 120 + rnd() * 80)
    hill.position.set(side * (230 + rnd() * 100), -12, along[0] + 100 - i * ((along[0] - along[1] + 200) / 14))
    group.add(hill)
  }
  return group
}

/** Where nothing grows: the road, paths, floors (world rectangles: minX, minZ, maxX, maxZ). */
export type Clear = [number, number, number, number]

/** Leaves fallen on the lawns and the edges of the road, a few hundred cards lying flat. */
export function fallen(spots: [number, number][]): THREE.Group {
  const group = new THREE.Group()
  const rnd = random(99)
  PALETTES.forEach((palette, k) => {
    const mine = spots.filter((_, i) => i % 3 === k)
    const mat = new THREE.MeshStandardMaterial({ map: leaves(palette), alphaTest: 0.5, roughness: 0.85, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: -2 })
    const geo = new THREE.PlaneGeometry(0.55, 0.55).rotateX(-Math.PI / 2)
    const mesh = new THREE.InstancedMesh(geo, mat, mine.length)
    const m = new THREE.Matrix4()
    mine.forEach(([x, z], i) => {
      m.compose(new THREE.Vector3(x, 0.135 + rnd() * 0.01, z), new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), rnd() * 6.3), new THREE.Vector3(1, 1, 1).multiplyScalar(0.6 + rnd() * 0.7))
      mesh.setMatrixAt(i, m)
    })
    mesh.receiveShadow = true
    mesh.userData.noAO = true
    group.add(mesh)
  })
  return group
}
