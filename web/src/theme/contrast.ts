// How readable a color is on another (3 Nov, the CS 2112 UI lecture: "low contrast text is hard to read"): WCAG's
// contrast ratio, and the OKLab mix the theme's grays are made with (`color-mix(in oklch, text p%, page)`; for grays,
// which have no hue, that is the same as OKLab).

type Rgb = [number, number, number] // 0–1, gamma-encoded sRGB

const toLinear = (c: number) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4)
const toGamma = (c: number) => (c <= 0.0031308 ? 12.92 * c : 1.055 * c ** (1 / 2.4) - 0.055)

export function rgb(hex: string): Rgb {
  const h = hex.replace("#", "")
  return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16) / 255) as Rgb
}

function oklab([r, g, b]: Rgb): Rgb {
  const [R, G, B] = [r, g, b].map(toLinear)
  const l = Math.cbrt(0.4122214708 * R + 0.5363325363 * G + 0.0514459929 * B)
  const m = Math.cbrt(0.2119034982 * R + 0.6806995451 * G + 0.1073969566 * B)
  const s = Math.cbrt(0.0883024619 * R + 0.2817188376 * G + 0.6299787005 * B)
  return [
    0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s,
    1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
    0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s,
  ]
}

function fromOklab([L, a, b]: Rgb): Rgb {
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
  const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
  const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3
  const lin = [
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
  ]
  return lin.map((c) => toGamma(Math.max(0, Math.min(1, c)))) as Rgb
}

/** `share` (0–100) of `a` over `b`, mixed as the theme mixes its grays. */
export function mix(a: string, b: string, share: number): Rgb {
  const [A, B] = [oklab(rgb(a)), oklab(rgb(b))]
  return fromOklab(A.map((v, i) => (v * share) / 100 + B[i] * (1 - share / 100)) as Rgb)
}

const luminance = (c: Rgb) => {
  const [r, g, b] = c.map(toLinear)
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

/** WCAG's contrast ratio, 1 (none) to 21 (black on white). 4.5 is the floor for words at normal sizes. */
export function contrast(fg: Rgb | string, bg: Rgb | string): number {
  const [a, b] = [fg, bg].map((c) => luminance(typeof c === "string" ? rgb(c) : c))
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05)
}
