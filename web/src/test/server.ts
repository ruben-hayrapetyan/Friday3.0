// A real Friday for the screen tests (11 Nov: "write tests to get the coverage higher or at least cover all
// functionalities"): `fridayd demo` with Alex, a sample first-year three weeks into using Friday (sim/history.py),
// on a port of its own. Built once a run (globalSetup.ts); each test file serves its own copy, so what one changes
// another never sees. Node only: the screens reach it through fetch (setup.ts).

import { type ChildProcess, spawn } from "node:child_process"
import { cpSync, mkdtempSync } from "node:fs"
import { get } from "node:http"
import { createServer } from "node:net"
import { tmpdir } from "node:os"
import path from "node:path"

export const REPO = path.resolve(__dirname, "../../..")
export const CASE = "alex"

/** A port nothing is listening on. */
export function freePort(): Promise<number> {
  return new Promise((done, fail) => {
    const probe = createServer()
    probe.once("error", fail)
    probe.listen(0, "127.0.0.1", () => {
      const { port } = probe.address() as { port: number }
      probe.close(() => done(port))
    })
  })
}

/** `fridayd demo` over `folder` on `port`; resolves once it answers. */
export async function serve(folder: string, port: number, seconds = 240): Promise<ChildProcess> {
  // Made-up app keys (integrations/keys.py reads FRIDAY_<NAME> first): the services' boxes are ready whether or not
  // this checkout has the gitignored Mac/app_keys.json, as on a contributor's fork or GitHub's checks
  const keys = { MICROSOFT_CLIENT_ID: "test-microsoft-id", SLACK_CLIENT_ID: "test-slack-id", SLACK_CLIENT_SECRET: "test-slack-secret", TICKTICK_CLIENT_ID: "test-ticktick-id", TICKTICK_CLIENT_SECRET: "test-ticktick-secret", TRELLO_CLIENT_ID: "test-trello-id" }
  const env: NodeJS.ProcessEnv = { ...process.env, ...Object.fromEntries(Object.entries(keys).map(([k, v]) => [`FRIDAY_${k}`, v])) }
  delete env.VIRTUAL_ENV
  const child = spawn("uv", ["run", "--quiet", "fridayd", "--data-dir", folder, "demo", "--case", CASE, "--ready", "--port", String(port)], {
    cwd: REPO,
    env,
    stdio: ["ignore", "ignore", "pipe"],
  })
  let said = ""
  child.stderr?.on("data", (d: Buffer) => (said = (said + d.toString()).slice(-4000)))
  const until = Date.now() + seconds * 1000
  while (Date.now() < until) {
    if (child.exitCode !== null) throw new Error(`fridayd demo stopped (${child.exitCode}):\n${said}`)
    if (await answers(port)) return child
    await new Promise((r) => setTimeout(r, 250))
  }
  child.kill("SIGKILL")
  throw new Error(`fridayd demo didn't answer in ${seconds}s:\n${said}`)
}

/** Whether Friday answers on `port` yet (Node's own HTTP: a page's fetch would be held to the page's origin). */
function answers(port: number): Promise<boolean> {
  return new Promise((done) => {
    const asked = get({ host: "127.0.0.1", port, path: "/api/q/status", timeout: 2000 }, (r) => (r.resume(), done(r.statusCode === 200)))
    asked.on("error", () => done(false))
    asked.on("timeout", () => (asked.destroy(), done(false)))
  })
}

export function stop(child: ChildProcess): Promise<void> {
  return new Promise((done) => {
    if (child.exitCode !== null) return done()
    child.once("exit", () => done())
    child.kill("SIGTERM")
    setTimeout(() => child.kill("SIGKILL"), 3000)
  })
}

/** A copy of the sample built this run, for one test file. */
export function copyOf(built: string): string {
  const folder = mkdtempSync(path.join(tmpdir(), "friday-screens-"))
  cpSync(built, folder, { recursive: true })
  return folder
}
