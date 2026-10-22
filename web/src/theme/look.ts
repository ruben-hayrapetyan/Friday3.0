// How Friday looks on this device (v22 Settings → Appearance): theme, accent hue, block style, glow, panel chrome,
// Now bar and heading font. Kept in localStorage, applied as CSS variables on <html>. Ported from the design's
// `cfg`, `applyTheme()` and `theme()` (design/friday-v22.dc.html), so colours match it exactly.

export interface Look {
  theme: "Dark" | "Light" | "Match system"
  accentHue: number
  blocks: "Soft" | "Solid"
  glow: "Off" | "Today" | "More"
  headFont: "Archivo" | "Inter" | "Instrument Sans"
  headWeight: "Bold" | "Black"
  chrome: "Tonal" | "Shadow" | "Flat" | "Outline"
  dockStyle: "Bar" | "Ring" | "Minimal"
}

export const DEFAULT_LOOK: Look = {
  theme: "Dark",
  accentHue: 250,
  blocks: "Soft",
  glow: "Today",
  headFont: "Archivo",
  headWeight: "Black",
  chrome: "Tonal",
  dockStyle: "Bar",
}

const KEY = "friday-look-v7"

export function loadLook(): Look {
  try {
    return { ...DEFAULT_LOOK, ...JSON.parse(localStorage.getItem(KEY) ?? "{}") }
  } catch {
    return DEFAULT_LOOK
  }
}

export function saveLook(look: Look): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(look))
  } catch {
    // private mode: the look lasts this visit
  }
}

export function isLight(look: Look): boolean {
  return look.theme === "Light" || (look.theme === "Match system" && matchMedia("(prefers-color-scheme: light)").matches)
}

/** OKLCH to sRGB hex, clipped. */
export function oklch(L: number, C: number, h: number): string {
  const a = C * Math.cos((h * Math.PI) / 180)
  const b = C * Math.sin((h * Math.PI) / 180)
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
  const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
  const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3
  const rgb = [
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
  ]
  const hex = (x: number) => {
    const c = Math.max(0, Math.min(1, x))
    const g = c <= 0.0031308 ? 12.92 * c : 1.055 * c ** (1 / 2.4) - 0.055
    return Math.round(g * 255)
      .toString(16)
      .padStart(2, "0")
  }
  return `#${rgb.map(hex).join("")}`
}

export const accentHex = (hue: number, light: boolean) => (light ? oklch(0.54, 0.15, hue) : oklch(0.71, 0.14, hue))

/** An area's colour from its hue ("n" is the neutral grey). */
export function areaHex(hue: number | "n", light: boolean): string {
  if (hue === "n") return light ? oklch(0.76, 0.02, 260) : oklch(0.7, 0.02, 260)
  return light ? oklch(0.77, 0.12, hue) : oklch(0.79, 0.1, hue)
}

const set = (name: string, value: string) => document.documentElement.style.setProperty(name, value)

export function applyLook(look: Look): void {
  const light = isLight(look)
  const [bg, surface, text] = light ? ["#f2f4f7", "#ffffff", "#121821"] : ["#0c141c", "#131e29", "#e3ecf2"]
  const accent = accentHex(look.accentHue, light)
  set("--color-bg", bg)
  set("--color-surface", surface)
  set("--color-text", text)
  set("--color-accent", accent)
  const neutral = { 100: 92, 200: 80, 300: 66, 400: 52, 500: 40, 600: 30, 700: 22, 800: 15, 900: 10 }
  for (const [n, p] of Object.entries(neutral)) set(`--color-neutral-${n}`, `color-mix(in oklch, ${text} ${p}%, ${bg})`)
  const ramp: Record<number, [string, number]> = {
    100: [text, 70], 200: [text, 50], 300: [text, 30], 400: [text, 14], 500: [accent, 0],
    600: [bg, 20], 700: [bg, 40], 800: [bg, 62], 900: [bg, 78],
  } // prettier-ignore
  for (const [n, [mix, p]] of Object.entries(ramp)) set(`--color-accent-${n}`, `color-mix(in oklch, ${mix} ${p}%, ${accent})`)
  set("--color-divider", `color-mix(in srgb, ${text} ${light ? 10 : 12}%, transparent)`)
  set("--fr-ink", light ? "#121821" : bg)
  set("--fr-warn", light ? "#9a6510" : "#e8bd74")
  set("--fr-due", light ? "#b8323e" : "#f3a7ad")
  set("--fr-knob", light ? "#ffffff" : "#0c141c")
  const root = document.documentElement.style
  if (light) {
    set("--shadow-lg", "0 12px 32px rgba(18,24,33,0.14)")
    set("--shadow-sm", "0 1px 2px rgba(18,24,33,0.08)")
  } else {
    root.removeProperty("--shadow-lg")
    root.removeProperty("--shadow-sm")
  }
  document.body.style.background = bg
  root.background = bg
  root.colorScheme = light ? "light" : "dark"
  set("--fr-backdrop", "var(--color-bg)")
  applyChrome(look, light)
  applyGlowAndType(look, light)
}

function applyChrome(look: Look, light: boolean): void {
  const chrome: Record<Look["chrome"], [string, string]> = {
    Outline: ["var(--color-surface)", "var(--shadow-lg), 0 0 0 1px color-mix(in srgb, var(--color-text) 10%, transparent)"],
    Shadow: [
      "var(--color-surface)",
      light ? "0 10px 30px rgba(18,24,33,0.16), 0 2px 6px rgba(18,24,33,0.08)" : "0 14px 36px rgba(0,0,0,0.55), 0 2px 8px rgba(0,0,0,0.35)",
    ],
    Tonal: [
      light ? "#ffffff" : "color-mix(in srgb, var(--color-text) 7%, var(--color-surface))",
      light ? "0 8px 24px rgba(18,24,33,0.10)" : "0 10px 28px rgba(0,0,0,0.38)",
    ],
    Flat: [light ? "color-mix(in srgb, var(--color-text) 5%, #ffffff)" : "color-mix(in srgb, var(--color-text) 10%, var(--color-surface))", "none"],
  }
  const [floatBg, floatShadow] = chrome[look.chrome] ?? chrome.Tonal
  set("--fr-float-bg", floatBg)
  set("--fr-float-sh", floatShadow)
  set("--fr-chip-bg", `color-mix(in srgb, var(--color-text) ${look.chrome === "Outline" ? 6 : 8}%, transparent)`)
}

function applyGlowAndType(look: Look, light: boolean): void {
  const glows: Record<Look["glow"], string[]> = { Off: [], Today: ["--g-today"], More: ["--g-today", "--g-now", "--g-dock", "--g-accent"] }
  const glowing = glows[look.glow] ?? []
  for (const k of ["--g-now", "--g-today", "--g-dock", "--g-logo", "--g-accent"]) set(k, glowing.includes(k) && !light ? "1" : "0")
  const fonts = { Inter: "'Inter', sans-serif", Archivo: "'Archivo', sans-serif", "Instrument Sans": "'Instrument Sans', sans-serif" }
  set("--fr-head", fonts[look.headFont] ?? fonts.Archivo)
  set("--fr-body", "'Inter', system-ui, sans-serif")
  set("--fr-head-w", look.headWeight === "Bold" ? "700" : look.headFont === "Archivo" ? "900" : "800")
  set("--fr-head-ls", look.headFont === "Archivo" ? "-0.045em" : "-0.03em")
}
