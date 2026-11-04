// Settings → Calendars → Categories: which categories one can be folded into (3 Nov). Only saved ones: the server
// merges what's saved, so a category typed but not saved yet is neither merged nor merged into.

/** The other saved categories `name` can go into, each once, in the order you keep them. */
export function mergeTargets(saved: { categories: readonly { name: string }[] }, name: string): string[] {
  if (!saved.categories.some((c) => c.name === name)) return []
  return [...new Set(saved.categories.map((c) => c.name.trim()).filter((n) => n && n !== name.trim()))]
}
