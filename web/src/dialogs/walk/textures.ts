// The walk's surfaces, made rather than downloaded (Friday runs offline): asphalt, concrete, brick, siding, shingles,
// wood, plaster, grass, bark, autumn leaves. Each is a tile of real size with its colour, its bumps (a normal map, from
// a height field) and how rough it is, generated from noise once when the walk opens.

import * as THREE from "three"

export interface Surface {
  map: THREE.Texture
  normalMap: THREE.Texture
  roughnessMap: THREE.Texture
}

/** A repeatable random stream. */
export function random(seed: number): () => number {
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) >>> 0
    let t = a
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

/** A fixed random number for a cell. */
export function hash(x: number, y: number, seed = 0): number {
  let h = Math.imul(x | 0, 374761393) + Math.imul(y | 0, 668265263) + Math.imul(seed | 0, 1442695041)
  h = Math.imul(h ^ (h >>> 13), 1274126177)
  return ((h ^ (h >>> 16)) >>> 0) / 4294967296
}

/** Noise that tiles: `size` pixels square, `cells` features across at the coarsest, octaves halving. 0 to 1. */
export function fbm(size: number, cells: number, octaves: number, seed: number, gain = 0.5, stretch: [number, number] = [1, 1]): Float32Array {
  const out = new Float32Array(size * size)
  let amp = 1
  let total = 0
  for (let o = 0; o < octaves; o++) {
    const px = Math.max(1, Math.round(cells * stretch[0])) << o
    const py = Math.max(1, Math.round(cells * stretch[1])) << o
    const lat = new Float32Array(px * py)
    for (let k = 0; k < lat.length; k++) lat[k] = hash(k % px, Math.floor(k / px), seed + o * 7919)
    for (let j = 0; j < size; j++) {
      const fy = (j / size) * py
      const y0 = Math.floor(fy)
      const ty = fy - y0
      const sy = ty * ty * (3 - 2 * ty)
      const r0 = (y0 % py) * px
      const r1 = ((y0 + 1) % py) * px
      for (let i = 0; i < size; i++) {
        const fx = (i / size) * px
        const x0 = Math.floor(fx)
        const tx = fx - x0
        const sx = tx * tx * (3 - 2 * tx)
        const x1 = (x0 + 1) % px
        const a = lat[r0 + x0] + (lat[r0 + x1] - lat[r0 + x0]) * sx
        const b = lat[r1 + x0] + (lat[r1 + x1] - lat[r1 + x0]) * sx
        out[j * size + i] += amp * (a + (b - a) * sy)
      }
    }
    total += amp
    amp *= gain
  }
  for (let k = 0; k < out.length; k++) out[k] /= total
  return out
}

function texture(data: Uint8Array, size: number, unit: [number, number], srgb: boolean): THREE.DataTexture {
  const t = new THREE.DataTexture(data, size, size, THREE.RGBAFormat)
  t.wrapS = t.wrapT = THREE.RepeatWrapping
  t.magFilter = THREE.LinearFilter
  t.minFilter = THREE.LinearMipmapLinearFilter
  t.generateMipmaps = true
  t.anisotropy = 8
  if (srgb) t.colorSpace = THREE.SRGBColorSpace
  t.repeat.set(1 / unit[0], 1 / unit[1])
  t.needsUpdate = true
  return t
}

/** A surface from a function giving, at each pixel (u, v from 0 to 1), its colour (0-255), height (0-1) and
 * roughness (0-1). `bump` is how steep the heights are. Rows go up the tile (v), as texture coordinates do. */
export function surface(size: number, unit: [number, number], bump: number, at: (i: number, j: number) => [number, number, number, number, number]): Surface {
  const color = new Uint8Array(size * size * 4)
  const rough = new Uint8Array(size * size * 4)
  const height = new Float32Array(size * size)
  for (let j = 0; j < size; j++) {
    for (let i = 0; i < size; i++) {
      const [r, g, b, h, ro] = at(i, j)
      const k = j * size + i
      color[k * 4] = r
      color[k * 4 + 1] = g
      color[k * 4 + 2] = b
      color[k * 4 + 3] = 255
      height[k] = h
      const rv = Math.max(0, Math.min(255, ro * 255))
      rough[k * 4] = rv
      rough[k * 4 + 1] = rv
      rough[k * 4 + 2] = rv
      rough[k * 4 + 3] = 255
    }
  }
  return { map: texture(color, size, unit, true), normalMap: texture(normals(height, size, bump), size, unit, false), roughnessMap: texture(rough, size, unit, false) }
}

/** A tangent-space normal map from heights. */
export function normals(height: Float32Array, size: number, bump: number): Uint8Array {
  const out = new Uint8Array(size * size * 4)
  for (let j = 0; j < size; j++) {
    for (let i = 0; i < size; i++) {
      const l = height[j * size + ((i - 1 + size) % size)]
      const r = height[j * size + ((i + 1) % size)]
      const d = height[((j - 1 + size) % size) * size + i]
      const u = height[((j + 1) % size) * size + i]
      const nx = (l - r) * bump
      const ny = (d - u) * bump
      const len = Math.hypot(nx, ny, 1)
      const k = (j * size + i) * 4
      out[k] = ((nx / len) * 0.5 + 0.5) * 255
      out[k + 1] = ((ny / len) * 0.5 + 0.5) * 255
      out[k + 2] = ((1 / len) * 0.5 + 0.5) * 255
      out[k + 3] = 255
    }
  }
  return out
}

const clamp = (v: number) => Math.max(0, Math.min(255, v))
const made = new Map<string, Surface>()
function once(key: string, make: () => Surface): Surface {
  const found = made.get(key)
  if (found) return found
  const s = make()
  made.set(key, s)
  return s
}

/** Road: dark aggregate, old patches, a sheen where it's worn. 4m. */
export const asphalt = () =>
  once("asphalt", () => {
    const n = 256
    const low = fbm(n, 3, 4, 11)
    const fine = fbm(n, 64, 2, 12)
    return surface(n, [4, 4], 6, (i, j) => {
      const k = j * n + i
      const grit = hash(i, j, 3)
      const stone = grit > 0.93 ? 34 : grit < 0.05 ? -22 : 0
      const patch = low[k] > 0.62 ? -12 : 0
      const v = 58 + (low[k] - 0.5) * 22 + (fine[k] - 0.5) * 18 + stone + patch
      return [clamp(v), clamp(v + 1), clamp(v + 3), fine[k] * 0.5 + (grit > 0.93 ? 0.4 : 0), 0.82 + fine[k] * 0.15 - (patch ? 0.08 : 0)]
    })
  })

/** Sidewalk: a concrete slab with its joints, 1.5m square. */
export const concrete = () =>
  once("concrete", () => {
    const n = 256
    const low = fbm(n, 4, 4, 21)
    const fine = fbm(n, 96, 2, 22)
    return surface(n, [1.5, 1.5], 5, (i, j) => {
      const k = j * n + i
      const edge = Math.min(i, n - 1 - i, j, n - 1 - j)
      const joint = edge < 3
      const v = 178 + (low[k] - 0.5) * 30 + (fine[k] - 0.5) * 16 - (joint ? 55 : 0) - (hash(i, j, 5) > 0.97 ? 20 : 0)
      return [clamp(v + 2), clamp(v), clamp(v - 5), (joint ? 0 : 0.6) + fine[k] * 0.15, joint ? 1 : 0.86 + fine[k] * 0.1]
    })
  })

/** A lawn in late October: green going tired, with brown and the first fallen leaves. 4m. */
export const lawn = () =>
  once("lawn", () => {
    const n = 256
    const low = fbm(n, 5, 4, 31)
    const fine = fbm(n, 128, 2, 32)
    const leaves = fbm(n, 24, 2, 33)
    return surface(n, [4, 4], 3, (i, j) => {
      const k = j * n + i
      const dry = low[k]
      let r = 62 + dry * 50 + (fine[k] - 0.5) * 40
      let g = 88 + dry * 30 + (fine[k] - 0.5) * 46
      let b = 34 + dry * 10
      const leaf = leaves[k] > 0.72 && hash(i >> 2, j >> 2, 34) > 0.45
      if (leaf) {
        const hue = hash(i >> 3, j >> 3, 35)
        r = 170 + hue * 60
        g = 60 + hue * 90
        b = 25
      }
      return [clamp(r), clamp(g), clamp(b), fine[k] + (leaf ? 0.3 : 0), 0.95]
    })
  })

/** Red brick in running bond, 1.2m square: 6 bricks across, 16 courses. */
export const brick = (tone: "red" | "pale" = "red") =>
  once(`brick-${tone}`, () => {
    const n = 256
    const fine = fbm(n, 80, 3, 41)
    const low = fbm(n, 6, 3, 42)
    const base = tone === "red" ? [146, 66, 48] : [190, 150, 118]
    return surface(n, [1.2, 1.2], 9, (i, j) => {
      const k = j * n + i
      const fv = (j / n) * 16
      const row = Math.floor(fv)
      const fu = (i / n) * 6 + (row % 2 ? 0.5 : 0)
      const col = Math.floor(fu) % 6
      const du = Math.min(fu - Math.floor(fu), 1 - (fu - Math.floor(fu))) * 0.2
      const dv = Math.min(fv - row, 1 - (fv - row)) * 0.075
      const mortar = du < 0.006 || dv < 0.006
      if (mortar) {
        const m = 168 + (fine[k] - 0.5) * 40
        return [clamp(m), clamp(m - 4), clamp(m - 12), 0.1 + fine[k] * 0.1, 0.97]
      }
      const shade = 0.78 + hash(col, row, 43) * 0.38 - (hash(col, row, 44) > 0.9 ? 0.25 : 0)
      const spot = (fine[k] - 0.5) * 34 + (low[k] - 0.5) * 20
      const bevel = Math.min(1, Math.min(du, dv) / 0.012)
      return [clamp(base[0] * shade + spot), clamp(base[1] * shade + spot * 0.7), clamp(base[2] * shade + spot * 0.6), 0.45 + bevel * 0.4 + fine[k] * 0.15, 0.82 + fine[k] * 0.1]
    })
  })

/** Painted clapboard: 15cm boards, each lapping over the one below. Pale, to be tinted. 1.2m. */
export const siding = () =>
  once("siding", () => {
    const n = 256
    const grain = fbm(n, 6, 3, 51, 0.5, [8, 0.5])
    return surface(n, [1.2, 1.2], 7, (i, j) => {
      const k = j * n + i
      const fv = (j / n) * 8
      const t = fv - Math.floor(fv) // 0 at a board's bottom edge, 1 at its top
      const shadow = t < 0.06 ? 0.72 : 1
      const v = (236 + (grain[k] - 0.5) * 14) * shadow
      return [clamp(v), clamp(v), clamp(v - 2), 1 - t * 0.85 + grain[k] * 0.05, 0.55 + grain[k] * 0.1]
    })
  })

/** Limestone ashlar, 1.2m square: blocks 60cm by 30cm. */
export const stone = () =>
  once("stone", () => {
    const n = 256
    const fine = fbm(n, 64, 3, 61)
    const low = fbm(n, 8, 3, 62)
    return surface(n, [1.2, 1.2], 7, (i, j) => {
      const k = j * n + i
      const fv = (j / n) * 4
      const row = Math.floor(fv)
      const fu = (i / n) * 2 + (row % 2 ? 0.5 : 0)
      const col = Math.floor(fu) % 2
      const du = Math.min(fu - Math.floor(fu), 1 - (fu - Math.floor(fu))) * 0.6
      const dv = Math.min(fv - row, 1 - (fv - row)) * 0.3
      if (du < 0.006 || dv < 0.006) return [150, 144, 132, 0.1, 0.95]
      const s = 0.9 + hash(col, row, 63) * 0.14
      const v = (205 + (low[k] - 0.5) * 26 + (fine[k] - 0.5) * 22) * s
      return [clamp(v), clamp(v - 8), clamp(v - 26), 0.5 + fine[k] * 0.3, 0.88]
    })
  })

/** Asphalt shingles: rows of three tabs, 1m square, dark. */
export const shingles = () =>
  once("shingles", () => {
    const n = 256
    const fine = fbm(n, 128, 2, 71)
    return surface(n, [1, 1], 8, (i, j) => {
      const k = j * n + i
      const fv = (j / n) * 5
      const row = Math.floor(fv)
      const t = fv - row
      const fu = (i / n) * 3 + (row % 2 ? 0.5 : 0)
      const gap = Math.abs(fu - Math.round(fu)) < 0.012
      const tone = 0.85 + hash(Math.floor(fu), row, 72) * 0.3
      const v = (70 + (fine[k] - 0.5) * 40) * tone * (t < 0.08 ? 0.6 : 1) * (gap ? 0.55 : 1)
      return [clamp(v + 4), clamp(v), clamp(v - 2), gap ? 0 : t * 0.7 + fine[k] * 0.2, 0.92]
    })
  })

/** Oak floorboards, 14cm wide, of different lengths, varnished. 2m. */
export const floorboards = () =>
  once("floor", () => {
    const n = 256
    const grain = fbm(n, 4, 4, 81, 0.55, [1, 14])
    return surface(n, [2, 2], 4, (i, j) => {
      const k = j * n + i
      const lanes = 14
      const fl = (i / n) * lanes
      const lane = Math.floor(fl)
      const across = Math.min(fl - lane, 1 - (fl - lane))
      const len = 0.45 + hash(lane, 0, 82) * 0.4
      const along = (j / n + hash(lane, 1, 83)) / len
      const seg = Math.floor(along)
      const end = Math.min(along - seg, 1 - (along - seg)) * len < 0.004
      const tone = 0.8 + hash(lane, seg, 84) * 0.35
      const ring = Math.sin(grain[k] * 40) * 0.5 + 0.5
      const seam = across < 0.04 || end
      const v = seam ? 0.55 : tone * (0.86 + ring * 0.14)
      return [clamp(176 * v), clamp(124 * v), clamp(78 * v), seam ? 0 : 0.6 + ring * 0.05, seam ? 0.8 : 0.38 + ring * 0.12]
    })
  })

/** Wood for furniture: long grain, mid brown. 1m. */
export const wood = () =>
  once("wood", () => {
    const n = 128
    const grain = fbm(n, 3, 4, 91, 0.55, [1, 10])
    return surface(n, [1, 1], 2, (i, j) => {
      const k = j * n + i
      const ring = Math.sin(grain[k] * 34) * 0.5 + 0.5
      const v = 0.82 + ring * 0.18
      return [clamp(150 * v), clamp(98 * v), clamp(60 * v), ring * 0.3, 0.5 + ring * 0.15]
    })
  })

/** Painted plaster: nearly flat, a little uneven. White, to be tinted. 2m. */
export const plaster = () =>
  once("plaster", () => {
    const n = 128
    const low = fbm(n, 6, 4, 101)
    return surface(n, [2, 2], 1.5, (i, j) => {
      const k = j * n + i
      const v = 238 + (low[k] - 0.5) * 10
      return [clamp(v), clamp(v - 1), clamp(v - 3), low[k], 0.9]
    })
  })

/** Woven fabric for upholstery and bedding, white to be tinted. 40cm. */
export const fabric = () =>
  once("fabric", () => {
    const n = 128
    const low = fbm(n, 8, 3, 111)
    return surface(n, [0.4, 0.4], 3, (i, j) => {
      const k = j * n + i
      const weave = (Math.sin(i * 1.6) * Math.sin(j * 1.6)) * 0.5 + 0.5
      const v = 222 + (weave - 0.5) * 26 + (low[k] - 0.5) * 18
      return [clamp(v), clamp(v), clamp(v), weave * 0.6 + low[k] * 0.4, 0.95]
    })
  })

/** Bark: grey-brown, furrowed upward. 1m. */
export const bark = () =>
  once("bark", () => {
    const n = 128
    const furrow = fbm(n, 6, 4, 121, 0.5, [1, 0.25])
    const fine = fbm(n, 48, 2, 122)
    return surface(n, [0.8, 1.6], 10, (i, j) => {
      const k = j * n + i
      const f = furrow[k]
      const v = 70 + f * 60 + (fine[k] - 0.5) * 24
      return [clamp(v + 6), clamp(v), clamp(v - 8), f * 0.8 + fine[k] * 0.2, 0.93]
    })
  })

/** Cork, for the notice board. 1m. */
export const cork = () =>
  once("cork", () => {
    const n = 128
    const fine = fbm(n, 64, 3, 131)
    return surface(n, [0.6, 0.6], 4, (i, j) => {
      const k = j * n + i
      const v = fine[k]
      return [clamp(150 + v * 70), clamp(102 + v * 52), clamp(58 + v * 30), v, 0.95]
    })
  })

/** Carpet: short pile, white to be tinted. 1m. */
export const carpet = () =>
  once("carpet", () => {
    const n = 128
    const fine = fbm(n, 96, 2, 141)
    const low = fbm(n, 6, 2, 142)
    return surface(n, [1, 1], 3, (i, j) => {
      const k = j * n + i
      const v = 210 + (fine[k] - 0.5) * 50 + (low[k] - 0.5) * 16
      return [clamp(v), clamp(v), clamp(v), fine[k], 1]
    })
  })

export type Palette = "maple" | "birch" | "oak"

const LEAF_COLORS: Record<Palette, string[]> = {
  maple: ["#b8321e", "#cf4a1f", "#e0681f", "#a2261c", "#d9532a", "#8e2a1c", "#e88a2a"],
  birch: ["#e2b42c", "#d39b1c", "#f0c94a", "#c98c18", "#e7bf3a", "#b5862a", "#d6a832"],
  oak: ["#a8742a", "#8a5a22", "#c48a2c", "#6f7a2a", "#9c6a1e", "#b77d34", "#7e8c32"],
}

/** A spray of leaves on a transparent card, for the trees and for the ones on the ground. */
export function leaves(palette: Palette): THREE.CanvasTexture {
  const canvas = document.createElement("canvas")
  canvas.width = canvas.height = 512
  const ctx = canvas.getContext("2d")
  if (ctx) {
    const rnd = random(palette.length * 977 + 3)
    const colors = LEAF_COLORS[palette]
    for (let n = 0; n < 70; n++) {
      const x = 50 + rnd() * 412
      const y = 50 + rnd() * 412
      const s = 26 + rnd() * 34
      ctx.save()
      ctx.translate(x, y)
      ctx.rotate(rnd() * Math.PI * 2)
      ctx.fillStyle = colors[Math.floor(rnd() * colors.length)]
      ctx.beginPath()
      if (palette === "maple") {
        // five points, the way a maple leaf has them
        for (let p = 0; p <= 10; p++) {
          const a = -Math.PI / 2 + (p / 10) * Math.PI * 2
          const r = p % 2 === 0 ? s : s * 0.48
          ctx.lineTo(Math.cos(a) * r, Math.sin(a) * r)
        }
      } else {
        ctx.moveTo(0, -s)
        ctx.quadraticCurveTo(s * 0.55, -s * 0.2, 0, s * 0.85)
        ctx.quadraticCurveTo(-s * 0.55, -s * 0.2, 0, -s)
      }
      ctx.closePath()
      ctx.fill()
      ctx.strokeStyle = "rgba(60,30,10,0.35)"
      ctx.lineWidth = 1.5
      ctx.beginPath()
      ctx.moveTo(0, -s * 0.8)
      ctx.lineTo(0, s * 0.8)
      ctx.stroke()
      ctx.restore()
    }
  }
  const tex = new THREE.CanvasTexture(canvas)
  tex.colorSpace = THREE.SRGBColorSpace
  tex.anisotropy = 4
  return tex
}

/** The moon's face. */
export function moonFace(): THREE.CanvasTexture {
  const n = 256
  const canvas = document.createElement("canvas")
  canvas.width = canvas.height = n
  const ctx = canvas.getContext("2d")
  if (ctx) {
    const img = ctx.createImageData(n, n)
    const low = fbm(n, 4, 5, 151)
    for (let j = 0; j < n; j++) {
      for (let i = 0; i < n; i++) {
        const dx = (i - n / 2) / (n / 2)
        const dy = (j - n / 2) / (n / 2)
        const r = Math.hypot(dx, dy)
        const k = (j * n + i) * 4
        const v = 200 + (low[j * n + i] - 0.5) * 120 - (low[j * n + i] > 0.6 ? 40 : 0)
        img.data[k] = clamp(v)
        img.data[k + 1] = clamp(v)
        img.data[k + 2] = clamp(v + 6)
        img.data[k + 3] = r < 0.98 ? 255 : r < 1 ? Math.round((1 - r) * 50 * 255) : 0
      }
    }
    ctx.putImageData(img, 0, 0)
  }
  const tex = new THREE.CanvasTexture(canvas)
  tex.colorSpace = THREE.SRGBColorSpace
  return tex
}

/** Words and figures drawn on something in the world: a clock's display, a flyer, a screen. Redrawn when they change. */
export class Board {
  canvas = document.createElement("canvas")
  ctx: CanvasRenderingContext2D
  texture: THREE.CanvasTexture
  private said = ""

  constructor(w: number, h: number) {
    this.canvas.width = w
    this.canvas.height = h
    this.ctx = this.canvas.getContext("2d") as CanvasRenderingContext2D
    this.texture = new THREE.CanvasTexture(this.canvas)
    this.texture.colorSpace = THREE.SRGBColorSpace
    this.texture.anisotropy = 8
  }

  /** Draw again, only when `key` (what it says) has changed. */
  draw(key: string, paint: (ctx: CanvasRenderingContext2D, w: number, h: number) => void): void {
    if (key === this.said) return
    this.said = key
    this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height)
    paint(this.ctx, this.canvas.width, this.canvas.height)
    this.texture.needsUpdate = true
  }
}
