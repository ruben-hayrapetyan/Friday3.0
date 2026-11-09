// What "Update it" changes on the task you already have, said before you press it (9 Nov: an email's "PS11" took the
// name of "Chem 2090 Problem Set 11", which then looked deleted). Your name for it stays; dates and length follow
// what was found.

import { dur, when } from "@/lib/format"

type Has = { title: string; due?: string | null; start?: string | null; end?: string | null; duration_min?: number | null }

export function updateSays(found: Record<string, unknown>, have: Has, today: string): string {
  const changes: string[] = []
  const at = (key: "due" | "start" | "end", words: string) => {
    const v = found[key]
    if (typeof v === "string" && v && v !== have[key]) changes.push(`${words} ${when(v, today)}`)
  }
  at("due", "due")
  at("start", "starts")
  at("end", "ends")
  const length = found.duration_min
  if (typeof length === "number" && length !== have.duration_min) changes.push(`${dur(length)} long`)
  const name = `“${have.title}” keeps its name`
  return changes.length ? `Accepting makes it ${changes.join(", ")}; ${name}.` : `Nothing about it changes; ${name}.`
}
