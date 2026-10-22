// Buffers live in the `buffer` rule's parameters (DESIGN §12.2): a default and one per tag and per kind.

import { useCommand } from "@/hooks/useCommand"
import { useSettings } from "@/hooks/queries"

export interface RuleSpec {
  type: string
  name: string
  weight: number
  params: Record<string, unknown>
  [key: string]: unknown
}

export interface Buffers {
  minutes: string
  by_area: Record<string, string>
  by_preset: Record<string, string>
}

export const BUFFER_OPTIONS = ["0m", "15m", "30m", "45m"]
export const bufferLabel = (v: string) => (v === "0m" ? "None" : v.replace("m", " min"))

export function useBuffers(): { buffers: Buffers; set: (change: Partial<Buffers>) => void } {
  const settings = useSettings().data as Record<string, unknown> | undefined
  const save = useCommand("settings_set", { label: () => "Buffer saved" })
  const rules = (settings?.rules as RuleSpec[]) ?? []
  const rule = rules.find((r) => r.type === "buffer")
  const p = (rule?.params ?? {}) as Partial<Buffers>
  const buffers = { minutes: String(p.minutes ?? "0m"), by_area: p.by_area ?? {}, by_preset: p.by_preset ?? {} }
  const set = (change: Partial<Buffers>) => {
    const params = { ...buffers, ...change }
    const next = rule
      ? rules.map((r) => (r === rule ? { ...r, params } : r))
      : [...rules, { type: "buffer", name: "buffer", weight: 3, params }]
    save({ key: "rules", value: next })
  }
  return { buffers, set }
}
