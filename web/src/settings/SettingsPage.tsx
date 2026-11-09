// Settings (v22): appearance, tags and kinds, schedule, repeating, integrations, about you and shortcuts, with
// Advanced for the rest (learning, plugins, saved paces and any key). Changes apply right away; keys friday.toml
// sets are read-only here and say so.

import { useShell } from "@/shell/ShellContext"
import { type ReactNode, useEffect, useState } from "react"
import { Navigate, NavLink, useNavigate, useParams } from "react-router"
import { H, Icon } from "@/components/fr/controls"
import { useStatus } from "@/hooks/queries"
import { AboutYou } from "./AboutYou"
import { AdvancedSection } from "./Advanced"
import { Appearance } from "./Appearance"
import { CalendarsSection } from "./CalendarsSection"
import { Tokens } from "./Assistants"
import { Integrations } from "./Integrations"
import { Phone } from "./Phone"
import { Repeating } from "./Repeating"
import { Schedule } from "./Schedule"
import { Shortcuts } from "./Shortcuts"
import { TagsKinds } from "./TagsKinds"
import { UpdatesSection } from "./UpdatesSection"

const SECTIONS = [
  { id: "appearance", label: "Appearance", icon: "paint-brush", page: Appearance },
  { id: "calendars", label: "Calendars", icon: "calendar", page: CalendarsSection },
  { id: "tags", label: "Tags/Kinds", icon: "tag", page: TagsKinds },
  { id: "schedule", label: "Schedule", icon: "clock", page: Schedule },
  { id: "repeating", label: "Repeating", icon: "repeat", page: Repeating },
  { id: "integrations", label: "Integrations", icon: "plugs", page: Integrations },
  { id: "phone", label: "Phone", icon: "device-mobile", page: Phone },
  { id: "tokens", label: "Tokens", icon: "key", page: Tokens },
  { id: "about", label: "About you", icon: "user", page: AboutYou },
  { id: "shortcuts", label: "Shortcuts", icon: "keyboard", page: Shortcuts },
  { id: "updates", label: "Updates", icon: "arrow-circle-up", page: UpdatesSection },
  { id: "advanced", label: "Advanced", icon: "brackets-curly", page: AdvancedSection },
]

const LAST = "friday.settings.section"
const FIRST = "integrations" // the first visit is to connect calendars and mail

function remembered(): string {
  try {
    const last = localStorage.getItem(LAST)
    return SECTIONS.some((s) => s.id === last) ? (last as string) : FIRST
  } catch {
    return FIRST // storage blocked
  }
}

export function SettingsPage() {
  const { section } = useParams()
  const { layout, setDialog } = useShell()
  const tight = layout.tight // a narrow window: the sections in a row above, scrolled sideways
  const navigate = useNavigate()
  const owned = useStatus().data?.config_keys ?? []
  const known = SECTIONS.find((s) => s.id === section)
  useEffect(() => {
    try {
      if (known) localStorage.setItem(LAST, known.id)
    } catch {
      // storage blocked: settings just open at the first section next time
    }
  }, [known])
  if (!known) return <Navigate to={`/settings/${remembered()}`} replace />
  const Page = known.page
  return (
    <>
      <div className="fr-page-head">
        <span className="fr-h fr-title">Settings</span>
        <span className="fr-head-note" style={{ color: "var(--color-neutral-500)" }}>Changes apply right away</span>
        <div style={{ flex: 1 }} />
        <SetupAnswers onAll={() => setDialog("setup")} />
        <button className="btn btn-secondary" onClick={() => navigate("/")}>
          <Icon name="arrow-left" size={15} />
          <span className="fr-head-note">Back to plan</span>
        </button>
      </div>
      <div className="fr-panel" style={{ display: "grid", ...(tight ? { gridTemplateRows: "auto minmax(0,1fr)" } : { gridTemplateColumns: "208px minmax(0,1fr)" }), overflow: "hidden" }}>
        <nav
          data-tour="settings-nav"
          style={
            tight
              ? { padding: "10px 12px", display: "flex", gap: 4, overflowX: "auto", boxShadow: "inset 0 -1px 0 color-mix(in srgb, var(--color-text) 8%, transparent)" }
              : { padding: "14px 10px", display: "flex", flexDirection: "column", gap: 1, boxShadow: "inset -1px 0 0 color-mix(in srgb, var(--color-text) 8%, transparent)" }
          }
        >
          {SECTIONS.map((s) => (
            <NavLink
              key={s.id}
              to={`/settings/${s.id}`}
              className="fr-hover"
              style={({ isActive }) => ({
                display: "flex",
                gap: 10,
                alignItems: "center",
                padding: "8px 10px",
                borderRadius: "var(--radius-md)",
                background: isActive ? "color-mix(in srgb, var(--color-accent) 14%, transparent)" : undefined,
                color: isActive ? "var(--color-text)" : "var(--color-neutral-300)",
                textDecoration: "none",
                whiteSpace: "nowrap",
                flex: "none",
              })}
            >
              {({ isActive }) => (
                <>
                  <Icon name={s.icon} size={16} style={{ color: isActive ? "var(--color-accent-300)" : undefined }} />
                  {s.label}
                </>
              )}
            </NavLink>
          ))}
        </nav>
        <div className="fr-gutter" style={{ overflowY: "auto", minHeight: 0, padding: "30px 40px 80px" }}>
          <div style={{ maxWidth: 780, display: "flex", flexDirection: "column" }}>
            {owned.length > 0 && (
              <div style={{ display: "flex", gap: 10, alignItems: "center", padding: "10px 12px", marginBottom: 18, borderRadius: "var(--radius-md)", background: "var(--color-bg)", fontSize: 12, color: "var(--color-neutral-300)" }}>
                <Icon name="file-text" size={15} style={{ color: "var(--color-accent-300)" }} />
                Set in friday.toml, so read-only here: {owned.join(", ")}.
              </div>
            )}
            <Page />
          </div>
        </div>
      </div>
    </>
  )
}

export function SectionHead({ title, note, right }: { title: string; note: string; right?: ReactNode }) {
  return (
    <div style={{ display: "flex", alignItems: "flex-end", gap: 16, paddingBottom: 14 }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 4, flex: 1 }}>
        <H size={30}>{title}</H>
        <span style={{ color: "var(--color-neutral-400)" }}>{note}</span>
      </div>
      {right}
    </div>
  )
}

/** One setting: its name and a line on what it does, then the control. */
export function Field({ name, note, children }: { name: string; note?: string; children: ReactNode }) {
  return (
    <div className="fr-stack" style={{ display: "grid", gridTemplateColumns: "220px minmax(0,1fr)", gap: 28, padding: "18px 0", boxShadow: "inset 0 1px 0 color-mix(in srgb, var(--color-text) 8%, transparent)" }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
        <span style={{ fontWeight: 500 }}>{name}</span>
        {note && <span style={{ fontSize: 12, color: "var(--color-neutral-500)", textWrap: "pretty" }}>{note}</span>}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 10, minWidth: 0 }}>{children}</div>
    </div>
  )
}

// Setup's questions, each one to change on its own (8 Nov: redoing the whole setup to change one answer "is a lot of
// effort").
const ANSWERS: [string, string][] = [
  ["wake", "When you get up"],
  ["bed", "When you go to bed"],
  ["work", "Work in a normal day"],
  ["heavy", "Work on a heavy day"],
  ["focus", "Longest stretch of work"],
  ["deadline", "How early work is done"],
  ["evening", "Free evenings"],
  ["weekend", "Free weekends"],
  ["brief", "The morning brief"],
  ["ai", "The AI Friday reads with"],
  ["bring", "Calendars, links and syllabi"],
]

/** Setup's questions again: all of them, or one, changed alone and saved. */
function SetupAnswers({ onAll }: { onAll: () => void }) {
  const { openSetup } = useShell()
  const [open, setOpen] = useState(false)
  return (
    <span style={{ position: "relative" }}>
      <button className="btn btn-ghost" onClick={() => setOpen(!open)} aria-expanded={open} title="Your day, load, free time and calendars">
        <Icon name="sliders-horizontal" size={15} />
        <span className="fr-head-note">Change a Setup answer</span>
        <Icon name="caret-down" size={12} />
      </button>
      {open && (
        <>
          <div onClick={() => setOpen(false)} style={{ position: "fixed", inset: 0, zIndex: 20 }} />
          <div role="menu" style={{ position: "absolute", right: 0, top: "calc(100% + 6px)", zIndex: 21, display: "flex", flexDirection: "column", minWidth: 240, padding: 6, borderRadius: "var(--radius-md)", background: "var(--color-surface)", boxShadow: "var(--shadow-lg, 0 8px 24px rgb(0 0 0 / 18%))" }}>
            {ANSWERS.map(([step, label]) => (
              <button key={step} role="menuitem" className="fr-plain fr-hover" onClick={() => (setOpen(false), openSetup(step))} style={{ textAlign: "left", padding: "7px 10px", borderRadius: "var(--radius-sm)" }}>
                {label}
              </button>
            ))}
            <div style={{ height: 1, margin: "4px 6px", background: "color-mix(in srgb, var(--color-text) 8%, transparent)" }} />
            <button role="menuitem" className="fr-plain fr-hover" onClick={() => (setOpen(false), onAll())} style={{ textAlign: "left", padding: "7px 10px", borderRadius: "var(--radius-sm)", color: "var(--color-neutral-300)" }}>
              All of Setup’s questions, in order
            </button>
          </div>
        </>
      )}
    </span>
  )
}
