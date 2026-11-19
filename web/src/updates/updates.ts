// Friday's own updater on the page: the server looks and downloads
// (commands/updates.py); the page asks you, shows what's new, and tells the Mac app to swap the new version in
// (Mac/Sources/Updater.swift), right away or when you quit, as Settings → Updates says.

import { type QueryClient, useQuery, useQueryClient } from "@tanstack/react-query"
import { useCallback, useEffect, useRef } from "react"
import { command, errorWords, query, type Schemas } from "@/api/client"
import { type Toast, useToast } from "@/components/Toasts"
import { inMacApp } from "@/dialogs/Setup"

export type UpdateStatus = Schemas["UpdateStatusOut"]
export type UpdateVersion = Schemas["UpdateVersionOut"]
export type TestUser = Schemas["TestUserOut"]
type Act = "update_check" | "update_later" | "update_start" | "update_stop" | "whats_new_seen" | "update_test_join" | "update_test_leave"

const KEY = ["updates"] as const
const BUSY = new Set(["checking", "downloading"])

/** The updater's state; asked every second while it's looking or downloading, else on `updates.changed`. */
export function useUpdates() {
  return useQuery({
    queryKey: KEY,
    queryFn: () => query("update_status"),
    refetchInterval: (q) => (q.state.data && BUSY.has(q.state.data.state) ? 1000 : false),
  })
}

/** One of the updater's commands; its answer is the new state, shown at once. A refusal ("this Friday is built from
 * its code here", Friday not where it can be replaced) is said in a toast, and the state read again (audit, 12 Nov:
 * it went nowhere, and Update did nothing you could see). Undefined then. */
export async function runUpdateAct(client: QueryClient, toast: (t: Toast) => void, name: Act, input: Record<string, unknown> = {}): Promise<UpdateStatus | undefined> {
  const shown = client.getQueryData<UpdateStatus>(KEY)
  const before = shown && optimistic(shown, name, input)
  if (before) client.setQueryData(KEY, before)
  try {
    const out = await command(name, input as never)
    client.setQueryData(KEY, out.result)
    return out.result
  } catch (error) {
    toast({ message: errorWords(error), tone: "error" })
    void client.invalidateQueries({ queryKey: KEY })
    return undefined
  }
}

export function useUpdateAct() {
  const client = useQueryClient()
  const toast = useToast()
  return useCallback((name: Act, input?: Record<string, unknown>) => runUpdateAct(client, toast, name, input), [client, toast])
}

/** A code as Friday keeps it, from however it was typed ("k7qf 29xm" is K7QF-29XM), or null if it isn't eight letters
 * and digits (H224). */
export function testCode(typed: string): string | null {
  const bare = typed.toUpperCase().replace(/[\s-]/g, "")
  return /^[A-Z0-9]{8}$/.test(bare) ? `${bare.slice(0, 4)}-${bare.slice(4)}` : null
}

/** What joining or leaving shows before the server answers (UI-PRINCIPLES 2: every click shows its result at once). */
function optimistic(status: UpdateStatus, name: Act, input: Record<string, unknown>): UpdateStatus | null {
  if (name === "update_test_leave") return { ...status, test_user: null, versions: (status.versions ?? []).filter((v) => !v.test) }
  const code = name === "update_test_join" ? testCode(String(input.code ?? "")) : null
  return code ? { ...status, state: "checking", test_user: { code, name: null, known: null } } : null
}

/** "You're a test user, as Ana", "Checking your code…", or that the site doesn't know it. */
export function testUserLine(user: TestUser, state: UpdateStatus["state"]): string {
  if (user.known) return user.name ? `You're a test user, as ${user.name}` : "You're a test user"
  if (user.known === false) return "Friday's site doesn't know this code"
  return state === "checking" ? "Checking your code…" : "Your code is checked the next time Friday looks"
}

// Whenever Friday's window opens or comes back into view, the server looks for a new version (H208, 15 Nov: "whenever
// there is a new version, the popup shows up"; it looked once a month). Quietly: a site that can't be reached is said
// in Settings → Updates, not in a toast. At most once in six hours, however often the window comes and goes.
// 19 Nov: every ten minutes read as "CONSTANTLY checking for updates"; your choice "Look less often": six hours
export const LOOK_AGAIN_MS = 6 * 60 * 60_000
let lookedAt = -Infinity

export function useLookWhenOpened(checks: boolean | undefined) {
  const client = useQueryClient()
  useEffect(() => {
    if (!checks) return
    const look = () => {
      if (document.visibilityState !== "visible" || Date.now() - lookedAt < LOOK_AGAIN_MS) return
      lookedAt = Date.now()
      command("update_check", {}).then(
        (out) => client.setQueryData(KEY, out.result),
        () => void client.invalidateQueries({ queryKey: KEY }),
      )
    }
    look()
    document.addEventListener("visibilitychange", look)
    return () => document.removeEventListener("visibilitychange", look)
  }, [checks, client])
}

/** Whether the popup is up: asked for (Settings → Updates), or a newer version is offered or downloading, unless you
 * closed it for that same version (a newer one opens it again, H209). */
export function popupOpen(status: UpdateStatus, asked: boolean, closedFor: string | null): boolean {
  const working = status.state === "downloading" || status.state === "ready"
  return asked || (closedFor !== (newest(status)?.version ?? null) && (status.popup || working))
}

/** For tests: the window as if it had never looked. */
export const forgetLooking = () => void (lookedAt = -Infinity)

/** The newest version you could update to, or nothing. */
export const newest = (status: UpdateStatus | undefined): UpdateVersion | undefined => status?.versions?.[0]

/** "Friday is up to date", "Friday 0.3.0 is out", or what's going on. */
export function headline(status: UpdateStatus): string {
  if (!status.checks) return "This Friday doesn't look for updates"
  if (status.state === "checking") return "Looking for a new version…"
  if (status.state === "downloading") return `Downloading Friday ${newest(status)?.version ?? ""}`.trim()
  if (status.state === "ready") return `Friday ${newest(status)?.version ?? ""} is ready to go in`
  const next = newest(status)
  return next ? `Friday ${next.version} is out` : "Friday is up to date"
}

/** When Friday last looked, as people say it: "just now", "5 minutes ago", "yesterday", "on 3 November". */
export function lookedAgo(at: string | null | undefined, now: Date): string {
  if (!at) return "Hasn't looked yet"
  const then = new Date(at)
  const minutes = Math.round((now.getTime() - then.getTime()) / 60_000)
  // later than now by more than a minute: the clocks disagree, so the time itself, never "just now" (19 Nov)
  if (minutes < -1) return `Looked at ${then.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" }).toLowerCase()}`
  if (minutes < 1) return "Looked just now"
  if (minutes < 60) return `Looked ${minutes} minute${minutes === 1 ? "" : "s"} ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `Looked ${hours} hour${hours === 1 ? "" : "s"} ago`
  const days = Math.round(hours / 24)
  if (days === 1) return "Looked yesterday"
  if (days < 7) return `Looked ${days} days ago`
  return `Looked on ${then.getDate()} ${then.toLocaleString("en", { month: "long" })}`
}

/** A download's progress and its seconds counting up, as every wait in Friday shows them (preferences, 3 Nov). */
export function progressLine(progress: number, seconds: number): string {
  return `${Math.round(progress * 100)}% · ${Math.floor(seconds)} s`
}

/** What to tell the Mac app once a new version is unpacked: swap now and reopen, or when you quit (H146). */
export function macMessage(status: UpdateStatus): { update: "install" | "atQuit"; app: string } | null {
  if (status.state !== "ready" || !status.staged) return null
  return { update: status.restart === "quit" ? "atQuit" : "install", app: status.staged }
}

type Bridge = { webkit?: { messageHandlers?: { friday?: { postMessage: (m: unknown) => void } } } }

/** In the Mac app, a ready update is handed over once: it restarts into it now, or swaps it in when you quit. */
export function useSwapWhenReady(status: UpdateStatus | undefined): void {
  const told = useRef<string | null>(null)
  useEffect(() => {
    const message = status && macMessage(status)
    if (!message || !inMacApp()) return
    const said = `${message.update} ${message.app}`
    if (told.current === said) return
    told.current = said
    ;(window as unknown as Bridge).webkit?.messageHandlers?.friday?.postMessage(message)
  }, [status])
}
