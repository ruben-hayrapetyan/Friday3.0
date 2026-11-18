// Build tools stay out of the app's runtime dependencies (17 Nov: GitHub rated picomatch's ReDoS, which comes in only
// through Vite, "runtime" because the Tailwind Vite plugin was listed with the app's own dependencies; nothing of it
// is in the built app).
import { readFileSync } from "node:fs"
import path from "node:path"
import { describe, expect, it } from "vitest"

const pkg = JSON.parse(readFileSync(path.resolve(__dirname, "../package.json"), "utf8")) as { dependencies: Record<string, string> }
const BUILD_ONLY = /^(vite|vitest|@vitejs\/|@tailwindcss\/vite$|tailwindcss$|@vitest\/|typescript$|eslint)/

describe("the app's runtime dependencies", () => {
  it("hold no build or test tools", () => {
    expect(Object.keys(pkg.dependencies).filter((d) => BUILD_ONLY.test(d))).toEqual([])
  })
})
