// picomatch's ReDoS (CVE-2026-112366, GHSA-fc5q-39xc-vjpf; Dependabot, 17 Nov): `+(*a)` against a run of a's backtracks
// exponentially, and picomatch has no fixed release yet. Friday's patch (web/patches/picomatch@4.0.7.patch, applied by
// pnpm at install) matches such a repeated wildcard literally, as picomatch does its other risky extglobs. Vite uses
// picomatch at build time only; nothing of it ships.
import picomatch from "picomatch"
import { describe, expect, it } from "vitest"

const timed = (pattern: string, input: string) => {
  const re = picomatch.makeRe(pattern)
  const start = performance.now()
  re.test(input)
  return performance.now() - start
}

describe("picomatch, patched", () => {
  it("doesn't backtrack on a repeated wildcard extglob", () => {
    // unpatched, 26 a's took about half a second and each one more doubles it
    for (const pattern of ["+(*a)", "*(*a)", "+(*)", "+(?a)"]) expect(timed(pattern, `${"a".repeat(26)}!`)).toBeLessThan(50)
    expect(picomatch.isMatch("+(*a)", "+(*a)")).toBe(true) // matched literally
  })

  it("matches ordinary globs as before", () => {
    expect(picomatch.isMatch("a/node_modules/b.js", "**/node_modules/**")).toBe(true)
    expect(picomatch.isMatch("x.tsx", "*.{ts,tsx}")).toBe(true)
    expect(picomatch.isMatch("src/a/b.test.ts", "src/**/*.test.ts")).toBe(true)
    expect(picomatch.isMatch("ab", "+(a|b)")).toBe(true)
    expect(picomatch.isMatch("aab", "+(*(a)|*(b))")).toBe(true)
    expect(picomatch.isMatch("x.ts", "!(*.d).ts")).toBe(true)
  })
})
