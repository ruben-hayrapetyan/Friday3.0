// React's rule of hooks, checked over the source (27 Oct: `selected || usePicks()` skipped a hook whenever a block was
// selected; React threw on the next render and the window went black). A component calls the same hooks in the same
// order every render: never after `||`, `&&`, `??` or `?`, never inside an `if`, never after an early return. There is
// no linter here, so this reads the code as Prettier lays it out: a component's body two spaces in.

import { describe, expect, it } from "vitest"

const files = import.meta.glob(["./**/*.tsx", "./**/*.ts", "!./**/*.test.ts", "!./**/*.test.tsx", "!./api/schema.ts"], {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>

const HOOK = /\buse[A-Z]\w*\(/
const CONDITIONAL = /(\|\||&&|\?\?|\?)\s*!*use[A-Z]\w*\(/
const OPENS = /^(export )?(default )?function (use[A-Z]\w*|[A-Z]\w*)\b/

/** Each top-level component or hook: its name and its body's lines, with their line numbers. */
function bodies(source: string): { name: string; lines: [number, string][] }[] {
  const lines = source.split("\n")
  const out: { name: string; lines: [number, string][] }[] = []
  for (let i = 0; i < lines.length; i++) {
    const head = OPENS.exec(lines[i])
    if (!head) continue
    const body: [number, string][] = []
    for (let j = i + 1; j < lines.length && lines[j] !== "}"; j++) body.push([j + 1, lines[j]])
    out.push({ name: head[3], lines: body })
  }
  return out
}

/** Where a body breaks the rule: a conditional call, a call inside an `if`, or a call after an early return. */
export function broken(source: string): string[] {
  const found: string[] = []
  for (const { name, lines } of bodies(source)) {
    let returned = false
    let inIf = false
    let ifReturns = false
    for (const [n, line] of lines) {
      const direct = /^ {2}\S/.test(line)
      const statement = line.trimStart()
      const callsHook = (/^(const|let) [^=]+= *!*use[A-Z]\w*\(/.test(statement) || /^use[A-Z]\w*\(/.test(statement)) && HOOK.test(line)
      if (CONDITIONAL.test(line) && !statement.startsWith("//")) found.push(`${name}:${n} calls a hook conditionally: ${statement}`)
      if (inIf) {
        if (/^ {2}\}/.test(line)) {
          inIf = false
          if (ifReturns) returned = true
          if (!/^ {2}\} else/.test(line)) continue
          inIf = true
        }
        if (/^ {4}return\b/.test(line)) ifReturns = true
        if (/^ {4}\S/.test(line) && callsHook) found.push(`${name}:${n} calls a hook inside an if: ${statement}`)
        continue
      }
      if (!direct) continue
      if (returned && callsHook) found.push(`${name}:${n} calls a hook after an early return: ${statement}`)
      if (/^if \(.*\) return\b/.test(statement) || /^if \(.*\) \(?[a-z]\w*\([^)]*\), return\b/.test(statement)) returned = true
      if (/^if \(.*\) \{$/.test(statement)) {
        inIf = true
        ifReturns = false
      }
      if (/^return\b/.test(statement)) returned = true
    }
  }
  return found
}

describe("the rule of hooks", () => {
  it("finds what broke the window on 27 Oct, and the other ways to break it", () => {
    const or = "export function PlanPage() {\n  const block = !!useShell().selected || usePicks().length > 0\n  return null\n}"
    const early = "function Card({ id }: { id: number }) {\n  if (!id) return null\n  const item = useItem(id)\n  return item\n}"
    const inside = "function Card({ id }: { id: number }) {\n  if (id) {\n    const item = useItem(id)\n  }\n  return null\n}"
    const after = "function Card({ id }: { id: number }) {\n  if (!id) {\n    return null\n  }\n  const [a] = useState(0)\n  return a\n}"
    const fine = "function Card({ id }: { id: number }) {\n  const item = useItem(id)\n  useEffect(() => {\n    if (id) return\n  })\n  if (!item) return null\n  return item\n}"
    expect(broken(or)).toHaveLength(1)
    expect(broken(early)).toHaveLength(1)
    expect(broken(inside)).toHaveLength(1)
    expect(broken(after)).toHaveLength(1)
    expect(broken(fine)).toEqual([])
  })

  it("holds in every component and hook of the app", () => {
    expect(Object.keys(files).length).toBeGreaterThan(100) // it read the app (149 files on 27 Oct), not nothing
    expect(Object.keys(files)).toContain("./plan/PlanPage.tsx")
    const found = Object.entries(files).flatMap(([path, source]) => broken(source).map((b) => `${path} ${b}`))
    expect(found).toEqual([])
  })
})
