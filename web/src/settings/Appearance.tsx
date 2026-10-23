// Appearance (v22): theme, accent hue, block style, glow, floating panels, the Now bar and the heading face, on this
// device, with a live preview.

import { Icon, Seg } from "@/components/fr/controls"
import { accentHex, areaHex, type Look } from "@/theme/look"
import { useLook } from "@/theme/LookProvider"
import { Field, SectionHead } from "./SettingsPage"

const HUES = Array.from({ length: 16 }, (_, i) => Math.round(i * 22.5))

export function Appearance() {
  const { look, light, setLook, skinOf } = useLook()
  const pick = <K extends keyof Look>(k: K) => (v: Look[K]) => setLook({ [k]: v } as Partial<Look>)
  const preview = [
    { title: "PS5", meta: "09:00–12:00", top: 8, h: 96, kind: "planned" as const, area: null, col: areaHex(265, light) },
    { title: "Lunch", meta: "12:30", top: 112, h: 34, kind: "routine" as const, area: null, col: "" },
    { title: "Project draft", meta: "14:00–15:30", top: 150, h: 60, kind: "preferred" as const, area: null, col: areaHex(60, light) },
  ]
  return (
    <>
      <SectionHead
        title="Appearance"
        note="How Friday looks on this device."
        right={
          <button className="fr-link" onClick={() => setLook(null)} style={{ display: "flex", gap: 6, alignItems: "center" }}>
            <Icon name="arrow-counter-clockwise" />
            Reset to default
          </button>
        }
      />
      <div className="fr-well fr-stack" style={{ display: "grid", gridTemplateColumns: "200px minmax(0,1fr)", gap: 20, padding: 18, marginBottom: 10, borderRadius: "var(--radius-lg)" }}>
        <div style={{ position: "relative", height: 220, borderRadius: "var(--radius-md)", background: "var(--color-surface)", backgroundImage: "repeating-linear-gradient(to bottom, color-mix(in srgb, var(--color-text) 6%, transparent) 0 1px, transparent 1px 44px)" }}>
          {preview.map((b) => {
            const s = b.col ? { ...skinOf(b.kind, null), ...skinFor(b.kind, b.col, look, skinOf) } : skinOf(b.kind, null)
            return (
              <div key={b.title} style={{ position: "absolute", left: 6, right: 6, top: b.top, height: b.h, padding: "4px 7px 4px 9px", borderRadius: 6, background: s.bg, border: s.bd, color: s.fg, overflow: "hidden", fontSize: 12, lineHeight: 1.3 }}>
                <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: 3, background: s.stripe }} />
                <div style={{ fontWeight: 500 }}>{b.title}</div>
                <div className="tnum" style={{ fontSize: 11, color: s.sub }}>
                  {b.meta}
                </div>
              </div>
            )
          })}
          <div style={{ position: "absolute", left: 0, right: 0, top: 96, height: 2, background: "var(--fr-now)", boxShadow: "0 0 calc(10px * var(--g-now)) calc(1px * var(--g-now)) var(--fr-now)" }} />
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 14, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
            <span className="fr-h" style={{ fontSize: 44, lineHeight: 0.9, color: "var(--color-accent-200)", textShadow: "0 0 calc(18px * var(--g-today)) var(--color-accent)" }}>
              19
            </span>
            <span className="fr-h" style={{ fontSize: 22 }}>
              Monday
            </span>
          </div>
          <div style={{ height: 2, width: 120, borderRadius: 1, background: "var(--color-accent)", boxShadow: "0 0 calc(12px * var(--g-today)) calc(1px * var(--g-today)) var(--color-accent)" }} />
          <div style={{ color: "var(--color-neutral-300)", textWrap: "pretty" }}>
            PS5 runs until 12:00. Project draft is pinned after lunch. <a style={{ textDecoration: "underline" }}>Why here?</a>
          </div>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            <button className="btn btn-primary">
              <Icon name="check" size={15} />
              Done
            </button>
            <button className="btn btn-secondary">+15</button>
            <span style={{ display: "inline-flex", gap: 4, alignItems: "center", fontSize: 12, padding: "2px 8px", borderRadius: "var(--radius-sm)", background: "color-mix(in srgb, var(--color-accent) 16%, transparent)", color: "var(--color-accent-200)" }}>
              <span style={{ color: "var(--color-accent-400)" }}>Due</span>Wed 17:00
            </span>
          </div>
        </div>
      </div>
      <Field name="Theme" note="Match system follows your computer’s light or dark setting.">
        <Seg options={["Dark", "Light", "Match system"] as const} value={look.theme} onPick={pick("theme")} size="big" />
      </Field>
      <Field name="Ink" note="The ink Friday’s own marks are written in: buttons, today, focus rings and highlights. Navy by default; pick any hue.">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(16, 1fr)", gap: 6 }}>
          {HUES.map((h) => (
            <button
              key={h}
              onClick={() => setLook({ accentHue: h })}
              aria-label={`Hue ${h}`}
              title={`Hue ${h}`}
              style={{ aspectRatio: "1", border: 0, borderRadius: 6, background: accentHex(h, light), boxShadow: Math.abs(look.accentHue - h) < 12 ? "0 0 0 2px var(--color-bg), 0 0 0 4px var(--color-text)" : "none", cursor: "pointer" }}
            />
          ))}
        </div>
        <div style={{ position: "relative", height: 24, display: "flex", alignItems: "center" }}>
          <div style={{ position: "absolute", left: 0, right: 0, height: 10, borderRadius: 5, background: `linear-gradient(to right, ${HUES.map((h) => accentHex(h, light)).join(", ")}, ${accentHex(359, light)})` }} />
          <input type="range" min={0} max={359} step={1} value={look.accentHue} onChange={(e) => setLook({ accentHue: Number(e.target.value) })} aria-label="Accent hue" style={{ position: "relative", width: "100%", margin: 0, background: "transparent", accentColor: "var(--color-accent)", cursor: "pointer" }} />
        </div>
        <span className="tnum" style={{ display: "inline-flex", alignItems: "center", gap: 8, fontSize: 12, color: "var(--color-neutral-400)" }}>
          <span style={{ width: 14, height: 14, borderRadius: 4, background: "var(--color-accent)" }} />
          {accentHex(look.accentHue, light)}, hue {look.accentHue}°
        </span>
      </Field>
      <Field name="Hours shown" note="Waking hours run the grid from your earliest wake time to your latest bedtime, with the night shaded. All day shows every hour and opens at your wake time.">
        <Seg options={["Waking", "All day"] as const} value={look.hours} onPick={pick("hours")} size="big" />
      </Field>
      <Field name="Deadlines" note="Chips put a day's deadlines in its header. Lanes give each day with something due a to-do list down the side of its column, which stays in view as you scroll and ticks off like the to-do list.">
        <Seg options={["Chips", "Lanes"] as const} value={look.deadlines} onPick={pick("deadlines")} size="big" />
      </Field>
      <Field name="Calendar blocks" note="Soft blocks sit back on the surface with a colored edge. Solid blocks fill with the area color.">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 220px))", gap: 10 }}>
          {(["Soft", "Solid"] as const).map((mode) => (
            <button key={mode} onClick={() => setLook({ blocks: mode })} className="fr-plain" style={{ display: "flex", flexDirection: "column", gap: 10, padding: 12, borderRadius: "var(--radius-md)", background: "var(--color-bg)", boxShadow: look.blocks === mode ? "inset 0 0 0 1px var(--color-accent)" : "inset 0 0 0 1px color-mix(in srgb, var(--color-text) 8%, transparent)" }}>
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                {[
                  ["PS5", 265, 30],
                  ["Essay", 155, 22],
                ].map(([title, hue, h]) => {
                  const col = areaHex(hue as number, light)
                  const s = skinFor("planned", col, { ...look, blocks: mode }, skinOf)
                  return (
                    <div key={title} style={{ position: "relative", height: h as number, padding: "3px 8px 3px 10px", borderRadius: 5, background: s.bg, color: s.fg, fontSize: 11, fontWeight: 500, overflow: "hidden" }}>
                      <span style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: 3, background: s.stripe }} />
                      {title}
                    </div>
                  )
                })}
              </div>
              <span style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
                <span>{mode}</span>
                {look.blocks === mode && <Icon name="check" style={{ color: "var(--color-accent-300)" }} />}
              </span>
            </button>
          ))}
        </div>
      </Field>
      <Field name="Glow" note="A soft light behind key elements, on the dark page only. Off keeps the paper flat.">
        <Seg options={["Off", "Today", "More"] as const} value={look.glow} onPick={pick("glow")} size="big" />
        <span className="fr-kicker">{light ? "Glow shows on the dark theme only." : { Off: "No glow anywhere.", Today: "Today’s date and underline glow.", More: "Today, the now line, the Now bar and the selected block glow." }[look.glow]}</span>
      </Field>
      <Field name="Floating panels" note="The Now bar, Shove, Pace and the to-do sidebar. Tonal panels sit a shade lighter with no outline.">
        <Seg options={["Tonal", "Shadow", "Flat", "Outline"] as const} value={look.chrome} onPick={pick("chrome")} size="big" />
      </Field>
      <Field name="Now bar" note="Bar shows the most. Minimal keeps the type small and the buttons to their icons.">
        <Seg options={["Bar", "Minimal"] as const} value={look.dockStyle} onPick={pick("dockStyle")} size="big" />
      </Field>
      <Field name="Headings" note="The typeface for titles, dates and big numbers. What people wrote stays in the system sans, and what Friday prints in mono.">
        <Seg options={["Serif", "Archivo", "Inter"] as const} value={look.headFont} onPick={pick("headFont")} size="big" />
        <Seg options={["Bold", "Black"] as const} value={look.headWeight} onPick={pick("headWeight")} size="big" />
      </Field>
    </>
  )
}

type SkinOf = ReturnType<typeof useLook>["skinOf"]

/** A block painted in a given colour (not an area's), for the previews. */
function skinFor(kind: "planned" | "preferred" | "routine", col: string, look: Look, skinOf: SkinOf) {
  const base = skinOf(kind, null)
  if (kind === "routine") return base
  const mix = (p: number) => `color-mix(in srgb, ${col} ${p}%, var(--color-bg))`
  return look.blocks === "Solid"
    ? { ...base, bg: col, fg: "var(--fr-ink)", sub: "color-mix(in srgb, var(--fr-ink) 72%, transparent)", stripe: "transparent" }
    : { ...base, bg: mix(24), fg: "var(--color-text)", sub: mix(80), stripe: col }
}
