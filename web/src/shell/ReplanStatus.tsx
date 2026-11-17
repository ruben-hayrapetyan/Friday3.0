// "Replanning…" while a change is planned, then "Plan updated" for a moment, on every page but Plan and To-do (they
// say it in their own headers), over a popup too: a pace, a rule or a setting changed shows that it's acted on.

import { useEffect, useRef, useState } from "react"
import { createPortal } from "react-dom"
import { useLocation } from "react-router"
import { useQuery } from "@tanstack/react-query"
import { query } from "@/api/client"
import { replanning, useWantedPlan } from "@/lib/replan"

export const DONE_MS = 2500

export function ReplanStatus() {
  const want = useWantedPlan()
  // status asked again each second while a plan is coming: nothing else says when it lands on a page without the plan
  const [watching, setWatching] = useState(false)
  const status = useQuery({ queryKey: ["status"], queryFn: () => query("status"), refetchInterval: watching ? 1000 : false }).data
  const busy = replanning(status, want)
  useEffect(() => setWatching(busy), [busy])
  const [done, setDone] = useState(false)
  const was = useRef(false)
  const [spot, setSpot] = useState<HTMLElement | null>(null)
  useEffect(() => setSpot(document.getElementById("fr-toast-head")), [])
  useEffect(() => {
    if (busy) return void ((was.current = true), setDone(false))
    if (!was.current) return
    was.current = false
    setDone(true)
    const t = setTimeout(() => setDone(false), DONE_MS)
    return () => clearTimeout(t)
  }, [busy])
  const { pathname } = useLocation()
  if (pathname === "/" || pathname === "/todo" || !spot || (!busy && !done)) return null
  return createPortal(
    <span
      data-replan
      className="fr-pill"
      style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12, padding: "6px 12px", background: "var(--color-neutral-900)", color: busy ? "var(--color-accent-200)" : "var(--color-neutral-300)", boxShadow: "var(--shadow-md)" }}
    >
      <span style={{ width: 6, height: 6, borderRadius: "50%", background: busy ? "var(--color-accent)" : "var(--color-neutral-400)" }} />
      {busy ? "Replanning…" : "Plan updated"}
    </span>,
    spot,
  )
}
