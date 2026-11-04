// Search (v22, ⌘K or ⌘F): to-dos, calendar events (any year, one per series, as personal's sidebar search),
// projects, pages and settings, and actions, filtered as you type; ↑↓ and Enter to open. With nothing matching,
// Enter adds what you typed as a to-do (COMBINED.md 57).

import { useAi } from "@/settings/AiConnect"
import { useQuery } from "@tanstack/react-query"
import { openMatches } from "./tasks"
import { useEffect, useMemo, useRef, useState } from "react"
import { useNavigate } from "react-router"
import { query } from "@/api/client"
import { Icon } from "@/components/fr/controls"
import { useAdd } from "@/components/todo/QuickAdd"
import { useHorizon, useProjects } from "@/hooks/queries"
import { useCommand } from "@/hooks/useCommand"
import { when } from "@/lib/format"
import { nextBlocks } from "@/lib/todo"
import { useLook } from "@/theme/LookProvider"
import { draftOf } from "@/shell/EventPane"
import { useShell } from "@/shell/ShellContext"
import { useBreaks } from "@/now/breaks"
import { useAllItems } from "@/todo/TodoPage"

interface Hit {
  key: string
  label: string
  meta?: string
  icon?: string
  swatch?: string
  run: () => void
}

const PAGES: [string, string, string][] = [
  ["Plan", "/", "calendar-dots"],
  ["To-do", "/todo", "check-square"],
  ["Projects & exams", "/projects", "tree-structure"],
  ["Inbox: what's waiting, how your day went", "/inbox", "tray"],
  ["Insights", "/insights", "chart-line"],
  ["Sleep & meals", "/body", "moon-stars"],
  ["Rules", "/rules", "sliders-horizontal"],
  ["Appearance", "/settings/appearance", "paint-brush"],
  ["Calendars and categories", "/settings/calendars", "calendar"],
  ["Tags and kinds", "/settings/tags", "tag"],
  ["Schedule", "/settings/schedule", "clock"],
  ["Repeating", "/settings/repeating", "repeat"],
  ["Integrations", "/settings/integrations", "plugs"],
  ["Shortcuts", "/settings/shortcuts", "keyboard"],
]

export function Search() {
  const { today, setDialog, setPop, setPlace, place, setEvent, setAgendaDay, askClaude, setTour } = useShell()
  const ai = useAi()
  const navigate = useNavigate()
  const { color } = useLook()
  const [q, setQ] = useState("")
  const [at, setAt] = useState(0)
  const ref = useRef<HTMLInputElement>(null)
  const items = useAllItems(false).data ?? [] // open tasks only (3 Nov)
  const projects = useProjects().data ?? []
  const next = nextBlocks(useHorizon().data?.blocks ?? [])
  const text = q.trim()
  const events = useQuery({ queryKey: ["events", text], queryFn: () => query("events", { text, limit: 8 }), enabled: text.length > 1 }).data ?? []
  const add = useAdd()
  const breaks = useBreaks()
  const goOver = useCommand("review_again", { label: (o) => o.result.message ?? "Ready" })
  useEffect(() => ref.current?.focus(), [])
  const close = () => setDialog(null)
  const go = (f: () => void) => () => (f(), close())
  const groups = useMemo(() => {
    const has = (text: string) => text.toLowerCase().includes(q.trim().toLowerCase())
    const todos: Hit[] = openMatches(items, q).map((i) => ({
        key: `i${i.id}`,
        label: i.title,
        swatch: color(i.area, i.preset),
        meta: next.get(i.id) ? when(next.get(i.id)!.start, today) : i.due ? `due ${when(i.due, today)}` : "",
        run: go(() => navigate(`/todo?item=${i.id}`)),
      }))
    const eventHits: Hit[] = text.length > 1
      ? events.map((e) => ({
          key: `e${e.id}`,
          label: e.title,
          icon: e.series_id != null ? "repeat" : "calendar-blank",
          meta: e.start ? when(e.start, today) : "",
          run: go(() => {
            const day = (e.start ?? today).slice(0, 10)
            setPlace({ view: place.view === "month" ? 1 : place.view, first: day })
            setAgendaDay(day)
            navigate("/")
            if (e.start && e.end) setEvent(draftOf(e))
          }),
        }))
      : []
    const projectHits: Hit[] = projects
      .filter((p) => has(p.item.title))
      .slice(0, 4)
      .map((p) => ({ key: `p${p.item.id}`, label: p.item.title, swatch: color(p.item.area, p.item.preset), meta: "project", run: go(() => navigate(`/projects?id=${p.item.id}`)) }))
    const pages: Hit[] = PAGES.filter(([label]) => has(label)).map(([label, to, icon]) => ({ key: to, label, icon, run: go(() => navigate(to)) }))
    const actions: Hit[] = [
      { key: "shove", label: "Shove: take time back", icon: "hand-palm", run: go(() => setPop("shove")) },
      { key: "pace", label: "Change pace", icon: "gauge", run: go(() => setPop("pace")) },
      { key: "brief", label: "Morning brief", icon: "sun-horizon", run: () => setDialog("brief") },
      { key: "triage", label: "What gives when it can't all fit", icon: "warning", run: () => setDialog("triage") },
      { key: "ways", label: "Other ways to plan the week", icon: "shuffle", run: () => setDialog("ways") },
      { key: "tour", label: "Take the tour of Friday", icon: "question", run: () => (setDialog(null), setTour(true)) },
      { key: "setup", label: "Set up Friday: your day, load, free time, calendars", icon: "sliders-horizontal", run: () => setDialog("setup") },
      ...(breaks.nap ? [{ key: "nap", label: "Taking a nap", icon: "bed", run: go(breaks.nap) }] : []),
      ...(breaks.snack ? [{ key: "snack", label: "Having a snack", icon: "cookie", run: go(breaks.snack) }] : []),
      // The tasks Friday brought in, a message each in the Inbox, to keep or take off your list (29 Oct)
      { key: "again", label: "Go over everything Friday brought in again", icon: "arrow-counter-clockwise", run: go(() => (goOver({}), navigate("/inbox"))) },
      { key: "ask", label: `Ask ${ai.name}${text ? `: ${text}` : ""}`, icon: "sparkle", run: () => askClaude(text) },
    ].filter((a) => has(a.label))
    return [
      ["To-dos", todos],
      ["Events", eventHits],
      ["Projects", projectHits],
      ["Go to", pages],
      ["Actions", actions],
    ].filter(([, hits]) => (hits as Hit[]).length) as [string, Hit[]][]
  }, [q, text, items, events, projects, next, today, color, place.view, breaks])
  const flat = groups.flatMap(([, hits]) => hits)
  const key = async (e: React.KeyboardEvent) => {
    if (e.key === "Escape") close()
    if (e.key === "ArrowDown") (e.preventDefault(), setAt(Math.min(flat.length - 1, at + 1)))
    if (e.key === "ArrowUp") (e.preventDefault(), setAt(Math.max(0, at - 1)))
    if (e.key === "Enter") {
      if (flat[at]) flat[at].run()
      else if (q.trim() && (await add({ text: q }))) close()
    }
  }
  return (
    <div className="fr-scrim" style={{ zIndex: 40, alignItems: "flex-start", padding: "90px 24px 24px", background: "color-mix(in srgb, #05070b 50%, transparent)" }}>
      <div onClick={close} style={{ position: "absolute", inset: 0 }} />
      <div role="dialog" aria-modal="true" aria-label="Search" className="fr-float" style={{ position: "relative", width: "min(620px, 100%)", maxHeight: "calc(100% - 40px)", display: "flex", flexDirection: "column", overflow: "hidden" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "14px 16px", boxShadow: "inset 0 -1px 0 color-mix(in srgb, var(--color-text) 7%, transparent)" }}>
          <Icon name="magnifying-glass" size={18} style={{ color: "var(--color-neutral-400)" }} />
          <input
            ref={ref}
            value={q}
            onChange={(e) => (setQ(e.target.value), setAt(0))}
            onKeyDown={key}
            placeholder="Search to-dos, events, projects, settings…"
            aria-label="Search"
            style={{ flex: 1, minWidth: 0, border: 0, outline: 0, background: "transparent", color: "var(--color-text)", font: "inherit", fontSize: 16 }}
          />
          <kbd className="fr-kbd">Esc</kbd>
        </div>
        <div style={{ overflowY: "auto", padding: "6px 8px 10px", display: "flex", flexDirection: "column" }}>
          {groups.map(([name, hits]) => (
            <div key={name} style={{ display: "flex", flexDirection: "column", paddingTop: 6 }}>
              <span style={{ fontSize: 11, color: "var(--color-neutral-500)", padding: "4px 8px" }}>{name}</span>
              {hits.map((h) => {
                const i = flat.indexOf(h)
                return (
                  <button
                    key={h.key}
                    onClick={h.run}
                    onMouseEnter={() => setAt(i)}
                    className="fr-plain"
                    style={{ display: "grid", gridTemplateColumns: "18px minmax(0,1fr) auto", gap: 10, alignItems: "center", padding: 8, borderRadius: "var(--radius-md)", background: i === at ? "color-mix(in srgb, var(--color-accent) 14%, transparent)" : undefined }}
                  >
                    <span style={{ display: "flex", justifyContent: "center" }}>
                      {h.swatch ? <span className="fr-swatch" style={{ background: h.swatch }} /> : <Icon name={h.icon ?? "circle"} size={15} style={{ color: "var(--color-neutral-400)" }} />}
                    </span>
                    <span style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{h.label}</span>
                    <span className="tnum" style={{ fontSize: 12, color: "var(--color-neutral-500)", whiteSpace: "nowrap" }}>
                      {h.meta}
                    </span>
                  </button>
                )
              })}
            </div>
          ))}
          {!flat.length && <div style={{ padding: "18px 10px", color: "var(--color-neutral-400)" }}>Nothing matches. Press Enter to add it as a to-do.</div>}
        </div>
        <div style={{ display: "flex", gap: 14, padding: "8px 16px", fontSize: 11, color: "var(--color-neutral-500)", boxShadow: "inset 0 1px 0 color-mix(in srgb, var(--color-text) 7%, transparent)" }}>
          <span>↑↓ to move</span>
          <span>Enter to open</span>
          <span>Esc to close</span>
        </div>
      </div>
    </div>
  )
}
