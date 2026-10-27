// The sidebar (v22): the Friday mark, Settings and the tour, the pages, personal's mini month and day agenda
// (COMBINED.md 10), and what's next on the to-do list, folded until you open it. Rows drag onto the calendar; a block
// dropped here goes back to Friday ("let Friday decide"). In a narrower window it is a rail of the pages' icons; in a
// narrow one it slides over the page from the menu button.

import { useQuery } from "@tanstack/react-query"
import { useState } from "react"
import { NavLink, useNavigate } from "react-router"
import { type Block, type Item, query } from "@/api/client"
import { useDragging } from "@/components/calendar/useDrag"
import { Icon } from "@/components/fr/controls"
import { useHorizon, useItems, useNow, useStatus } from "@/hooks/queries"
import { dur, when } from "@/lib/format"
import { nextBlocks, sections } from "@/lib/todo"
import { useLook } from "@/theme/LookProvider"
import { DayAgenda } from "./DayAgenda"
import { MiniMonth } from "./MiniMonth"
import { useShell } from "./ShellContext"
import { DecisionCount, useDecisions } from "@/inbox/Decisions"
import { useReviewWaiting } from "@/review/DailyReview"

const PAGES = [
  { to: "/", icon: "calendar-dots", label: "Plan" },
  { to: "/todo", icon: "check-square", label: "To-do" },
  { to: "/projects", icon: "tree-structure", label: "Projects & exams" },
  { to: "/review", icon: "cards", label: "Review" },
  { to: "/inbox", icon: "tray", label: "Inbox" },
  { to: "/insights", icon: "chart-line", label: "Insights" },
  { to: "/body", icon: "moon-stars", label: "Sleep & meals" },
  { to: "/rules", icon: "sliders-horizontal", label: "Rules" },
] as const

export function Sidebar({ showTodos, rail = false, onClose }: { showTodos: boolean; rail?: boolean; onClose?: () => void }) {
  const navigate = useNavigate()
  const { drag } = useDragging()
  const { setTour } = useShell()
  const dropping = !!drag?.moved && drag.kind !== "row" && drag.itemId !== null
  if (rail) return <Rail />
  return (
    <aside
      data-drop="todo"
      style={{
        position: "relative",
        display: "flex",
        flexDirection: "column",
        gap: 18,
        padding: "16px 12px 120px",
        overflowY: "auto",
        minHeight: 0,
        background: "color-mix(in srgb, var(--color-bg) 70%, transparent)",
        flex: onClose ? 1 : undefined,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 2, padding: "0 6px" }}>
        <Mark />
        <span style={{ flex: 1 }} />
        <button className="btn btn-icon btn-ghost" data-tour="help" onClick={() => setTour(true)} aria-label="Take the tour" title="Take the tour" style={{ width: 28, height: 28 }}>
          <Icon name="question" size={16} />
        </button>
        <button className="btn btn-icon btn-ghost" data-tour="settings" onClick={() => navigate("/settings")} aria-label="Settings" title="Settings" style={{ width: 28, height: 28 }}>
          <Icon name="gear-six" size={16} />
        </button>
        {onClose && (
          <button className="btn btn-icon btn-ghost" onClick={onClose} aria-label="Close" style={{ width: 28, height: 28 }}>
            <Icon name="x" size={16} />
          </button>
        )}
      </div>
      <Pages />
      <MiniMonth />
      <DayAgenda />
      {showTodos && (
        <Folded name="Up next" storage="friday-upnext-open">
          <Upcoming />
        </Folded>
      )}
      {dropping && (
        <div
          style={{
            position: "absolute",
            inset: 0,
            zIndex: 21,
            pointerEvents: "none",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            background: "color-mix(in srgb, var(--color-accent) 12%, transparent)",
            boxShadow: "inset 0 0 0 2px var(--color-accent)",
          }}
        >
          <span className="fr-float" style={{ padding: "8px 12px", borderRadius: "var(--radius-md)" }}>
            Drop to let Friday decide
          </span>
        </div>
      )}
    </aside>
  )
}

/** How far round the ring is: 0 as Saturday begins, all the way on Friday (as the Mac app's icon). */
function weekSweep(now = new Date()): number {
  const sinceSat = ((now.getDay() + 1) % 7) + (now.getHours() * 60 + now.getMinutes()) / 1440
  return Math.min(1, sinceSat / 6)
}

function Mark() {
  return (
    <div className="fr-h" style={{ display: "flex", alignItems: "center", gap: 8, fontFamily: "var(--fr-head)", fontWeight: 600, fontSize: 20, letterSpacing: "-0.005em", lineHeight: 1 }}>
      <Ring />
      Friday
    </div>
  )
}

function Ring() {
  return (
      <span
        style={{
          width: 12,
          height: 12,
          borderRadius: "50%",
          // The Dock icon's ring, closed as far as the week has come round to Friday.
          background: `conic-gradient(var(--color-accent) ${weekSweep()}turn, color-mix(in srgb, var(--color-text) 12%, transparent) 0)`,
          WebkitMask: "radial-gradient(circle, transparent 3.4px, #000 3.6px)",
          mask: "radial-gradient(circle, transparent 3.4px, #000 3.6px)",
          boxShadow: "0 0 calc(10px * var(--g-logo)) calc(1px * var(--g-logo)) var(--color-accent)",
        }}
      />
  )
}

/** A section of the sidebar that opens and closes, remembered on this device. */
function Folded({ name, storage, children }: { name: string; storage: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(() => {
    try {
      return localStorage.getItem(storage) === "1"
    } catch {
      return false
    }
  })
  const toggle = () => {
    setOpen(!open)
    try {
      localStorage.setItem(storage, open ? "0" : "1")
    } catch {
      // private mode: it stays this way for the visit
    }
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <button className="fr-plain fr-hover-text" onClick={toggle} aria-expanded={open} style={{ display: "flex", alignItems: "center", gap: 6, padding: "0 8px", fontSize: 12, color: "var(--color-neutral-500)", textTransform: "uppercase", letterSpacing: "0.06em" }}>
        <Icon name={open ? "caret-down" : "caret-right"} size={11} />
        {name}
      </button>
      {open && children}
    </div>
  )
}

/** The sidebar as a rail: the pages' icons, with their names on hover, and Settings and the tour below. */
function Rail() {
  const navigate = useNavigate()
  const { setTour } = useShell()
  const status = useStatus().data
  const deciding = useDecisions().length
  return (
    <aside data-tour="nav" style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 4, padding: "18px 0 16px", minHeight: 0, overflowY: "auto", background: "color-mix(in srgb, var(--color-bg) 70%, transparent)" }}>
      <span style={{ marginBottom: 14 }}>
        <Ring />
      </span>
      {PAGES.map((p) => (
        <NavLink
          key={p.to}
          to={p.to}
          end={p.to === "/"}
          title={p.label}
          aria-label={p.label}
          className="fr-hover"
          style={({ isActive }) => ({
            position: "relative",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            width: 40,
            height: 36,
            borderRadius: "var(--radius-md)",
            background: isActive ? "color-mix(in srgb, var(--color-accent) 14%, transparent)" : undefined,
            color: isActive ? "var(--color-accent-300)" : "var(--color-neutral-400)",
          })}
        >
          <Icon name={p.icon} size={18} />
          {p.label === "Inbox" && !!deciding && <DecisionCount n={deciding} style={{ position: "absolute", top: 2, right: 1 }} />}
          {p.label === "Inbox" && !deciding && !!status?.suggestions && (
            <span style={{ position: "absolute", top: 6, right: 7, width: 6, height: 6, borderRadius: "50%", background: "var(--color-accent)" }} />
          )}
        </NavLink>
      ))}
      <span style={{ flex: 1 }} />
      <button className="btn btn-icon btn-ghost" data-tour="help" onClick={() => setTour(true)} aria-label="Take the tour" title="Take the tour" style={{ width: 36, height: 36 }}>
        <Icon name="question" size={18} />
      </button>
      <button className="btn btn-icon btn-ghost" data-tour="settings" onClick={() => navigate("/settings")} aria-label="Settings" title="Settings" style={{ width: 36, height: 36 }}>
        <Icon name="gear-six" size={18} />
      </button>
    </aside>
  )
}

function Pages() {
  const status = useStatus().data
  const questions = useQuery({ queryKey: ["questions"], queryFn: () => query("questions") }).data
  const asking = !!questions && (questions.comparisons.length > 0 || !!questions.proposal || !!questions.wall)
  const reviewing = useReviewWaiting() > 0
  const deciding = useDecisions().length
  return (
    <nav data-tour="nav" style={{ display: "flex", flexDirection: "column", gap: 1 }}>
      {status?.demo && (
        <span className="fr-well" title="fridayd demo: a made-up student's term with stand-in Google, Gmail and AI" style={{ display: "flex", flexDirection: "column", gap: 2, padding: "8px 10px", marginBottom: 8, fontSize: 12 }}>
          <span style={{ fontWeight: 600, color: "var(--fr-warn)" }}>Demo</span>
          <span style={{ color: "var(--color-neutral-400)" }}>Made-up sample data, not your calendars or mail.</span>
        </span>
      )}
      {PAGES.map((p) => (
        <NavLink
          key={p.to}
          to={p.to}
          end={p.to === "/"}
          style={({ isActive }) => ({
            display: "flex",
            gap: 10,
            alignItems: "center",
            padding: "7px 8px",
            borderRadius: "var(--radius-md)",
            background: isActive ? "color-mix(in srgb, var(--color-accent) 14%, transparent)" : undefined,
            color: isActive ? "var(--color-text)" : "var(--color-neutral-300)",
            textDecoration: "none",
          })}
          className="fr-hover"
        >
          {({ isActive }) => (
            <>
              <Icon name={p.icon} size={16} style={{ color: isActive ? "var(--color-accent-300)" : "var(--color-neutral-400)" }} />
              <span style={{ flex: 1 }}>{p.label}</span>
              {((p.label === "Review" && reviewing) || (p.label === "Insights" && asking)) && (
                <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--color-accent)" }} />
              )}
              {p.label === "Inbox" && !!deciding && <DecisionCount n={deciding} />}
              {p.label === "Inbox" && !!status?.suggestions && (
                <span className="tnum" style={{ fontSize: 11, color: "var(--color-accent-300)" }}>
                  {status.suggestions}
                </span>
              )}
            </>
          )}
        </NavLink>
      ))}
    </nav>
  )
}

const SHOWN = ["Today", "This week", "Ongoing"] as const

/** The next things on the to-do list, in the order they'll happen. */
function Upcoming() {
  const { today, select } = useShell()
  const navigate = useNavigate()
  const items = useItems().data
  const blocks = useHorizon().data?.blocks ?? []
  const now = useNow().data
  if (!items) return <Skeleton />
  const open = items.filter((i) => i.status === "todo")
  if (!open.length) {
    return <div style={{ padding: "6px 8px", fontSize: 12, color: "var(--color-neutral-500)" }}>Your to-dos show up here once you add them.</div>
  }
  const bySection = sections(open, blocks, today)
  const next = nextBlocks(blocks)
  const startBy = new Map((now?.alerts ?? []).map((a) => [a.item_id, a.latest_start]))
  return (
    <>
      {SHOWN.filter((s) => bySection[s].length).map((s) => (
        <div key={s} style={{ display: "flex", flexDirection: "column", gap: 1 }}>
          <div style={{ fontSize: 12, color: "var(--color-neutral-500)", padding: "0 8px 4px" }}>{s}</div>
          {bySection[s].map(({ item }) => (
            <Row
              key={item.id}
              item={item}
              next={next.get(item.id)}
              isNow={now?.current?.item_id === item.id}
              startBy={startBy.get(item.id)}
              onOpen={() => {
                const block = next.get(item.id)
                if (block) select(block)
                else navigate(`/todo?item=${item.id}`)
              }}
            />
          ))}
        </div>
      ))}
    </>
  )
}

function Row(props: { item: Item; next?: Block; isNow: boolean; startBy?: string; onOpen: () => void }) {
  const { item, next, isNow, startBy, onOpen } = props
  const { today } = useShell()
  const { color } = useLook()
  const { begin } = useDragging()
  const length = item.remaining_min ?? item.duration_min ?? 60
  const sub = isNow ? "Now" : next ? when(next.start, today) : "not planned"
  return (
    <button
      className="fr-plain fr-hover"
      onClick={onOpen}
      onPointerDown={(e) => begin(e, { kind: "row", start: 0, end: length, grab: 0, itemId: item.id, blockKey: null, title: item.title })}
      title={`${item.title}${item.remaining_min ? `, ${dur(item.remaining_min)} left` : ""}`}
      style={{ display: "grid", gridTemplateColumns: "3px minmax(0,1fr)", gap: 10, padding: "6px 8px", borderRadius: "var(--radius-md)", touchAction: "none" }}
    >
      <span style={{ borderRadius: 2, background: color(item.area, item.preset) }} />
      <span style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
        <span style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{item.title}</span>
        <span className="tnum" style={{ fontSize: 12, color: "var(--color-neutral-500)" }}>
          {sub}
          {startBy && (
            <>
              , <span style={{ color: "var(--fr-warn)" }}>start by {when(startBy, today)}</span>
            </>
          )}
        </span>
      </span>
    </button>
  )
}

function Skeleton() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10, padding: "0 8px" }}>
      {["70%", "55%", "80%", "45%"].map((w) => (
        <div key={w} style={{ display: "flex", flexDirection: "column", gap: 5 }}>
          <span style={{ height: 10, width: w, borderRadius: 4, background: "color-mix(in srgb, var(--color-text) 8%, transparent)" }} />
          <span style={{ height: 8, width: "40%", borderRadius: 4, background: "color-mix(in srgb, var(--color-text) 5%, transparent)" }} />
        </div>
      ))}
    </div>
  )
}
