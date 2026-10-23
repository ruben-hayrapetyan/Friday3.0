// Lengths typed the way people say them (COMBINED.md 42), ported from personal's Minutes.parse
// (UI/Sources/Planner/Lengths.swift): "90", "2h", "1h30", "1:30", "an hour and a half", "half an hour", "forty-five
// minutes", "a couple of hours", "2-3 hours" (the middle), "about 2h or so". A number on its own is hours up to 8
// and minutes above. Null when any word can't be read, so a typo shows rather than being guessed at.

const UNITS: Record<string, number> = { h: 60, hr: 60, hrs: 60, hour: 60, hours: 60, m: 1, min: 1, mins: 1, minute: 1, minutes: 1 }
const NUMBER_WORDS: Record<string, number> = {
  a: 1, an: 1, one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9, ten: 10, eleven: 11,
  twelve: 12, fifteen: 15, twenty: 20, thirty: 30, forty: 40, fourty: 40, fifty: 50, sixty: 60, ninety: 90,
  couple: 2, few: 3, several: 3,
} // prettier-ignore
const FILLERS = new Set([
  "about", "around", "maybe", "like", "roughly", "approx", "approximately", "probably", "prob", "i", "think", "guess",
  "it", "it'll", "itll", "will", "would", "take", "takes", "took", "me", "should", "be", "ish", "or", "so", "of", "and",
  "the", "just", "under", "over", "at", "most", "least", "max", "tops", "only", "-",
]) // prettier-ignore

export function parseLength(raw: string): number | null {
  let text = ` ${raw.toLowerCase()} `
  const replace = (pattern: RegExp, template: string) => (text = text.replace(pattern, template))
  replace(/[–—]/g, "-")
  replace(/[~?!,;]/g, " ")
  replace(/-?ish\b/g, " ish")
  replace(/\bthree[- ]quarters? of an? hour\b/g, " 45 min ")
  replace(/\b(?:a )?quarter[- ](?:of an )?hour\b/g, " 15 min ")
  replace(/\b(?:a )?half[- ]?(?:an )?hour\b/g, " 30 min ")
  replace(/\band (?:a|one) half\b/g, " and_half ")
  replace(/\ba (couple|few)\b/g, " $1 ")
  replace(/([a-z])-([a-z])/g, "$1 $2")
  replace(/(\d+):(\d{2})\b/g, " $1 h $2 m ")
  replace(/(\d)([a-z])/g, "$1 $2")
  replace(/([a-z])(\d)/g, "$1 $2")
  replace(/(\d)\s*-\s*(\d)/g, "$1 - $2")

  const tokens = text.split(/\s+/).filter(Boolean)
  let total = 0
  let first: number | null = null
  let pending: number | null = null
  let rangeFrom: number | null = null
  let lastUnit: number | null = null
  let sawHours = false
  for (let i = 0; i < tokens.length; i++) {
    const token = tokens[i]
    const n = /^\d+(\.\d+)?$/.test(token) ? Number(token) : NUMBER_WORDS[token]
    if (n !== undefined) {
      if (pending !== null) {
        // "forty five": tens then units.
        if (!(pending >= 20 && pending % 10 === 0 && n < 10)) return null
        pending += n
      } else if (rangeFrom !== null) {
        pending = (rangeFrom + n) / 2
        rangeFrom = null
      } else {
        pending = n
      }
    } else if (token in UNITS) {
      const unit = UNITS[token]
      total += (pending ?? rangeFrom ?? 1) * unit
      pending = null
      rangeFrom = null
      lastUnit = unit
      sawHours = sawHours || unit === 60
    } else if (token === "and_half") {
      if (pending !== null) pending += 0.5
      else if (lastUnit !== null) total += lastUnit / 2
      else return null
    } else if (["-", "to", "or"].includes(token) && tokens[i + 1] !== "so") {
      if (pending !== null) {
        rangeFrom = pending
        pending = null
      } else if (total > 0 && first === null) {
        // "2 hours to 3 hours": two lengths, the middle of them.
        first = total
        total = 0
        lastUnit = null
        sawHours = false
      }
    } else if (!FILLERS.has(token)) {
      return null
    }
  }
  if (pending !== null) {
    if (sawHours) total += pending // "1h 30"
    else if (total === 0) total = pending <= 8 ? pending * 60 : pending
    else return null
  }
  if (first !== null) total = total > 0 ? (first + total) / 2 : first
  return total > 0 && total <= 100 * 60 ? total : null
}

/** 135 → "2h 15m"; 45 → "45m". */
export function lengthLabel(minutes: number): string {
  const m = Math.round(minutes)
  if (m < 60) return `${m}m`
  return m % 60 === 0 ? `${m / 60}h` : `${Math.floor(m / 60)}h ${m % 60}m`
}
