// What a break pauses, chosen for two calendars or forty (18 Nov: "say somebody has 20 calendars connected, this UI
// would be terrible"): two starting points, a search, and groups that fold, each saying how many are paused, with
// Pause all and Keep all in plain words (no half-filled box: "a weird green shade with a black bottom").

import { useQuery } from "@tanstack/react-query"
import { useState } from "react"
import { query } from "@/api/client"
import { Box, Chip, Icon } from "@/components/fr/controls"
import { allCalendars, calendarPaused, type Choices, EVERYTHING, flipCalendar, flipSeries, listed, type Pause, pauses } from "./words"

export const useBreakChoices = () => useQuery({ queryKey: ["break_choices"], queryFn: () => query("break_choices") })

type Group = "calendars" | "tags" | "series"

export function PauseChooser({ pause, onChange }: { pause: Pause; onChange: (pause: Pause) => void }) {
  const choices = useBreakChoices().data
  const [search, setSearch] = useState("")
  const [open, setOpen] = useState<Group | null>("calendars")
  if (!choices) return <span className="fr-kicker">Reading your calendars…</span>
  const q = search.trim().toLowerCase()
  const match = (...words: string[]) => !q || words.some((w) => w.toLowerCase().includes(q))
  const paused = choices.series.filter((s) => pauses(pause, s.id, s.calendar))
  const calendars = choices.calendars.filter((c) => match(c.name))
  const tags = choices.tags.filter((t) => match(t))
  const series = choices.series.filter((s) => match(s.title, s.calendar))
  const nothing = q && !calendars.length && !tags.length && !series.length
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        <Chip on={pause.repeating === "all"} onClick={() => onChange({ ...EVERYTHING, tags: pause.tags })}>
          Everything that repeats
        </Chip>
        <Chip on={pause.repeating === "only"} onClick={() => onChange({ ...allCalendars(pause, false), tags: pause.tags })}>
          Only what I pick
        </Chip>
      </div>
      {(choices.calendars.length + choices.series.length + choices.tags.length > 8) && (
        <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Icon name="magnifying-glass" size={13} style={{ color: "var(--color-neutral-500)" }} />
          <input className="input" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Find a calendar, tag or event" aria-label="Find a calendar, tag or event" style={{ flex: 1, minWidth: 0 }} />
        </label>
      )}
      {nothing && <span className="fr-kicker">Nothing called “{search.trim()}”.</span>}
      <Section
        title="Calendars"
        count={`${choices.calendars.filter((c) => calendarPaused(pause, c.name)).length} of ${choices.calendars.length} paused`}
        open={!!q || open === "calendars"}
        hidden={!!q && !calendars.length}
        onOpen={() => setOpen(open === "calendars" ? null : "calendars")}
        onAll={(on) => onChange({ ...allCalendars(pause, on), tags: pause.tags })}
      >
        {calendars.map((c) => (
          <Choice key={c.name} on={calendarPaused(pause, c.name)} onClick={() => onChange(flipCalendar(pause, c.name))} note={c.repeats ? `${c.repeats} repeating` : "no repeats"}>
            {c.name}
          </Choice>
        ))}
      </Section>
      <Section
        title="Tasks by tag"
        count={`${pause.tags.length} of ${choices.tags.length} wait`}
        open={!!q || open === "tags"}
        hidden={(!!q && !tags.length) || !choices.tags.length}
        onOpen={() => setOpen(open === "tags" ? null : "tags")}
        onAll={(on) => onChange({ ...pause, tags: on ? [...choices.tags] : [] })}
      >
        {tags.map((t) => (
          <Choice key={t} on={pause.tags.includes(t)} onClick={() => onChange({ ...pause, tags: pause.tags.includes(t) ? pause.tags.filter((x) => x !== t) : [...pause.tags, t] })}>
            {t}
          </Choice>
        ))}
      </Section>
      <Section
        title="Repeating events"
        count={`${paused.length} of ${choices.series.length} paused`}
        open={!!q || open === "series"}
        hidden={(!!q && !series.length) || !choices.series.length}
        onOpen={() => setOpen(open === "series" ? null : "series")}
        onAll={(on) => onChange({ ...allCalendars(pause, on), tags: pause.tags })}
      >
        {series.map((s) => (
          <Choice key={s.id} on={pauses(pause, s.id, s.calendar)} onClick={() => onChange(flipSeries(pause, s.id, s.calendar))} note={`${s.calendar} · ${s.every}`}>
            {s.title}
          </Choice>
        ))}
      </Section>
      <span style={{ fontSize: 12, color: "var(--color-neutral-300)", textWrap: "pretty" }}>{effect(pause, choices, paused.map((s) => s.title))}</span>
    </div>
  )
}

/** The chooser's sentence: what the break will actually pause (the lecture: show the effect, not the setting). */
export function effect(pause: Pause, choices: Choices, titles: string[]): string {
  const events = titles.length ? `${titles.length} repeating event${titles.length === 1 ? "" : "s"} (${listed(titles, 3)})` : "no repeating events"
  const tags = pause.tags.length ? ` and tasks tagged ${listed(pause.tags)}` : ""
  const none = !choices.series.length ? " You have no repeating events yet; any you add follow this." : ""
  return `This pauses ${events}${tags}. One-off events stay.${none}`
}

function Section(props: { title: string; count: string; open: boolean; hidden?: boolean; onOpen: () => void; onAll: (on: boolean) => void; children: React.ReactNode }) {
  if (props.hidden) return null
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4, paddingTop: 6, boxShadow: "inset 0 1px 0 color-mix(in srgb, var(--color-text) 7%, transparent)" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <button className="fr-plain" onClick={props.onOpen} aria-expanded={props.open} style={{ display: "inline-flex", alignItems: "center", gap: 6, fontWeight: 600, cursor: "pointer" }}>
          <Icon name={props.open ? "caret-down" : "caret-right"} size={11} style={{ color: "var(--color-neutral-500)" }} />
          {props.title}
          <span className="tnum" style={{ fontWeight: 400, fontSize: 12, color: "var(--color-neutral-500)" }}>
            {props.count}
          </span>
        </button>
        <span style={{ flex: 1 }} />
        <button className="fr-plain fr-link" onClick={() => props.onAll(true)} style={{ fontSize: 12 }}>
          Pause all
        </button>
        <button className="fr-plain fr-link" onClick={() => props.onAll(false)} style={{ fontSize: 12 }}>
          Keep all
        </button>
      </div>
      {props.open && <div style={{ maxHeight: 220, overflowY: "auto", display: "flex", flexDirection: "column", paddingLeft: 17 }}>{props.children}</div>}
    </div>
  )
}

function Choice({ on, onClick, note, children }: { on: boolean; onClick: () => void; note?: string; children: React.ReactNode }) {
  return (
    <button className="fr-plain fr-hover" aria-pressed={on} onClick={onClick} style={{ display: "flex", alignItems: "center", gap: 9, padding: "5px 6px", borderRadius: "var(--radius-sm)", textAlign: "left", cursor: "pointer", minWidth: 0 }}>
      <Box on={on} />
      <span style={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{children}</span>
      {note && (
        <span className="tnum" style={{ marginLeft: "auto", paddingLeft: 10, fontSize: 11, color: "var(--color-neutral-500)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", minWidth: 0 }}>
          {note}
        </span>
      )}
    </button>
  )
}
