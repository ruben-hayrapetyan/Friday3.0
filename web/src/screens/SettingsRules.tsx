// Settings that change rules (DESIGN §17.5): a few plain-language preferences, and any key as JSON (the expert
// Rules view). Both show a full preview's change list before saving.

import { useState } from "react"
import { command, type Schemas } from "@/api/client"
import { ChangeList } from "@/components/ChangeList"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { useCommand } from "@/hooks/useCommand"
import { useStatus } from "@/hooks/queries"
import { hours } from "@/lib/format"

interface Rule {
  type: string
  name: string
  params: Record<string, unknown>
}

// Each control edits one parameter of a reference rule, found by name; a control whose rule is gone is hidden.
const CONTROLS: [string, string, string][] = [
  ["Keep free on weekday evenings", "weekday_evenings", "free"],
  ["Keep free on weekends", "weekends", "free"],
  ["Daily load soft limit", "daily_load", "threshold"],
  ["Longest deep stretch", "deep_run", "threshold"],
]

type Settings = Record<string, unknown>

export function Preferences({ settings, today }: { settings: Settings; today: string }) {
  const saved = settings.rules as Rule[]
  const [rules, setRules] = useState(saved)
  const set = (name: string, param: string, value: string) =>
    setRules(rules.map((r) => (r.name === name ? { ...r, params: { ...r.params, [param]: `${Number(value)}h` } } : r)))
  const changed = JSON.stringify(rules) !== JSON.stringify(saved)
  return (
    <div className="space-y-2">
      {CONTROLS.map(([label, name, param]) => {
        const rule = rules.find((r) => r.name === name)
        if (!rule) return null
        return (
          <label key={name} className="flex items-center gap-3">
            <span className="flex-1">{label}</span>
            <Input
              type="number"
              className="h-8 w-20"
              min={0}
              max={24}
              step={0.5}
              value={hours(String(rule.params[param] ?? ""))}
              onChange={(e) => set(name, param, e.target.value)}
            />
            <span className="w-40 text-xs text-muted-foreground">
              hours · {rule.type} {name}.{param}
            </span>
          </label>
        )
      })}
      <PreviewSave settingKey="rules" value={changed ? rules : null} today={today} onReset={() => setRules(saved)} />
    </div>
  )
}

export function Advanced({ settings, today }: { settings: Settings; today: string }) {
  const [key, setKey] = useState("rules")
  const [text, setText] = useState(() => JSON.stringify(settings.rules, null, 2))
  let value: unknown = null
  let error: string | null = null
  try {
    value = JSON.parse(text)
  } catch (e) {
    error = (e as Error).message
  }
  const changed = !error && JSON.stringify(value) !== JSON.stringify(settings[key])
  const pick = (k: string) => {
    setKey(k)
    setText(JSON.stringify(settings[k], null, 2))
  }
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1">
        {Object.keys(settings).map((k) => (
          <Button key={k} size="xs" variant={k === key ? "secondary" : "ghost"} onClick={() => pick(k)}>
            {k}
          </Button>
        ))}
      </div>
      <Textarea className="h-80 font-mono text-xs" spellCheck={false} value={text} onChange={(e) => setText(e.target.value)} />
      {error && <p className="text-destructive">{error}</p>}
      <PreviewSave
        settingKey={key}
        value={changed ? value : null}
        today={today}
        onReset={() => setText(JSON.stringify(settings[key], null, 2))}
      />
    </div>
  )
}

interface PreviewProps {
  settingKey: string
  value: unknown // null while nothing changed
  today: string
  onReset: () => void
}

function PreviewSave({ settingKey, value, today, onReset }: PreviewProps) {
  const owned = (useStatus().data?.config_keys ?? []).includes(settingKey)
  const [changes, setChanges] = useState<{ of: unknown; out: Schemas["ChangeOut"] | null } | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const save = useCommand("settings_set")
  const preview = async () => {
    setBusy(true)
    setError(null)
    try {
      const out = await command("settings_set", { key: settingKey, value }, { preview: "full" })
      setChanges({ of: value, out: out.changes ?? null })
    } catch (e) {
      setError((e as Error).message)
    }
    setBusy(false)
  }
  // A preview of an earlier edit says nothing about this one.
  const shown = changes && JSON.stringify(changes.of) === JSON.stringify(value) ? changes.out : null
  return (
    <div className="space-y-2">
      {(shown || busy) && <ChangeList changes={shown} today={today} busy={busy} />}
      {error && <p className="text-destructive">{error}</p>}
      <div className="flex gap-2">
        <Button size="sm" variant="outline" disabled={value === null || busy} onClick={preview}>
          Preview
        </Button>
        <Button size="sm" disabled={value === null || owned} onClick={() => save({ key: settingKey, value })}>
          {owned ? "Set in friday.toml" : "Save"}
        </Button>
        <Button size="sm" variant="ghost" disabled={value === null} onClick={onReset}>
          Reset
        </Button>
      </div>
    </div>
  )
}
