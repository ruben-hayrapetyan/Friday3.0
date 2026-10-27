// Settings (v22): appearance, tags and kinds, schedule, repeating, integrations, about you and shortcuts, with
// Advanced for the rest (learning, plugins, saved paces and any key). Changes apply right away; keys friday.toml
// sets are read-only here and say so.

import { useShell } from "@/shell/ShellContext"
import { type ReactNode, useEffect } from "react"
import { Navigate, NavLink, useNavigate, useParams } from "react-router"
import { H, Icon } from "@/components/fr/controls"
import { useStatus } from "@/hooks/queries"
import { AboutYou } from "./AboutYou"
import { AdvancedSection } from "./Advanced"
import { Appearance } from "./Appearance"
import { CalendarsSection } from "./CalendarsSection"
import { Tokens } from "./Assistants"
import { Integrations } from "./Integrations"
import { Repeating } from "./Repeating"
import { Schedule } from "./Schedule"
import { Shortcuts } from "./Shortcuts"
import { TagsKinds } from "./TagsKinds"

const SECTIONS = [
  { id: "appearance", label: "Appearance", icon: "paint-brush", page: Appearance },
  { id: "calendars", label: "Calendars", icon: "calendar", page: CalendarsSection },
  { id: "tags", label: "Tags/Kinds", icon: "tag", page: TagsKinds },
  { id: "schedule", label: "Schedule", icon: "clock", page: Schedule },
  { id: "repeating", label: "Repeating", icon: "repeat", page: Repeating },
  { id: "integrations", label: "Integrations", icon: "plugs", page: Integrations },
  { id: "tokens", label: "Tokens", icon: "key", page: Tokens },
  { id: "about", label: "About you", icon: "user", page: AboutYou },
  { id: "shortcuts", label: "Shortcuts", icon: "keyboard", page: Shortcuts },
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
        <button className="btn btn-ghost" onClick={() => setDialog("setup")} title="Your day, load, free time and calendars, a question at a time">
          <Icon name="sliders-horizontal" size={15} />
          <span className="fr-head-note">Answer Setup’s questions again</span>
        </button>
        <button className="btn btn-secondary" onClick={() => navigate("/")}>
          <Icon name="arrow-left" size={15} />
          <span className="fr-head-note">Back to plan</span>
        </button>
      </div>
      <div className="fr-panel" style={{ display: "grid", ...(tight ? { gridTemplateRows: "auto minmax(0,1fr)" } : { gridTemplateColumns: "208px minmax(0,1fr)" }), overflow: "hidden" }}>
        <nav
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
