// Once a run, before the screen tests: Alex's three lived-in weeks built (about 20 seconds), Friday's terms accepted
// and Setup's questions answered as they stand, then the server stopped; each test file serves a copy (setup.ts).

import { mkdtempSync, rmSync } from "node:fs"
import { tmpdir } from "node:os"
import path from "node:path"
import type { TestProject } from "vitest/node"
import { freePort, serve, shiftToThursday, stop } from "./server"

export default async function setup(project: TestProject) {
  const folder = mkdtempSync(path.join(tmpdir(), "friday-sample-"))
  const port = await freePort()
  const shiftMinutes = shiftToThursday() // one shift for the whole run: the server and every file's page agree
  const server = await serve(folder, port, 240, shiftMinutes)
  const base = `http://127.0.0.1:${port}`
  const terms = (await (await fetch(`${base}/api/q/terms`)).json()) as { version: string; needed: boolean }
  if (terms.needed) {
    const accepted = await fetch(`${base}/api/c/terms_accept`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ version: terms.version }) })
    if (!accepted.ok) throw new Error(`terms_accept: ${accepted.status} ${await accepted.text()}`)
  }
  // through Setup's questions and offered the tour, as anyone a few weeks in: the screens open on the page itself
  const post = (name: string, body: unknown) => fetch(`${base}/api/c/${name}`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) })
  const setup = (await (await fetch(`${base}/api/q/setup`)).json()) as { done: boolean; answers: Record<string, unknown> }
  if (!setup.done) {
    const saved = await post("setup_save", { ...setup.answers, brief: false })
    if (!saved.ok) throw new Error(`setup_save: ${saved.status} ${await saved.text()}`)
  }
  await post("tour_offered", {})
  await stop(server)
  project.provide("fridaySample", folder)
  project.provide("fridayShiftMinutes", shiftMinutes)
  return () => rmSync(folder, { recursive: true, force: true })
}

declare module "vitest" {
  export interface ProvidedContext {
    fridaySample: string
    fridayShiftMinutes: number
  }
}
