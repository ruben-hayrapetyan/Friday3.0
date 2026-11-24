// The Rules page's order (23 Nov: "organize rules based on either importance or alphabetically"; your choice:
// strongest first, A–Z within each strength): Always, then Strongly, then Prefer, each A–Z by what the rule says;
// rules switched off last, as they don't count while off.

const RANK: Record<string, number> = { Always: 0, Strongly: 1, Prefer: 2 }

export function inOrder<T extends { sentence: string; strength: string; enabled: boolean }>(rules: T[]): T[] {
  return [...rules].sort(
    (a, b) =>
      Number(!a.enabled) - Number(!b.enabled) ||
      (RANK[a.strength] ?? 3) - (RANK[b.strength] ?? 3) ||
      a.sentence.localeCompare(b.sentence, undefined, { sensitivity: "base" }),
  )
}
