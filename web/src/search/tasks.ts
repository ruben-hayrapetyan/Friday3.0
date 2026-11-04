// The tasks ⌘K finds (3 Nov: "items marked as done still show up in my cmd k"; it asked for every task, done,
// deleted and skipped too, and kept the first eight that matched). Only what's still open, a title starting with
// what you typed first.

interface Task {
  id: number
  title: string
  status: string
}

export function openMatches<T extends Task>(items: readonly T[], typed: string, limit = 8): T[] {
  const q = typed.trim().toLowerCase()
  const open = items.filter((i) => i.status === "todo" && i.title.toLowerCase().includes(q))
  const starts = (i: T) => (q && i.title.toLowerCase().startsWith(q) ? 0 : 1)
  return open
    .map((i, n) => ({ i, n }))
    .sort((a, b) => starts(a.i) - starts(b.i) || a.n - b.n)
    .slice(0, limit)
    .map(({ i }) => i)
}
