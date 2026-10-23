// How Friday looks on this device (Settings → Appearance): theme, ink, block style, glow, panel chrome, Now bar and
// heading face. Kept in localStorage, applied as CSS variables on <html>.
//
// The look is personal's paper and ink (COMBINED.md 61–65, from UI/Sources/Design/Theme.swift): a cool desk with
// pages on it, colour spent on content and never on chrome, one red kept for now and overdue. The accent is the ink
// the chrome is written in; the hue picker changes that ink. v22's options stay, adapted: glow is dark-only and off.

export interface Look {
  theme: "Dark" | "Light" | "Match system"
  accentHue: number
  blocks: "Soft" | "Solid"
  glow: "Off" | "Today" | "More"
  headFont: "Serif" | "Archivo" | "Inter"
  headWeight: "Bold" | "Black"
  chrome: "Tonal" | "Shadow" | "Flat" | "Outline"
  dockStyle: "Bar" | "Minimal"
  hours: "Waking" | "All day" // the day and week grid: wake to bedtime with sleep bands, or all 24 hours
  deadlines: "Chips" | "Lanes" // a day's dues as chips in its header, or as a to-do lane down its column
}

export const DEFAULT_LOOK: Look = {
  theme: "Match system",
  accentHue: 255, // personal's fresh iron-gall navy
  blocks: "Soft",
  glow: "Off",
  headFont: "Serif",
  headWeight: "Bold",
  chrome: "Outline",
  dockStyle: "Bar",
  hours: "Waking",
  deadlines: "Chips",
}

const KEY = "friday-look-v8"

// Paper and ink, light and dark (Theme.swift): desk, leaf, ink.
const PAPER = { light: ["#eceee9", "#fbfbf8", "#1a1d1c"], dark: ["#0f1113", "#1a1d20", "#e8ebe7"] } as const
// The reserved red (now and overdue) and the gold mark (attention), per appearance.
const NOW = { light: "#c7332a", dark: "#ee6a5e" }
const MARK = { light: "#b08423", dark: "#d8a94a" }

export const FACES = {
  serif: "ui-serif, 'New York', 'Source Serif 4', Georgia, serif",
  sans: "system-ui, -apple-system, 'SF Pro Text', 'Inter', 'Segoe UI', sans-serif",
  mono: "ui-monospace, 'SF Mono', Menlo, 'JetBrains Mono', monospace",
}

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

/** The ink of a hue: dark and quiet on paper, light on the dark page. */
export const accentHex = (hue: number, light: boolean) => (light ? oklch(0.34, 0.075, hue) : oklch(0.76, 0.075, hue))

/** An area's colour from its hue ("n" is the neutral grey): a pigment, mid-tone so it reads on paper. */
export function areaHex(hue: number | "n", light: boolean): string {
  if (hue === "n") return light ? oklch(0.66, 0.015, 150) : oklch(0.68, 0.015, 150)
  return light ? oklch(0.64, 0.12, hue) : oklch(0.76, 0.1, hue)
}

const set = (name: string, value: string) => document.documentElement.style.setProperty(name, value)

export function applyLook(look: Look): void {
  const light = isLight(look)
  const [bg, surface, text] = light ? PAPER.light : PAPER.dark
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
  set("--fr-ink", light ? surface : bg) // text on a filled accent
  set("--fr-now", light ? NOW.light : NOW.dark)
  set("--fr-due", light ? NOW.light : NOW.dark) // one red: overdue is the same mark as now
  set("--fr-mark", light ? MARK.light : MARK.dark)
  set("--fr-warn", light ? "#8a6514" : MARK.dark)
  set("--fr-knob", light ? surface : bg)
  set("--fr-hairline", `color-mix(in srgb, ${text} 7%, transparent)`)
  set("--fr-rule", `color-mix(in srgb, ${text} 12%, transparent)`)
  const root = document.documentElement.style
  if (light) {
    set("--shadow-lg", "0 10px 28px rgba(26,29,28,0.12)")
    set("--shadow-sm", "0 1px 2px rgba(26,29,28,0.08)")
  } else {
    set("--shadow-lg", "0 14px 36px rgba(0,0,0,0.5)")
    set("--shadow-sm", "0 1px 2px rgba(0,0,0,0.4)")
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
      light ? "0 10px 30px rgba(26,29,28,0.16), 0 2px 6px rgba(26,29,28,0.08)" : "0 14px 36px rgba(0,0,0,0.55), 0 2px 8px rgba(0,0,0,0.35)",
    ],
    Tonal: [
      light ? "var(--color-surface)" : "color-mix(in srgb, var(--color-text) 7%, var(--color-surface))",
      light ? "0 8px 24px rgba(26,29,28,0.10)" : "0 10px 28px rgba(0,0,0,0.38)",
    ],
    Flat: [light ? "color-mix(in srgb, var(--color-text) 4%, var(--color-surface))" : "color-mix(in srgb, var(--color-text) 10%, var(--color-surface))", "none"],
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
  // Three faces, one job each: serif headings (what you are looking at), sans for what people wrote, mono for what
  // Friday prints. Apple's own faces where the browser offers them, bundled ones elsewhere.
  const heads = { Serif: FACES.serif, Archivo: "'Archivo', sans-serif", Inter: "'Inter', sans-serif" }
  set("--fr-head", heads[look.headFont] ?? heads.Serif)
  set("--fr-body", FACES.sans)
  set("--fr-mono", FACES.mono)
  const serif = (look.headFont ?? "Serif") === "Serif"
  set("--fr-head-w", look.headWeight === "Bold" ? (serif ? "600" : "700") : serif ? "700" : look.headFont === "Archivo" ? "900" : "800")
  set("--fr-head-ls", serif ? "-0.005em" : look.headFont === "Archivo" ? "-0.045em" : "-0.03em")
}
