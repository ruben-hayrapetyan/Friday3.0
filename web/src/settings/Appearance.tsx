// Appearance (v22): theme, accent hue, block style, glow, floating panels, the Now bar and the heading face, on this
// device, with a live preview. Each choice is a card with a small picture of what it looks like (ChoiceCards). The
// clock is the one choice kept by Friday rather than this device (settings `clock`): the server's sentences, the
// command line and Siri follow it too.

import { Icon } from "@/components/fr/controls"
import { useSettings } from "@/hooks/queries"
import { useCommand } from "@/hooks/useCommand"
import type { Clock } from "@/lib/clock"
import { clockTime } from "@/lib/time"
import { accentHex, areaHex, type Look } from "@/theme/look"
import { useLook } from "@/theme/LookProvider"
import { BlocksArt, ChromeArt, ClockArt, DeadlinesArt, FaceArt, GlowArt, HoursArt, NowBarArt, ThemeArt } from "./appearanceArt"
import { ChoiceCards } from "./ChoiceCards"
import { Field, SectionHead } from "./SettingsPage"

const HUES = Array.from({ length: 16 }, (_, i) => Math.round(i * 22.5))

export function Appearance() {
  const { look, light, setLook, skinOf } = useLook()
  const pick = <K extends keyof Look>(k: K) => (v: Look[K]) => setLook({ [k]: v } as Partial<Look>)
  const span = (a: string, b: string) => `${clockTime(a)}–${clockTime(b)}`
  const preview = [
    { title: "PS5", meta: span("09:00", "12:00"), top: 8, h: 96, kind: "planned" as const, area: null, col: areaHex(265, light) },
    { title: "Lunch", meta: clockTime("12:30"), top: 112, h: 34, kind: "routine" as const, area: null, col: "" },
    { title: "Project draft", meta: span("14:00", "15:30"), top: 150, h: 60, kind: "preferred" as const, area: null, col: areaHex(60, light) },
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
            PS5 runs until {clockTime("12:00")}. Project draft is pinned after lunch. <a style={{ textDecoration: "underline" }}>Why here?</a>
          </div>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            <button className="btn btn-primary">
              <Icon name="check" size={15} />
              Done
            </button>
            <button className="btn btn-secondary">+15</button>
            <span style={{ display: "inline-flex", gap: 4, alignItems: "center", fontSize: 12, padding: "2px 8px", borderRadius: "var(--radius-sm)", background: "color-mix(in srgb, var(--color-accent) 16%, transparent)", color: "var(--color-accent-200)" }}>
              <span style={{ color: "var(--color-accent-400)" }}>Due</span>Wed {clockTime("17:00")}
            </span>
          </div>
        </div>
      </div>
      <Field name="Theme" note="Light, dark, or follow your device.">
        <ChoiceCards label="Theme" value={look.theme} onPick={pick("theme")} choices={(["Dark", "Light", "Match system"] as const).map((v) => ({ value: v, label: v, art: <ThemeArt theme={v} hue={look.accentHue} /> }))} />
      </Field>
      <ClockField />
      <Field name="Ink" note="The colour of buttons, today and highlights.">
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
      <Field name="Hours shown" note="How much of the day the calendar shows.">
        <ChoiceCards label="Hours shown" value={look.hours} onPick={pick("hours")} choices={[{ value: "Waking", label: "Waking hours", art: <HoursArt hours="Waking" /> }, { value: "All day", label: "All 24 hours", art: <HoursArt hours="All day" /> }]} />
      </Field>
      <Field name="Deadlines" note="Where things due show on the calendar.">
        <ChoiceCards label="Deadlines" value={look.deadlines} onPick={pick("deadlines")} choices={[{ value: "Chips", label: "Count on top", art: <DeadlinesArt deadlines="Chips" /> }, { value: "Lanes", label: "To-do lane", art: <DeadlinesArt deadlines="Lanes" /> }]} />
      </Field>
      <Field name="Calendar blocks" note="Edged and light, or filled with colour.">
        <ChoiceCards
          label="Calendar blocks"
          value={look.blocks}
          onPick={pick("blocks")}
          choices={(["Soft", "Solid"] as const).map((mode) => ({
            value: mode,
            label: mode,
            art: <BlocksArt skins={[265, 155].map((hue) => skinFor("planned", areaHex(hue, light), { ...look, blocks: mode }, skinOf))} />,
          }))}
        />
      </Field>
      <Field name="Glow" note="A soft light, on the dark theme only.">
        <ChoiceCards label="Glow" value={look.glow} onPick={pick("glow")} choices={[{ value: "Off", label: "Off", art: <GlowArt glow="Off" hue={look.accentHue} /> }, { value: "Today", label: "Today", art: <GlowArt glow="Today" hue={look.accentHue} /> }, { value: "More", label: "Today + more", art: <GlowArt glow="More" hue={look.accentHue} /> }]} />
        {light && <span className="fr-kicker">Switch to dark to see it.</span>}
      </Field>
      <Field name="Floating panels" note="The Now bar, Shove, Pace and sidebar.">
        <ChoiceCards label="Floating panels" value={look.chrome} onPick={pick("chrome")} choices={(["Tonal", "Shadow", "Flat", "Outline"] as const).map((v) => ({ value: v, label: v, art: <ChromeArt chrome={v} light={light} /> }))} />
      </Field>
      <Field name="Now bar" note="Everything at hand, or just the essentials.">
        <ChoiceCards label="Now bar" value={look.dockStyle} onPick={pick("dockStyle")} choices={[{ value: "Bar", label: "Full bar", art: <NowBarArt dock="Bar" /> }, { value: "Minimal", label: "Minimal", art: <NowBarArt dock="Minimal" /> }]} />
      </Field>
      <Field name="Headings" note="The typeface for titles, dates and numbers.">
        <ChoiceCards label="Heading face" value={look.headFont} onPick={pick("headFont")} choices={(["Serif", "Archivo", "Inter"] as const).map((v) => ({ value: v, label: v, art: <FaceArt font={v} weight={look.headWeight} /> }))} />
      </Field>
      <Field name="Heading weight" note="How heavy titles and dates look.">
        <ChoiceCards label="Heading weight" value={look.headWeight} onPick={pick("headWeight")} choices={(["Bold", "Black"] as const).map((v) => ({ value: v, label: v, art: <FaceArt font={look.headFont} weight={v} /> }))} />
      </Field>
    </>
  )
}

/** 12-hour or 24-hour times: saved to Friday, so it's the same on every device you open Friday on. */
function ClockField() {
  const clock: Clock = (useSettings().data as { clock?: Clock } | undefined)?.clock === "24h" ? "24h" : "12h"
  const save = useCommand("settings_set", { label: () => "Clock saved" })
  return (
    <Field name="Clock" note="How every time reads: on each device, the command line and Siri too.">
      <ChoiceCards
        label="Clock"
        value={clock}
        onPick={(value) => value !== clock && void save({ key: "clock", value })}
        choices={[
          { value: "12h", label: "12-hour", art: <ClockArt clock="12h" /> },
          { value: "24h", label: "24-hour", art: <ClockArt clock="24h" /> },
        ]}
      />
    </Field>
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
