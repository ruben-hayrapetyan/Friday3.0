// Quick-add's hooks (DESIGN §18.5): `parse` as you type, `add`, and the AI fallback for a line the grammar can't read
// (§22.7). The add box (todo/AddBox.tsx) and the drawer draw them.

import { useEffect, useState } from "react"
import { command, errorWords, query, type Schemas } from "@/api/client"
import { useCommand } from "@/hooks/useCommand"

type Parsed = Schemas["ParseOutput"]


/** How a quick-add line reads, asked of the server 120 ms after typing stops. An answer that comes once the line has
 * changed is dropped (the audit, 12 Nov: "essay fri"'s came after the box was emptied, and showed its due on nothing). */
export function useParsed(text: string): Parsed | null {
  const [parsed, setParsed] = useState<Parsed | null>(null)
  useEffect(() => {
    if (!text.trim()) return setParsed(null)
    let gone = false
    const timer = setTimeout(() => query("parse", { text }).then((p) => gone || setParsed(p), () => gone || setParsed(null)), 120)
    return () => {
      gone = true
      clearTimeout(timer)
    }
  }, [text])
  return parsed
}

export function useAdd() {
  return useCommand("add", {
    label: (out) => `Added ${out.result.item?.title ?? ""}${out.result.occurrences ? ` (${out.result.occurrences})` : ""}`,
  })
}

/** The quick-add AI fallback (DESIGN §22.7): what it read, held until you press Enter; editing the line forgets it. */
export function useAsk(text: string) {
  const [result, setResult] = useState<{ for: string; fields: Record<string, unknown> } | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const ask = async () => {
    setBusy(true)
    setError(null)
    try {
      const out = await command("ask_ai", { text })
      setResult({ for: text, fields: out.result as Record<string, unknown> })
    } catch (e) {
      setError(errorWords(e))
    }
    setBusy(false)
  }
  return { fields: result && result.for === text ? result.fields : null, ask, busy, error }
}

export interface Read {
  preset: string | null
  area: string | null
  due: string | null
  duration_min: number | null
  every: string | null
  per_window: number | null
}

/** The fields a line was read as, whether by the grammar (its own names) or the AI (the add command's). */
export function readFields(f: Record<string, unknown>): Read {
  const text = (k: string) => (typeof f[k] === "string" ? (f[k] as string) : null)
  const num = (k: string) => (typeof f[k] === "number" ? (f[k] as number) : null)
  const units = num("duration_units")
  const rule = text("rrule")
  return {
    preset: text("preset"),
    area: text("area"),
    due: text("due") ?? text("due_local"),
    duration_min: num("duration_min") ?? (units !== null ? units * 15 : null),
    every: text("every") ?? (rule ? `rrule:${rule}` : null),
    per_window: num("per_window"),
  }
}
