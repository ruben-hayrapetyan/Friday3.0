// Advanced (not in v22, kept so nothing the app could do is lost): what Friday learns and how, saved paces and their
// dials, plugins, and any settings key as JSON with a full preview before saving.

import { useState } from "react"
import { LearningSettings } from "@/components/Learning"
import { H, Icon } from "@/components/fr/controls"
import { useCommand } from "@/hooks/useCommand"
import { usePaces, useSettings, useStatus } from "@/hooks/queries"
import { Advanced } from "@/screens/SettingsRules"
import { useShell } from "@/shell/ShellContext"
import { SectionHead } from "./SettingsPage"
import { HeldRange } from "./Held"

const DIALS: [string, number, number][] = [
  ["capacity", 0.3, 1.5],
  ["rest", 0.5, 3],
  ["spread", 0, 5],
  ["growth", 0, 3],
]

export function AdvancedSection() {
  const { today } = useShell()
  const settings = useSettings().data
  return (
    <>
      <SectionHead title="Advanced" note="What Friday learns, saved paces, plugins, and every setting by name." />
      <Block title="Learning">
        <LearningSettings />
      </Block>
      <Block title="Saved paces">
        <Paces />
      </Block>
      <Block title="Plugins">
        <Plugins allowed={!!(settings?.server as { allow_plugins?: boolean } | undefined)?.allow_plugins} />
      </Block>
      <Block title="Every setting">{settings && <Advanced settings={settings} today={today} />}</Block>
    </>
  )
}

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="fr-row" style={{ display: "flex", flexDirection: "column", gap: 12, padding: "20px 0" }}>
      <H size={18}>{title}</H>
      {children}
    </section>
  )
}

function Paces() {
  const paces = usePaces().data
  const save = useCommand("pace_save", { label: (o) => o.result.message ?? "Saved" })
  const remove = useCommand("pace_delete", { label: (o) => o.result.message ?? "Deleted" })
  const [name, setName] = useState("")
  if (!paces) return null
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {Object.entries(paces.paces).map(([pace, dials]) => (
        <div key={pace} style={{ display: "grid", gridTemplateColumns: "100px repeat(4, minmax(0,1fr)) 28px", gap: 10, alignItems: "center" }}>
          <span style={{ fontWeight: 500 }}>
            {pace}
            {pace === paces.default && <span className="fr-kicker"> · default</span>}
          </span>
          {DIALS.map(([dial, lo, hi]) => (
            <label key={dial} style={{ display: "flex", flexDirection: "column", gap: 2, fontSize: 11, color: "var(--color-neutral-500)" }}>
              {dial} {dials[dial]?.toFixed(1)}
              <HeldRange min={lo} max={hi} step={0.1} value={dials[dial]} onSave={(v) => save({ name: pace, [dial]: v })} aria-label={`${pace} ${dial}`} style={{ accentColor: "var(--color-accent)" }} />
            </label>
          ))}
          {pace !== paces.default && pace !== paces.now_label ? (
            <button className="btn btn-icon btn-ghost" onClick={() => remove({ name: pace })} aria-label={`Delete ${pace}`} style={{ width: 28, height: 28, color: "var(--color-neutral-500)" }}>
              <Icon name="trash" />
            </button>
          ) : (
            <span />
          )}
        </div>
      ))}
      <div style={{ display: "flex", gap: 8 }}>
        <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="New pace, e.g. Exam week" aria-label="New pace" style={{ width: 220, padding: "5px 8px", minHeight: 0 }} />
        <button className="btn btn-secondary" disabled={!name.trim()} onClick={async () => (await save({ name: name.trim(), ...paces.now_dials })) && setName("")} style={{ fontSize: 12 }}>
          Save the dials in use
        </button>
      </div>
    </div>
  )
}

function Plugins({ allowed }: { allowed: boolean }) {
  const problems = (useStatus().data?.problems ?? []).filter((p) => p.toLowerCase().includes("plugin"))
  if (!allowed) return <span className="fr-kicker">Plugins are off (server.allow_plugins).</span>
  return problems.length ? (
    <>
      {problems.map((p) => (
        <span key={p} style={{ color: "var(--fr-due)" }}>
          {p}
        </span>
      ))}
    </>
  ) : (
    <span className="fr-kicker">Every plugin in ~/.config/friday/rules/ loaded.</span>
  )
}
