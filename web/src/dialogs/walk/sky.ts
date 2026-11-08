// The time of day in the walk (walk/World.ts), as real as we can make it (29 Oct: "make it as realistic as possible"):
// where the sun and moon are at a given minute, the colour and strength of their light, the haze, and the sky's colour
// toward the horizon (the Preetham daylight model, as three.js's Sky draws it, so the fog meets the sky without a seam).
// Pure, so it can be tested; the road runs north (-z), east is +x.

export type Vec3 = [number, number, number]

import { DAYLIGHT, type Season } from "./season"

// Sunrise, sunset and the noon sun's height: fall's (6:15am to 7:15pm, about 47°) until the walk says its season
// (walk/season.ts), so what's tested here is one day, whatever day the tests run.
let day = DAYLIGHT.fall

/** The walk's season's day: winter's short and low, summer's long and high. */
export function useDaylight(season: Season): void {
  day = DAYLIGHT[season]
}

/** Where it is in the day, 0 to 24, from minutes after midnight (any day). */
export function hourOf(minutes: number): number {
  return (((minutes % 1440) + 1440) % 1440) / 60
}

function toward(azimuth: number, elevation: number): Vec3 {
  // azimuth from north, clockwise (east is a quarter turn)
  return [Math.sin(azimuth) * Math.cos(elevation), Math.sin(elevation), -Math.cos(azimuth) * Math.cos(elevation)]
}

const deg = (d: number) => (d * Math.PI) / 180

/** The sun's direction, rising in the east and setting in the west over the south; below the horizon at night. */
export function sunAt(minutes: number): { dir: Vec3; elevation: number } {
  const h = hourOf(minutes)
  if (h >= day.rise && h <= day.set) {
    const s = (h - day.rise) / (day.set - day.rise)
    const elevation = day.noon * Math.sin(Math.PI * s)
    return { dir: toward(deg(100 + 160 * s), elevation), elevation }
  }
  const night = ((h - day.set + 24) % 24) / (24 - (day.set - day.rise))
  const elevation = -0.6 * Math.sin(Math.PI * night)
  return { dir: toward(deg(260 + 200 * night), elevation), elevation }
}

/** The moon: up through the night, across the south. */
export function moonAt(minutes: number): { dir: Vec3; elevation: number } {
  const h = hourOf(minutes)
  const night = ((h - (day.set - 0.75) + 24) % 24) / (24 - (day.set - day.rise) + 1.5)
  const elevation = night <= 1 ? 0.95 * Math.sin(Math.PI * night) - 0.05 : -0.4
  return { dir: toward(deg(95 + 170 * Math.min(1, night)), elevation), elevation }
}

const smooth = (a: number, b: number, x: number) => {
  const t = Math.max(0, Math.min(1, (x - a) / (b - a)))
  return t * t * (3 - 2 * t)
}
const mix = (a: number, b: number, t: number) => a + (b - a) * t
function mixHex(a: number, b: number, t: number): number {
  const ch = (s: number) => Math.round(mix((a >> s) & 255, (b >> s) & 255, t))
  return (ch(16) << 16) | (ch(8) << 8) | ch(0)
}

export interface Light {
  sun: Vec3
  moon: Vec3
  day: number // 0 at night, 1 in daylight (civil twilight between)
  sunColor: number
  sunLevel: number
  moonLevel: number
  skyFill: number // the hemisphere's colours and strength: light from the whole sky and from the ground
  groundFill: number
  fillLevel: number
  exposure: number
  haze: number // the fog's density
  lamps: number // street lamps and windows, 0 off to 1 on
  air: Air
  glow: Vec3 // the night sky's own faint light (and the town's), added to the sky
}

export interface Air {
  turbidity: number
  rayleigh: number
  mie: number
  mieG: number
}

export function lightAt(minutes: number): Light {
  const sun = sunAt(minutes)
  const moon = moonAt(minutes)
  const d = (sun.elevation * 180) / Math.PI
  const day = smooth(-7, 5, d)
  const golden = d > 0 ? 1 - smooth(3, 22, d) : 1
  const sunColor = d < 2 ? mixHex(0xff7b3a, 0xffb36a, smooth(-1, 2, d)) : mixHex(0xfff2e2, 0xffb36a, golden)
  const night = 1 - day
  return {
    sun: sun.dir,
    moon: moon.dir,
    day,
    sunColor,
    sunLevel: 3.4 * smooth(-1.5, 10, d),
    moonLevel: 0.32 * night * smooth(-2, 12, (moon.elevation * 180) / Math.PI),
    skyFill: mixHex(mixHex(0x2a3a66, 0xffc9a8, golden * day), 0xbfd6ff, day * (1 - golden)),
    groundFill: mixHex(0x1a1d22, 0x6b5a45, day),
    fillLevel: 0.12 + 0.55 * day,
    exposure: mix(1.25, 0.52, day),
    haze: mix(0.011, 0.0065, day) + 0.004 * golden * day,
    lamps: 1 - smooth(-3, 6, d),
    air: { turbidity: mix(3, 7, golden), rayleigh: mix(1.1, 2.6, golden), mie: mix(0.004, 0.009, golden), mieG: 0.82 },
    glow: [mix(0.0, 0.006, night), mix(0.0, 0.009, night), mix(0.0, 0.022, night)],
  }
}

/** Minutes from `from` to `to` going forward through the day (the walk's time only goes on), or back when `back`. */
export function timeStep(from: number, to: number, back: boolean): number {
  const ahead = (((to - from) % 1440) + 1440) % 1440
  return back ? -((((from - to) % 1440) + 1440) % 1440) : ahead
}

// ---- the Preetham sky, as three.js's Sky shader computes it, for one direction ---------------------------------------

const RAYLEIGH: Vec3 = [5.804542996261093e-6, 1.3562911419845635e-5, 3.0265902468824876e-5]
const MIE: Vec3 = [1.8399918514433978e14, 2.7798023919660528e14, 4.0790479543861094e14]

function sunIntensity(cosZenith: number): number {
  const z = Math.acos(Math.max(-1, Math.min(1, cosZenith)))
  return 1000 * Math.max(0, 1 - Math.exp(-((1.6110731556870734 - z) / 1.5)))
}

/** The sky's colour (linear, before exposure) looking along `dir`, with the sun along `sun`. */
export function skyColor(dir: Vec3, sun: Vec3, air: Air): Vec3 {
  const sunE = sunIntensity(sun[1])
  const betaR = RAYLEIGH.map((v) => v * air.rayleigh)
  const betaM = MIE.map((v) => 0.434 * (0.2 * air.turbidity * 10e-18) * v * air.mie)
  const zenith = Math.acos(Math.max(0, dir[1]))
  const inverse = 1 / (Math.cos(zenith) + 0.15 * Math.pow(93.885 - (zenith * 180) / Math.PI, -1.253))
  const sR = 8.4e3 * inverse
  const sM = 1.25e3 * inverse
  const cosTheta = dir[0] * sun[0] + dir[1] * sun[1] + dir[2] * sun[2]
  const rPhase = 0.05968310365946075 * (1 + Math.pow(cosTheta * 0.5 + 0.5, 2))
  const g = air.mieG
  const mPhase = 0.07957747154594767 * ((1 - g * g) / Math.pow(1 - 2 * g * cosTheta + g * g, 1.5))
  const low = Math.max(0, Math.min(1, Math.pow(1 - sun[1], 5)))
  const out: Vec3 = [0, 0, 0]
  const floor = [0, 0.0003, 0.00075]
  for (let i = 0; i < 3; i++) {
    const fex = Math.exp(-(betaR[i] * sR + betaM[i] * sM))
    const ratio = (betaR[i] * rPhase + betaM[i] * mPhase) / (betaR[i] + betaM[i])
    let lin = Math.pow(sunE * ratio * (1 - fex), 1.5)
    lin *= mix(1, Math.pow(sunE * ratio * fex, 0.5), low)
    const tex = (lin + 0.1 * fex) * 0.04 + floor[i]
    out[i] = Math.pow(tex, 1 / 2.4)
  }
  return out
}

/** The colour of the haze: the sky just above the horizon, all the way round, with the night's glow. */
export function hazeColor(l: Light): Vec3 {
  const sum: Vec3 = [0, 0, 0]
  const n = 8
  for (let i = 0; i < n; i++) {
    const a = (i / n) * Math.PI * 2
    const c = skyColor([Math.cos(a) * 0.9995, 0.03, Math.sin(a) * 0.9995], l.sun, l.air)
    for (let k = 0; k < 3; k++) sum[k] += c[k] / n
  }
  return [sum[0] + l.glow[0] * 1.6, sum[1] + l.glow[1] * 1.6, sum[2] + l.glow[2] * 1.6]
}
