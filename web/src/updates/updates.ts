// Friday's own updater on the page (HOSTED.md H118–H124, H144–H147): the server looks and downloads
// (commands/updates.py); the page asks you, shows what's new, and tells the Mac app to swap the new version in
// (Mac/Sources/Updater.swift), right away or when you quit, as Settings → Updates says.

import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useCallback, useEffect, useRef } from "react"
import { command, query, type Schemas } from "@/api/client"
import { inMacApp } from "@/dialogs/Setup"

export type UpdateStatus = Schemas["UpdateStatusOut"]
export type UpdateVersion = Schemas["UpdateVersionOut"]
type Act = "update_check" | "update_later" | "update_start" | "update_stop" | "whats_new_seen"

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

/** Run one of the updater's commands; its answer is the new state, shown at once. */
export function useUpdateAct() {
  const client = useQueryClient()
  return useCallback(
    async (name: Act) => {
      const out = await command(name, {})
      client.setQueryData(KEY, out.result)
      return out.result
    },
    [client],
  )
}

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
