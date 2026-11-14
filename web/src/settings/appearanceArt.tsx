// The small drawings on Settings → Appearance's choice cards. Each is drawn on a 120 × 72 grid and scales with its
// card (container units: 120 units = the card's width), in the app's own colours so it matches light and dark.

import type { CSSProperties, ReactNode } from "react"
import type { Clock } from "@/lib/clock"
import { shortHour } from "@/lib/time"
import { accentHex, FACES, type Look } from "@/theme/look"

/** Grid units to container width. */
const u = (n: number) => `${+(n / 1.2).toFixed(3)}cqw`

const mix = (col: string, p: number, on = "transparent") => `color-mix(in srgb, ${col} ${p}%, ${on})`

/** A box at x, y on the 120 × 72 grid. */
function Bx(props: { x: number; y: number; w: number; h: number; r?: number; style?: CSSProperties; children?: ReactNode }) {
  const { x, y, w, h, r, style, children } = props
  return (
    <span style={{ position: "absolute", display: "block", left: u(x), top: u(y), width: u(w), height: u(h), borderRadius: r === undefined ? undefined : u(r), ...style }}>
      {children}
    </span>
  )
}

/** A line of text, drawn as a bar. */
const Line = ({ x, y, w, col = "var(--color-text)", p = 45, h = 3 }: { x: number; y: number; w: number; col?: string; p?: number; h?: number }) => (
  <Bx x={x} y={y} w={w} h={h} r={h / 2} style={{ background: mix(col, p) }} />
)

/** Small mono type, as Friday prints times. */
const Tiny = ({ x, y, children, col = "var(--color-neutral-400)" }: { x: number; y: number; children: ReactNode; col?: string }) => (
  <Bx x={x} y={y} w={40} h={8} style={{ fontFamily: "var(--fr-mono)", fontSize: u(6.5), lineHeight: 1, color: col, whiteSpace: "nowrap" }}>
    {children}
  </Bx>
)

const Fill = ({ bg, children }: { bg: string; children?: ReactNode }) => <span style={{ position: "absolute", inset: 0, display: "block", background: bg }}>{children}</span>

/** Hour lines across a calendar from y0, every `step` units. */
function HourLines({ x = 0, y0, step, n }: { x?: number; y0: number; step: number; n: number }) {
  return (
    <>
      {Array.from({ length: n }, (_, i) => (
        <Bx key={i} x={x} y={y0 + i * step} w={120 - x} h={0.6} style={{ background: "var(--fr-rule)" }} />
      ))}
    </>
  )
}

const sleep = `repeating-linear-gradient(135deg, ${mix("var(--color-text)", 9)} 0 ${u(1.2)}, transparent ${u(1.2)} ${u(4)})`

/** A soft block in the accent, as a planned task. */
const Block = ({ x, y, w, h }: { x: number; y: number; w: number; h: number }) => (
  <Bx x={x} y={y} w={w} h={h} r={2.5} style={{ background: mix("var(--color-accent)", 22, "var(--color-surface)"), borderLeft: `${u(2)} solid var(--color-accent)` }}>
    <Line x={3} y={2.5} w={Math.min(w - 8, 22)} p={60} h={2.5} />
  </Bx>
)

// ---- Theme

// The paper and ink of each theme (theme/look.ts PAPER and NOW), so each card shows its own page whatever the look.
const PAPER = { light: { bg: "#eceee9", surface: "#fbfbf8", text: "#1a1d1c", now: "#c7332a" }, dark: { bg: "#0f1113", surface: "#1a1d20", text: "#e8ebe7", now: "#ee6a5e" } }

function Page({ light, hue }: { light: boolean; hue: number }) {
  const p = light ? PAPER.light : PAPER.dark
  const ink = accentHex(hue, light)
  return (
    <Fill bg={p.bg}>
      <Bx x={8} y={7} w={104} h={65} r={4} style={{ background: p.surface, boxShadow: `0 0 0 1px ${mix(p.text, 8)}` }}>
        <Bx x={7} y={6} w={14} h={9} style={{ fontFamily: "var(--fr-head)", fontWeight: 700, fontSize: u(9), lineHeight: 1, color: ink }}>
          19
        </Bx>
        <Line x={23} y={9} w={24} col={p.text} p={55} />
        <Bx x={7} y={19} w={90} h={18} r={2.5} style={{ background: mix(ink, 22, p.surface), borderLeft: `${u(2)} solid ${ink}` }}>
          <Line x={4} y={4} w={30} col={p.text} p={60} h={2.5} />
          <Line x={4} y={9} w={18} col={p.text} p={30} h={2.5} />
        </Bx>
        <Bx x={0} y={41} w={104} h={1} style={{ background: p.now }} />
        <Bx x={7} y={46} w={60} h={10} r={2.5} style={{ background: mix(p.text, 8, p.surface) }} />
      </Bx>
    </Fill>
  )
}

export function ThemeArt({ theme, hue }: { theme: Look["theme"]; hue: number }) {
  if (theme !== "Match system") return <Page light={theme === "Light"} hue={hue} />
  return (
    <>
      <Page light={false} hue={hue} />
      <span style={{ position: "absolute", inset: 0, display: "block", clipPath: "polygon(0 0, 100% 0, 0 100%)" }}>
        <Page light hue={hue} />
      </span>
    </>
  )
}

// ---- Hours shown

export function HoursArt({ hours }: { hours: Look["hours"] }) {
  if (hours === "Waking")
    return (
      <Fill bg="var(--color-surface)">
        <Bx x={18} y={60} w={102} h={12} style={{ background: sleep }} />
        <HourLines x={18} y0={4} step={8} n={8} />
        <Tiny x={3} y={1}>{shortHour(7)}</Tiny>
        <Tiny x={3} y={29}>{shortHour(15)}</Tiny>
        <Tiny x={3} y={57}>{shortHour(23)}</Tiny>
        <Block x={24} y={10} w={88} h={16} />
        <Block x={24} y={36} w={60} h={10} />
      </Fill>
    )
  return (
    <Fill bg="var(--color-surface)">
      <Bx x={18} y={0} w={102} h={21} style={{ background: sleep }} />
      <Bx x={18} y={66} w={102} h={6} style={{ background: sleep }} />
      <HourLines x={18} y0={0} step={3} n={24} />
      <Tiny x={3} y={1}>{shortHour(0)}</Tiny>
      <Tiny x={3} y={33}>{shortHour(12)}</Tiny>
      <Tiny x={3} y={63}>{shortHour(23)}</Tiny>
      <Block x={24} y={27} w={88} h={7} />
      <Block x={24} y={45} w={60} h={4} />
    </Fill>
  )
}

// ---- Clock

const CLOCK_ART: Record<Clock, string[]> = { "12h": ["9am", "12pm", "3pm", "2:30pm"], "24h": ["09:00", "12:00", "15:00", "14:30"] }

/** A calendar's hours and a block's time, on each clock (its own, whichever is chosen). */
export function ClockArt({ clock }: { clock: Clock }) {
  const [nine, noon, three, at] = CLOCK_ART[clock]
  return (
    <Fill bg="var(--color-surface)">
      <HourLines x={26} y0={4} step={22} n={4} />
      <Tiny x={3} y={1}>{nine}</Tiny>
      <Tiny x={3} y={23}>{noon}</Tiny>
      <Tiny x={3} y={45}>{three}</Tiny>
      <Bx x={30} y={45} w={84} h={20} r={2.5} style={{ background: mix("var(--color-accent)", 22, "var(--color-surface)"), borderLeft: `${u(2)} solid var(--color-accent)` }}>
        <Bx x={4} y={4} w={70} h={12} style={{ fontFamily: "var(--fr-mono)", fontSize: u(9), lineHeight: 1, color: "var(--color-text)", whiteSpace: "nowrap" }}>
          {at}
        </Bx>
      </Bx>
    </Fill>
  )
}

// ---- Deadlines

export function DeadlinesArt({ deadlines }: { deadlines: Look["deadlines"] }) {
  const due = "var(--color-accent)"
  const head = (
    <>
      <Bx x={0} y={0} w={120} h={20} style={{ background: "var(--color-bg)", borderBottom: "1px solid var(--fr-rule)" }} />
      <Bx x={6} y={4} w={14} h={10} style={{ fontFamily: "var(--fr-head)", fontWeight: 700, fontSize: u(9), lineHeight: 1, color: "var(--color-text)" }}>
        19
      </Bx>
      <Line x={20} y={7} w={16} p={45} />
    </>
  )
  if (deadlines === "Chips")
    return (
      <Fill bg="var(--color-surface)">
        <HourLines y0={30} step={12} n={4} />
        {head}
        <Bx x={40} y={5} w={26} h={10} r={5} style={{ background: mix("var(--fr-now)", 18), boxShadow: `inset 0 0 0 ${u(0.8)} var(--fr-now)` }}>
          <Line x={5} y={4} w={16} col="var(--fr-now)" p={85} />
        </Bx>
        <Block x={6} y={26} w={108} h={18} />
        <Block x={6} y={52} w={70} h={10} />
      </Fill>
    )
  return (
    <Fill bg="var(--color-surface)">
      <HourLines y0={30} step={12} n={4} />
      {head}
      <Block x={6} y={26} w={64} h={18} />
      <Block x={6} y={52} w={50} h={10} />
      <Bx x={76} y={20} w={44} h={52} style={{ background: mix(due, 9, "var(--color-surface)"), borderLeft: `1px solid ${mix(due, 30)}` }}>
        {[0, 1, 2].map((i) => (
          <span key={i}>
            <Bx x={5} y={6 + i * 13} w={7} h={7} r={1.5} style={{ boxShadow: `inset 0 0 0 ${u(1.2)} ${due}`, background: i === 0 ? due : "transparent" }} />
            <Line x={15} y={8 + i * 13} w={i === 1 ? 18 : 23} col={i === 0 ? "var(--color-text)" : due} p={i === 0 ? 25 : 70} />
          </span>
        ))}
      </Bx>
    </Fill>
  )
}

// ---- Calendar blocks

type Skin = { bg: string; fg: string; stripe: string }

export function BlocksArt({ skins }: { skins: Skin[] }) {
  return (
    <Fill bg="var(--color-surface)">
      <HourLines y0={6} step={15} n={5} />
      {skins.map((s, i) => (
        <Bx key={i} x={8} y={i ? 40 : 6} w={104} h={i ? 22 : 30} r={3} style={{ background: s.bg, overflow: "hidden" }}>
          <Bx x={0} y={0} w={2.5} h={30} style={{ background: s.stripe }} />
          <Line x={7} y={5} w={i ? 26 : 36} col={s.fg} p={85} h={3} />
          <Line x={7} y={11} w={20} col={s.fg} p={50} h={2.5} />
        </Bx>
      ))}
    </Fill>
  )
}

// ---- Glow (dark theme only, so drawn on the dark page)

export function GlowArt({ glow, hue }: { glow: Look["glow"]; hue: number }) {
  const p = PAPER.dark
  const ink = accentHex(hue, false)
  const today = glow !== "Off"
  const more = glow === "More"
  return (
    <Fill bg={p.bg}>
      <Bx x={8} y={6} w={40} h={26} style={{ fontFamily: "var(--fr-head)", fontWeight: "var(--fr-head-w)" as CSSProperties["fontWeight"], fontSize: u(26), lineHeight: 1, color: `color-mix(in oklch, ${p.text} 50%, ${ink})`, textShadow: today ? `0 0 ${u(9)} ${ink}` : "none" }}>
        19
      </Bx>
      <Bx x={9} y={33} w={34} h={1.6} r={1} style={{ background: ink, boxShadow: today ? `0 0 ${u(6)} ${u(1)} ${ink}` : "none" }} />
      <Bx x={60} y={8} w={52} h={26} r={3} style={{ background: mix(ink, 24, p.surface), boxShadow: more ? `0 0 0 ${u(1)} ${ink}, 0 0 ${u(9)} ${u(1)} ${ink}` : `0 0 0 ${u(1)} ${ink}` }}>
        <Line x={4} y={5} w={26} col={p.text} p={70} />
        <Line x={4} y={11} w={16} col={p.text} p={35} h={2.5} />
      </Bx>
      <Bx x={0} y={44} w={120} h={1.2} style={{ background: p.now, boxShadow: more ? `0 0 ${u(6)} ${u(1)} ${p.now}` : "none" }} />
      <Bx x={20} y={54} w={80} h={12} r={6} style={{ background: p.surface, boxShadow: more ? `0 0 ${u(8)} ${mix(ink, 70)}, 0 0 0 1px ${mix(p.text, 12)}` : `0 0 0 1px ${mix(p.text, 12)}` }}>
        <Bx x={5} y={4.5} w={3} h={3} r={1.5} style={{ background: p.now }} />
        <Line x={11} y={4.5} w={34} col={p.text} p={55} />
      </Bx>
    </Fill>
  )
}

// ---- Floating panels

/** Each panel style, scaled down from theme/look.ts applyChrome to the card's size. */
function panel(chrome: Look["chrome"], light: boolean): CSSProperties {
  const sh = (y: number, b: number, a: number) => `0 ${u(y)} ${u(b)} rgba(${light ? "26,29,28" : "0,0,0"},${a})`
  switch (chrome) {
    case "Outline":
      return { background: "var(--color-surface)", boxShadow: `${sh(2, 6, light ? 0.12 : 0.5)}, 0 0 0 1px ${mix("var(--color-text)", 16)}` }
    case "Shadow":
      return { background: "var(--color-surface)", boxShadow: `${sh(3, 9, light ? 0.22 : 0.65)}, ${sh(1, 2, light ? 0.1 : 0.4)}` }
    case "Tonal":
      return { background: light ? "var(--color-surface)" : mix("var(--color-text)", 9, "var(--color-surface)"), boxShadow: sh(2, 7, light ? 0.12 : 0.45) }
    case "Flat":
      return { background: mix("var(--color-text)", light ? 6 : 12, "var(--color-surface)"), boxShadow: "none" }
  }
}

export function ChromeArt({ chrome, light }: { chrome: Look["chrome"]; light: boolean }) {
  return (
    <Fill bg="var(--color-surface)">
      <HourLines y0={6} step={12} n={6} />
      <Block x={8} y={9} w={70} h={20} />
      <Bx x={10} y={40} w={100} h={24} r={5} style={panel(chrome, light)}>
        <Bx x={7} y={7} w={4} h={4} r={2} style={{ background: "var(--fr-now)" }} />
        <Line x={15} y={7} w={36} p={65} />
        <Line x={15} y={14} w={22} p={30} h={2.5} />
        <Bx x={70} y={7} w={22} h={10} r={2.5} style={{ background: "var(--color-accent)" }} />
      </Bx>
    </Fill>
  )
}

// ---- Now bar

export function NowBarArt({ dock }: { dock: Look["dockStyle"] }) {
  const float: CSSProperties = { background: "var(--fr-float-bg)", boxShadow: `0 ${u(2)} ${u(6)} rgba(0,0,0,0.22), 0 0 0 1px ${mix("var(--color-text)", 12)}` }
  return (
    <Fill bg="var(--color-surface)">
      <HourLines y0={6} step={12} n={6} />
      <Block x={8} y={9} w={70} h={18} />
      <Bx x={0} y={32} w={120} h={1} style={{ background: "var(--fr-now)" }} />
      {dock === "Bar" ? (
        <Bx x={5} y={42} w={110} h={25} r={5} style={float}>
          <Bx x={6} y={6} w={4} h={4} r={2} style={{ background: "var(--fr-now)" }} />
          <Line x={14} y={6} w={34} p={70} />
          <Line x={14} y={13} w={24} p={35} h={2.5} />
          <Bx x={58} y={7} w={26} h={11} r={2.5} style={{ background: "var(--color-accent)" }}>
            <Line x={5} y={4} w={16} col="var(--fr-ink)" p={90} />
          </Bx>
          <Bx x={87} y={7} w={17} h={11} r={2.5} style={{ boxShadow: `inset 0 0 0 1px ${mix("var(--color-text)", 25)}` }}>
            <Line x={4} y={4} w={9} p={55} />
          </Bx>
        </Bx>
      ) : (
        <Bx x={28} y={50} w={64} h={13} r={6.5} style={float}>
          <Bx x={6} y={4.5} w={4} h={4} r={2} style={{ background: "var(--fr-now)" }} />
          <Line x={13} y={5} w={22} p={65} />
          <Bx x={40} y={3} w={7} h={7} r={3.5} style={{ background: "var(--color-accent)" }} />
          <Bx x={50} y={3} w={7} h={7} r={3.5} style={{ boxShadow: `inset 0 0 0 1px ${mix("var(--color-text)", 30)}` }} />
        </Bx>
      )}
    </Fill>
  )
}

// ---- Headings

// The heading faces and weights (theme/look.ts applyGlowAndType), for a card that shows a face that is not chosen.
const HEADS: Record<Look["headFont"], string> = { Serif: FACES.serif, Archivo: "'Archivo', sans-serif", Inter: "'Inter', sans-serif" }

export function FaceArt({ font, weight }: { font: Look["headFont"]; weight: Look["headWeight"] }) {
  const serif = font === "Serif"
  const w = weight === "Bold" ? (serif ? 600 : 700) : serif ? 700 : font === "Archivo" ? 900 : 800
  const ls = serif ? "-0.005em" : font === "Archivo" ? "-0.045em" : "-0.03em"
  return (
    <Fill bg="var(--color-surface)">
      <span style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: u(3), fontFamily: HEADS[font], fontWeight: w, letterSpacing: ls, color: "var(--color-text)", lineHeight: 1 }}>
        <span style={{ fontSize: u(30) }}>Aa</span>
        <span style={{ fontSize: u(10), color: "var(--color-neutral-300)" }}>Monday 19</span>
      </span>
    </Fill>
  )
}
