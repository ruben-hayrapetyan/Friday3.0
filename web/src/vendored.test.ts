// The copies Friday keeps of others' code (12 Nov, before the repo went public): deepmerge with the prototype keys
// never written (GHSA-gcqx-w48m-w2h4 has no fixed release), and shadcn's Tailwind layer without its package.
import { readFileSync } from "node:fs"
import { createRequire } from "node:module"
import { describe, expect, it } from "vitest"

const require = createRequire(import.meta.url)
const merge = require("../vendor/deepmerge") as (a: unknown, b: unknown) => Record<string, unknown>

describe("deepmerge, patched", () => {
  it("merges as deepmerge 4.3.1 does", () => {
    expect(merge({ a: { b: 1 }, list: [1] }, { a: { c: 2 }, list: [2] })).toEqual({ a: { b: 1, c: 2 }, list: [1, 2] })
  })

  it("never gives the result another prototype, from either side", () => {
    const poison = JSON.parse('{"__proto__": {"polluted": "yes"}, "constructor": {"prototype": {"polluted": "yes"}}}')
    for (const out of [merge(poison, {}), merge({}, poison), merge({ x: 1 }, { nested: poison })]) {
      expect(Object.getPrototypeOf(out)).toBe(Object.prototype)
      expect((out as { polluted?: string }).polluted).toBeUndefined()
      expect(({} as { polluted?: string }).polluted).toBeUndefined()
    }
  })

  it("is the only deepmerge the build uses", () => {
    const lock = readFileSync(new URL("../pnpm-lock.yaml", import.meta.url), "utf8")
    expect(lock).toContain("deepmerge@file:vendor/deepmerge")
    expect(lock).not.toMatch(/deepmerge@\d/)
  })
})

describe("shadcn's Tailwind layer", () => {
  it("is Friday's own file, with its licence", () => {
    expect(readFileSync(new URL("./index.css", import.meta.url), "utf8")).toContain('@import "./theme/shadcn-tailwind.css"')
    expect(readFileSync(new URL("./theme/shadcn-tailwind.css", import.meta.url), "utf8")).toContain("Copyright (c) 2023 shadcn")
  })
})
