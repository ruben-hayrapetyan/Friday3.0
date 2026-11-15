// What the Projects & exams page repeats: a progress bar in a course's color, a status tag, a section heading, the
// tag of a project or an exam.

import type { QueryClient } from "@tanstack/react-query"
import { type ReactNode, useRef } from "react"
import type { Schemas } from "@/api/client"
import { H, Menu } from "@/components/fr/controls"
import { useCommand } from "@/hooks/useCommand"
import { useAreas } from "@/hooks/queries"
import type { Exam, Tone } from "./exams"

export type Project = Schemas["ProjectOut"]

export const PROJECT_STATUS: Record<Project["status"], [string, Tone]> = {
  on_track: ["On track", "good"],
  late: ["Behind", "due"],
  unplanned: ["Not planned yet", "warn"],
  done: ["Done", "quiet"],
}

export const EXAM_STATUS: Record<Schemas["ExamOut"]["status"], [string, Tone]> = {
  ready: ["Ready", "good"],
  on_track: ["On track", "good"],
  late: ["Behind", "due"],
  unplanned: ["Not all planned", "warn"],
  no_prep: ["No prep yet", "quiet"],
}

export const TONE: Record<Tone, string> = {
  good: "var(--color-accent-300)",
  warn: "var(--fr-warn)",
  due: "var(--fr-due)",
  quiet: "var(--color-neutral-400)",
}

export const RULE = "color-mix(in srgb, var(--color-text) 7%, transparent)"

export const projectPct = (p: Project) => (p.done_min + p.remaining_min ? Math.round((p.done_min / (p.done_min + p.remaining_min)) * 100) : 0)

/** A status in a small tag: accent when all is well, amber when something isn't planned, red when it's behind. */
export function StatusTag({ label, tone }: { label: string; tone: Tone }) {
  const cls = tone === "good" ? "fr-tag accent" : tone === "warn" ? "fr-tag warn" : tone === "due" ? "fr-tag due" : "fr-tag"
  return (
    <span className={cls} style={{ flex: "none", whiteSpace: "nowrap", ...(tone === "quiet" ? { background: "color-mix(in srgb, var(--color-text) 6%, transparent)", color: "var(--color-neutral-400)" } : {}) }}>
      {label}
    </span>
  )
}

/** How much is done, as a bar in the course's color. */
export function Bar({ pct, color, height = 6 }: { pct: number; color: string; height?: number }) {
  return (
    <div role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} style={{ height, borderRadius: height / 2, background: "color-mix(in srgb, var(--color-text) 8%, transparent)", overflow: "hidden" }}>
      <div style={{ height: "100%", width: `${Math.max(0, Math.min(100, pct))}%`, borderRadius: height / 2, background: color, transition: "width 300ms ease" }} />
    </div>
  )
}

/** A section of the overview: its title, a quiet note, something on the right, then the content. */
export function Section({ title, note, right, children }: { title: string; note?: ReactNode; right?: ReactNode; children: ReactNode }) {
  return (
    <section style={{ display: "flex", flexDirection: "column", gap: 14, minWidth: 0 }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: "4px 12px", flexWrap: "wrap" }}>
        <H size={22}>{title}</H>
        {note && <span className="fr-kicker">{note}</span>}
        <span style={{ flex: 1 }} />
        {right}
      </div>
      {children}
    </section>
  )
}

/** A card on the overview: paper raised off the page (a shade lighter in the dark), with the course's color down
 * its left edge. */
export const card = (color: string, light: boolean) =>
  ({
    position: "relative",
    display: "flex",
    flexDirection: "column",
    gap: 14,
    minWidth: 0,
    padding: "16px 18px 16px 22px",
    borderRadius: "var(--radius-lg)",
    background: light ? "var(--color-surface)" : "color-mix(in srgb, var(--color-text) 3%, var(--color-surface))",
    boxShadow: `0 0 0 1px ${RULE}, var(--shadow-sm), inset 4px 0 0 ${color}`,
    overflow: "hidden",
  }) as const

/** A project's or an exam's tag (15 Nov, a client: neither page could change it). The server's `edit` gives its steps
 * (an exam's prep) that had the old tag or none the new one, in the same change, so one Undo puts them all back; the
 * page shows it so at once, and as it was if Friday refuses (useCommand puts projects and exams back). */
export function useTag(id: number, title: string): (tag: string | null) => void {
  const said = useRef<string | null>(null)
  const edit = useCommand("edit", { label: () => (said.current ? `${title}: tagged ${said.current}` : `${title}: no tag`), optimistic: (client, input) => input.area !== undefined && retagged(client, id, input.area ?? null) })
  return (tag) => {
    said.current = tag
    edit({ id, area: tag })
  }
}

/** The projects and exams as they'll be once `id` has `area`: it, and its steps or prep that had its tag or none. */
export function retagged(client: QueryClient, id: number, area: string | null): void {
  const follows = (step: { area?: string | null }, was: string | null | undefined) => step.area == null || step.area === was
  client.setQueryData<Project[]>(["projects"], (list) =>
    list?.map((p) => (p.item.id !== id ? p : { ...p, item: { ...p.item, area }, children: p.children.map((c) => (c.parent_id === id && follows(c, p.item.area) ? { ...c, area } : c)) })),
  )
  client.setQueryData<Exam[]>(["exams"], (list) =>
    list?.map((e) => (e.item.id !== id ? e : { ...e, item: { ...e.item, area }, prep: e.prep.map((p) => (follows(p.item, e.item.area) ? { ...p, item: { ...p.item, area } } : p)) })),
  )
}

/** The tag menu, as a repeat's in Settings → Repeating: No tag, then your tags. */
export function TagMenu({ title, value, onPick }: { title: string; value: string | null; onPick: (tag: string | null) => void }) {
  const tags = (useAreas().data ?? []).filter((a) => !a.archived).map((a) => a.name)
  const options = [{ value: "", label: "No tag" }, ...[...new Set([...tags, ...(value ? [value] : [])])].map((t) => ({ value: t, label: t }))]
  return <Menu label={`Tag for ${title}`} value={value ?? ""} onPick={(tag) => onPick(tag || null)} options={options} />
}
