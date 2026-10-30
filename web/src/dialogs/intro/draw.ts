// Drawing the intro's world (scenes.ts) on its 256 × 144 canvas: sprites baked once into little canvases, flat
// rectangles, dithered fills, banded skies by the hour, and words in the 3 × 5 font. Everything lands on whole pixels.

import { PAL, words } from "./art"

export const W = 256
export const H = 144

const baked = new Map<string, HTMLCanvasElement>()

function bake(art: readonly string[], swap?: Record<string, string>): HTMLCanvasElement {
  const key = `${art.join("|")}#${swap ? JSON.stringify(swap) : ""}`
  const found = baked.get(key)
  if (found) return found
  const canvas = document.createElement("canvas")
  canvas.width = Math.max(...art.map((r) => r.length))
  canvas.height = art.length
  const ctx = canvas.getContext("2d")
  if (ctx)
    art.forEach((row, y) => {
      for (let x = 0; x < row.length; x++) {
        const ch = swap?.[row[x]] ?? row[x]
        if (ch === "." || !PAL[ch]) continue
        ctx.fillStyle = PAL[ch]
        ctx.fillRect(x, y, 1, 1)
      }
    })
  baked.set(key, canvas)
  return canvas
}

export class G {
  readonly ctx: CanvasRenderingContext2D

  constructor(ctx: CanvasRenderingContext2D) {
    this.ctx = ctx
    ctx.imageSmoothingEnabled = false
  }

  rect(x: number, y: number, w: number, h: number, color: string): void {
    this.ctx.fillStyle = PAL[color] ?? color
    this.ctx.fillRect(Math.round(x), Math.round(y), Math.round(w), Math.round(h))
  }

  /** A checkerboard of two colours: pixel art's half tone. */
  dither(x: number, y: number, w: number, h: number, color: string, phase = 0): void {
    this.ctx.fillStyle = PAL[color] ?? color
    for (let yy = 0; yy < h; yy++)
      for (let xx = (yy + phase) % 2; xx < w; xx += 2) this.ctx.fillRect(Math.round(x) + xx, Math.round(y) + yy, 1, 1)
  }

  sprite(art: readonly string[], x: number, y: number, opts: { flip?: boolean; swap?: Record<string, string>; alpha?: number; scale?: number } = {}): void {
    const img = bake(art, opts.swap)
    const { ctx } = this
    const k = opts.scale ?? 1
    if (opts.alpha !== undefined) ctx.globalAlpha = opts.alpha
    if (opts.flip) {
      ctx.save()
      ctx.translate(Math.round(x) + img.width * k, Math.round(y))
      ctx.scale(-1, 1)
      ctx.drawImage(img, 0, 0, img.width * k, img.height * k)
      ctx.restore()
    } else ctx.drawImage(img, Math.round(x), Math.round(y), img.width * k, img.height * k)
    if (opts.alpha !== undefined) ctx.globalAlpha = 1
  }

  /** Words, `scale` pixels a font pixel; with `outline`, ringed in that colour so they read over anything. */
  text(text: string, x: number, y: number, color = "k", scale = 1, outline?: string): void {
    if (outline) {
      const ring = Math.max(1, Math.round(scale / 2))
      for (const [dx, dy] of [[-1, 0], [1, 0], [0, -1], [0, 1], [-1, -1], [1, -1], [-1, 1], [1, 1], [1, 2], [0, 2], [2, 2]])
        this.text(text, x + dx * ring, y + dy * ring, outline, scale)
    }
    const art = words(text, color)
    if (scale === 1) return this.sprite(art, x, y)
    const img = bake(art)
    this.ctx.drawImage(img, Math.round(x), Math.round(y), img.width * scale, img.height * scale)
  }

  /** The whole picture dimmed toward night, in a dither so it stays pixel art. */
  shade(amount: number): void {
    if (amount <= 0) return
    this.ctx.fillStyle = "#14122a"
    this.ctx.globalAlpha = Math.min(0.85, amount)
    this.ctx.fillRect(0, 0, W, H)
    this.ctx.globalAlpha = 1
  }
}

/** The sky's colours at a time of day (minutes), top to bottom, in four bands. */
export function skyAt(minutes: number): string[] {
  const h = ((minutes % 1440) + 1440) % 1440 / 60
  if (h < 5 || h >= 21.5) return ["#14122a", "#1d1b3a", "#25244a", "#2f3352"]
  if (h < 6.5) return ["#2f3352", "#5b4a7a", "#b5708a", "#f29b6b"] // dawn
  if (h < 8) return ["#6f8fd8", "#9fb6e8", "#f2c9a6", "#f9dfa6"] // early morning
  if (h < 17) return ["#5fa8e8", "#7fc0f0", "#a6d6f6", "#cdeafa"] // day
  if (h < 19) return ["#5b7fd1", "#b07aa8", "#f29b6b", "#f4c542"] // late afternoon
  return ["#2f3352", "#5b4a7a", "#c46f8a", "#f29b6b"] // dusk
}

/** A sky in bands with a dithered edge between each. */
export function sky(g: G, x: number, y: number, w: number, h: number, minutes: number): void {
  const bands = skyAt(minutes)
  const band = Math.ceil(h / bands.length)
  bands.forEach((c, i) => g.rect(x, y + i * band, w, Math.min(band, h - i * band), c))
  bands.slice(1).forEach((c, i) => g.dither(x, y + (i + 1) * band - 2, w, 2, c))
}

/** Where the sun (or moon) sits in a sky box at a time: up over the day, down over the night. */
export function arc(minutes: number, from: number, to: number, x: number, y: number, w: number, h: number): [number, number] {
  const share = Math.max(0, Math.min(1, (minutes - from) / Math.max(1, to - from)))
  return [x + share * w, y + h - Math.sin(share * Math.PI) * h]
}

/** Is it night at this hour (for the moon, the stars and the lamp)? */
export function isNight(minutes: number): boolean {
  const h = ((minutes % 1440) + 1440) % 1440 / 60
  return h < 6.5 || h >= 20
}

/** A deterministic scatter (books on shelves, stars): the same picture every frame. */
export function scatter(seed: number): () => number {
  let s = seed
  return () => {
    s = (s * 9301 + 49297) % 233280
    return s / 233280
  }
}

// An ordered dither, the old consoles' way to fade: sixteen levels, each a 4 × 4 tile of dark pixels.
const BAYER = [0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5]
const tiles = new Map<number, CanvasPattern | null>()

/** The picture coming out of the dark, `s` from 0 (all dark) to 1 (all there). */
export function dissolve(g: G, s: number): void {
  const level = Math.round((1 - Math.max(0, Math.min(1, s))) * 16)
  if (level <= 0) return
  if (!tiles.has(level)) {
    const tile = document.createElement("canvas")
    tile.width = tile.height = 4
    const ctx = tile.getContext("2d")
    if (ctx) {
      ctx.fillStyle = "#14122a"
      BAYER.forEach((v, i) => v < level && ctx.fillRect(i % 4, Math.floor(i / 4), 1, 1))
    }
    tiles.set(level, ctx ? g.ctx.createPattern(tile, "repeat") : null)
  }
  const pattern = tiles.get(level)
  if (!pattern) return
  g.ctx.fillStyle = pattern
  g.ctx.fillRect(0, 0, W, H)
}
