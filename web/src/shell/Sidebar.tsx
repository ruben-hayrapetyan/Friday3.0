// The sidebar (v22): the Friday mark, Settings and the tour, the pages, personal's mini month and day agenda
// (COMBINED.md 10). No to-do list (3 Nov: "just remove it in its entirety"): the To-do drawer shows what's due. A
// block dropped here goes back to Friday ("let Friday decide"). In a narrower window it is a rail of the pages' icons;
// in a narrow one it slides over the page from the menu button.
import { useQuery } from "@tanstack/react-query"
import { NavLink, useNavigate } from "react-router"
import { query } from "@/api/client"
import { useDragging } from "@/components/calendar/useDrag"
import { Icon } from "@/components/fr/controls"
import { useStatus } from "@/hooks/queries"
import { DayAgenda } from "./DayAgenda"
import { MiniMonth } from "./MiniMonth"
import { useShell } from "./ShellContext"
import { DecisionCount } from "@/inbox/Decisions"
import { useInboxCount } from "@/inbox/queries"

// No Review (29 Oct: "I don't want a review section anymore"): it's messages in the Inbox, and the Inbox shows one
// count of everything waiting there.
const PAGES = [
  { to: "/", icon: "calendar-dots", label: "Plan" },
  { to: "/todo", icon: "check-square", label: "To-do" },
  { to: "/projects", icon: "tree-structure", label: "Projects & exams" },
  { to: "/inbox", icon: "tray", label: "Inbox" },
  { to: "/insights", icon: "chart-line", label: "Insights" },
  { to: "/rules", icon: "sliders-horizontal", label: "Rules" },
] as const

export function Sidebar({ rail = false, onClose }: { rail?: boolean; onClose?: () => void }) {
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
function Rail() {
  const navigate = useNavigate()
  const { setTour } = useShell()
  const waiting = useInboxCount()
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
          {p.label === "Inbox" && !!waiting && <DecisionCount n={waiting} style={{ position: "absolute", top: 2, right: 1 }} />}
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
  const waiting = useInboxCount()
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
              {p.label === "Insights" && asking && <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--color-accent)" }} />}
              {p.label === "Inbox" && !!waiting && <DecisionCount n={waiting} />}
            </>
          )}
        </NavLink>
      ))}
    </nav>
  )
}
