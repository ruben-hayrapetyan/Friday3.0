// Small preferences for this device only (no plan depends on them): the Now dock's "More time" presets.

const KEY = "friday-ui"

export function moreTimePresets(): number[] {
  try {
    const saved = JSON.parse(localStorage.getItem(KEY) ?? "{}").moreTime
    return Array.isArray(saved) && saved.length ? saved : [15, 30, 60]
  } catch {
    return [15, 30, 60]
  }
}

export function setMoreTimePresets(minutes: number[]): void {
  try {
    const all = JSON.parse(localStorage.getItem(KEY) ?? "{}")
    localStorage.setItem(KEY, JSON.stringify({ ...all, moreTime: minutes }))
  } catch {
    // private mode: the default presets stay
  }
}
