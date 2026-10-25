// Server state (DESIGN §18.2). Keys start with the query's name so server events can refresh them by name.

import { useQuery } from "@tanstack/react-query"
import { type Block, query } from "@/api/client"
import { GHOSTS } from "@/api/events"

export const useStatus = () => useQuery({ queryKey: ["status"], queryFn: () => query("status") })

// The clock moves what "now" means, so it is refetched every minute as well as on plan.changed.
export const useNow = () => useQuery({ queryKey: ["now"], queryFn: () => query("now"), refetchInterval: 60_000 })

export const useItems = () => useQuery({ queryKey: ["items"], queryFn: () => query("items", {}) })

export const useItem = (id: number | null) =>
  useQuery({ queryKey: ["item", id], queryFn: () => query("item", { id: id ?? 0 }), enabled: id !== null })

/** Blocks from now to the end of the planning horizon. */
export const useHorizon = () => useQuery({ queryKey: ["plan", "horizon"], queryFn: () => query("plan", {}) })

export const usePlan = (start: string, end: string) =>
  useQuery({ queryKey: ["plan", start, end], queryFn: () => query("plan", { start, end }) })

export const useCalendar = (start: string, days: number) =>
  useQuery({ queryKey: ["calendar", start, days], queryFn: () => query("calendar", { start, days }) })

export const useAreas = () => useQuery({ queryKey: ["areas"], queryFn: () => query("areas") })

export const usePaces = () => useQuery({ queryKey: ["paces"], queryFn: () => query("paces") })

export const useWhy = (key: string | null) =>
  useQuery({ queryKey: ["why", key], queryFn: () => query("why", { key: key ?? "" }), enabled: key !== null })

export const useGhosts = () =>
  useQuery<Block[]>({ queryKey: GHOSTS, queryFn: () => [], staleTime: Infinity, gcTime: Infinity })

export const useSettings = () => useQuery({ queryKey: ["settings"], queryFn: () => query("settings") })

export const useProjects = () => useQuery({ queryKey: ["projects"], queryFn: () => query("projects") })

export const useExams = () => useQuery({ queryKey: ["exams"], queryFn: () => query("exams") })

// Tracked sleep (Settings → Schedule): checked each minute, since what the Now bar offers ("I'm up", "Going to bed")
// changes with the clock.
export const useSleep = () => useQuery({ queryKey: ["sleep"], queryFn: () => query("sleep"), refetchInterval: 60_000 })

export const useLoad = (weeks: number) =>
  useQuery({ queryKey: ["load", weeks], queryFn: () => query("load", { weeks }), retry: false })
