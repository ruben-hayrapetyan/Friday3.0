// An exam, in the Projects page's popup (16 Nov, the user: the exam's fields and adding its prep were unintuitive): when it is and
// how ready you are; its prep as a list you change in place (tick it, rename it, how long, by when, delete it) with
// + Add prep for another; then its tag and exam focus as rows. Every change shows at once.

import { type QueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { useNavigate } from "react-router"
import type { Item } from "@/api/client"
import { Check, H, Icon } from "@/components/fr/controls"
import { useAreas, useHorizon, useSettings } from "@/hooks/queries"
import { useClock } from "@/hooks/useClock"
import { useCommand } from "@/hooks/useCommand"
import { dur, when } from "@/lib/format"
import { countdown, course, prepState, sitting, summary } from "@/projects/exams"
import { TONE, useTag } from "@/projects/parts"
import { useRules } from "@/rules/RulesPage"
import { useShell } from "@/shell/ShellContext"
import { useLook } from "@/theme/LookProvider"
import { DuePicker, LengthField } from "@/todo/Pickers"
import type { Exam } from "./model"
import { Choices, DropField, Rows, SettingRow } from "./Rows"

/** A change to one of an exam's prep, shown before the server answers; `null` takes it away. */
function changedPrep(client: QueryClient, prepId: number, change: Partial<Item> | null): void {
  client.setQueryData<Exam[]>(["exams"], (list) =>
    list?.map((e) => ({ ...e, prep: change === null ? e.prep.filter((p) => p.item.id !== prepId) : e.prep.map((p) => (p.item.id === prepId ? { ...p, item: { ...p.item, ...change } } : p)) })),
  )
}

const FOCUS = [0, 1, 2, 3, 5, 7] // days before an exam its class has to itself; 0 is off
const daysWord = (d: number) => (d === 1 ? "the day" : `${d} days`)

export function ExamPanel({ exam }: { exam: Exam }) {
  const { today, setPlace } = useShell()
  const { color } = useLook()
  const navigate = useNavigate()
  const now = useClock()
  const blocks = useHorizon().data?.blocks ?? []
  const e = exam.item
  const start = e.start ?? `${today}T00:00`
  const end = e.end ?? start
  const area = e.area ?? exam.prep.find((p) => p.item.area)?.item.area ?? null
  const tint = color(area)
  const states = exam.prep.map((p) => prepState(p, blocks, start, today))
  const line = summary(exam, states, today)
  const [open, setOpen] = useState<"tag" | "focus" | null>(null)
  const retag = useTag(e.id, e.title)
  const areas = (useAreas().data ?? []).filter((a) => !a.archived).map((a) => a.name)
  // this exam's own days of focus, else the rule's (19 Nov, a user's notes: "what is the point of this dropdown if it
  // affects all classes' exams and not just this one?"; your answer: "do each exam"); someone without exams never
  // sees it, as it's only in an exam's popup
  const focus = (useRules().data ?? []).find((r) => r.type === "exam_focus")
  const ruleDays = focus?.enabled ? Number((focus?.reading as { amount?: number } | null)?.amount ?? focus?.number?.value ?? 3) : 0
  const focusDays = exam.focus_days ?? 0
  const each = ((useSettings().data as Record<string, unknown> | undefined)?.exam_focus_each ?? {}) as Record<string, number>
  const save = useCommand("settings_set", {
    label: () => `${e.title}: saved`,
    optimistic: (client, input) => {
      const days = (input.value as Record<string, number>)[String(e.id)]
      client.setQueryData<Exam[]>(["exams"], (list) => list?.map((x) => (x.item.id !== e.id ? x : { ...x, focus_days: days ?? (ruleDays || null), focus_own: days !== undefined })))
    },
  })
  // a number of days, or none, for this exam alone; "As your other exams" lets it follow the rule again
  const pickFocus = (days: number | null) => {
    const rest = Object.fromEntries(Object.entries(each).filter(([k]) => k !== String(e.id)))
    save({ key: "exam_focus_each", value: days === null ? rest : { ...rest, [String(e.id)]: days } })
  }
  const total = exam.done_min + exam.remaining_min
  return (
    <>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        <span className="fr-eyebrow" style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <span style={{ width: 10, height: 10, borderRadius: 3, background: tint }} />
          {course({ ...e, area }) ?? "Exam"} · {countdown(start, end, now, today)}
        </span>
        <H size={26} style={{ overflowWrap: "anywhere" }}>
          {e.title}
        </H>
        <span className="tnum" style={{ fontSize: 13, color: "var(--color-neutral-300)" }}>
          {sitting(start, end)}
        </span>
      </div>
      <div className="fr-well" style={{ display: "flex", flexDirection: "column", gap: 6, padding: "12px 14px" }}>
        <span style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "baseline" }}>
          <span style={{ fontWeight: 500 }}>Prep</span>
          <span className="tnum" style={{ fontSize: 13 }}>{total ? `${dur(exam.done_min) || "0m"} of ${dur(total)} done` : "None yet"}</span>
        </span>
        <span style={{ fontSize: 12, color: TONE[line.tone] }}>{line.text}</span>
      </div>
      <section aria-label="Its prep" style={{ display: "flex", flexDirection: "column", gap: 2 }}>
        {exam.prep.map((p) => (
          <PrepRow key={p.item.id} prep={p.item} examStart={start} today={today} />
        ))}
        <AddPrep exam={exam} area={area} start={start} />
      </section>
      <Rows>
        <SettingRow label="Tag" value={e.area ?? "No tag"} open={open === "tag"} onToggle={() => setOpen(open === "tag" ? null : "tag")} note="Its course: its color, and the prep added from here">
          <Choices label="Tag" value={e.area ?? null} onPick={(t: string | null) => (t !== (e.area ?? null) && retag(t), setOpen(null))} options={[{ value: null as string | null, label: "No tag" }, ...areas.map((a) => ({ value: a as string | null, label: a }))]} />
        </SettingRow>
        {/* what "exam focus" does, said as what you'd see (17 Nov: "what does exam focus even mean, its very confusing"),
            set for this exam alone (19 Nov); the rule in Rules is what an exam without its own follows */}
        <SettingRow label="Before this exam" value={focusDays ? `Only its class's work, ${daysWord(focusDays)} before` : "Other classes' work goes on as usual"} open={open === "focus"} onToggle={() => setOpen(open === "focus" ? null : "focus")} note={`For this exam only. Work for other classes due after it waits until it's over${exam.focus_own ? "" : ruleDays ? `; now as your other exams (Rules)` : ""}`}>
          <Choices
            label="Before this exam"
            value={exam.focus_own ? focusDays : null}
            onPick={(d: number | null) => (pickFocus(d), setOpen(null))}
            options={[
              { value: null as number | null, label: "As your other exams", desc: ruleDays ? `${daysWord(ruleDays)} before, from your rule in Rules`.replace(/^t/, "T") : "Other classes go on as usual (no rule in Rules)" },
              ...FOCUS.map((d) => ({ value: d as number | null, label: d ? `${daysWord(d)} before`.replace(/^t/, "T") : "Off", desc: d ? "Only the exam's class is planned then" : "Other classes go on as usual" })),
            ]}
          />
        </SettingRow>
      </Rows>
      <button className="fr-plain fr-link" onClick={() => (setPlace({ view: 1, first: start.slice(0, 10) }), navigate("/"))} style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 12, alignSelf: "flex-start" }}>
        <Icon name="calendar-dots" size={13} />
        See the day on the calendar
      </button>
    </>
  )
}

/** One prep: tick it, its name (a click renames it), how long, by when, open it on To-do, and delete. */
function PrepRow({ prep, examStart, today }: { prep: Item; examStart: string; today: string }) {
  const navigate = useNavigate()
  const done = useCommand("done", { label: () => `${prep.title}: done`, optimistic: (c) => changedPrep(c, prep.id, { status: "done" }) })
  const reopen = useCommand("reopen", { label: () => `${prep.title}: open again`, optimistic: (c) => changedPrep(c, prep.id, { status: "todo" }) })
  const edit = useCommand("edit", { label: () => "Saved", optimistic: (c, input) => changedPrep(c, prep.id, { ...(input.title ? { title: input.title } : {}), ...(input.duration_min ? { duration_min: input.duration_min } : {}), ...(input.due !== undefined ? { due: input.due ?? null } : {}) }) })
  const drop = useCommand("drop", { label: () => `${prep.title} deleted`, optimistic: (c) => changedPrep(c, prep.id, null) })
  const [naming, setNaming] = useState(false)
  const [title, setTitle] = useState(prep.title)
  const isDone = prep.status === "done"
  const rename = () => (title.trim() && title.trim() !== prep.title && edit({ id: prep.id, title: title.trim() }), setNaming(false))
  const by = !prep.due || prep.due >= examStart ? "by the exam" : `by ${when(prep.due, today)}`
  return (
    <div role="listitem" aria-label={prep.title} style={{ display: "grid", gridTemplateColumns: "20px minmax(0,1fr) auto auto 28px 28px", gap: 8, alignItems: "center", padding: "4px 0", opacity: isDone ? 0.6 : 1 }}>
      <Check small done={isDone} onToggle={() => (isDone ? reopen({ id: prep.id }) : done({ id: prep.id }))} />
      {naming ? (
        <input
          autoFocus
          className="input"
          value={title}
          onChange={(ev) => setTitle(ev.target.value)}
          onBlur={rename}
          onKeyDown={(ev) => (ev.key === "Enter" ? (ev.preventDefault(), rename()) : ev.key === "Escape" && (ev.preventDefault(), setTitle(prep.title), setNaming(false)))}
          aria-label={`Rename ${prep.title}`}
          style={{ minWidth: 0, padding: "2px 6px", minHeight: 0, fontSize: 13 }}
        />
      ) : (
        <button className="fr-plain fr-hover-text" onClick={() => (setTitle(prep.title), setNaming(true))} title="Click to rename" style={{ minWidth: 0, textAlign: "left", fontSize: 13, overflowWrap: "anywhere", textDecoration: isDone ? "line-through" : undefined }}>
          {prep.title}
        </button>
      )}
      <LengthField value={prep.duration_min ?? null} onPick={(m) => m && m !== prep.duration_min && edit({ id: prep.id, duration_min: m })} label={`Length of ${prep.title}`} amounts={[30, 60, 120, 180, 240, 480]} />
      <DropField label={`When ${prep.title} is due`} value={by}>
        {(close) => <DuePicker value={prep.due ?? examStart} today={today} onPick={(v) => (edit({ id: prep.id, due: v && v > examStart ? examStart : v }), close())} autoFocus={false} />}
      </DropField>
      {/* its notes and planned sessions, as the old exam cards opened it (0.5.0 kept every way in) */}
      <button className="btn btn-icon btn-ghost" onClick={() => navigate(`/todo?item=${prep.id}`)} aria-label={`Open ${prep.title} on To-do`} title="Open it on the To-do page: its notes and planned sessions" style={{ width: 28, height: 28, color: "var(--color-neutral-400)" }}>
        <Icon name="arrow-square-out" size={14} />
      </button>
      <button className="btn btn-icon btn-ghost" onClick={() => drop({ id: prep.id })} aria-label={`Delete ${prep.title}`} title="Delete it (Undo brings it back)" style={{ width: 28, height: 28, color: "var(--color-neutral-400)" }}>
        <Icon name="trash" size={14} />
      </button>
    </div>
  )
}

/** + Add prep: a name and how long, due by the exam, in its course. */
function AddPrep({ exam, area, start }: { exam: Exam; area: string | null; start: string }) {
  const [adding, setAdding] = useState(false)
  const [title, setTitle] = useState("")
  const [minutes, setMinutes] = useState<number>(120)
  const add = useCommand("add", {
    label: (o) => `${o.result.item?.title ?? "Prep"} added`,
    optimistic: (client, input) =>
      client.setQueryData<Exam[]>(["exams"], (list) =>
        list?.map((e) => (e.item.id === exam.item.id ? { ...e, prep: [...e.prep, { item: { ...exam.item, id: -Date.now(), title: String(input?.title ?? ""), preset: "Exam prep", when: "window", start: null, end: null, due: start, duration_min: minutes, status: "todo", done_min: 0, remaining_min: minutes } as Item, planned_finish: null }] } : e)),
      ),
  })
  const save = () => {
    if (!title.trim()) return
    add({ title: title.trim(), preset: "Exam prep", due: start, duration_min: minutes, area, before: [exam.item.id] })
    setTitle("")
  }
  if (!adding)
    return (
      <button className="fr-plain fr-link" onClick={() => setAdding(true)} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, padding: "6px 0", alignSelf: "flex-start" }}>
        <Icon name="plus" size={13} /> Add prep
      </button>
    )
  return (
    <div className="fr-well" style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", padding: 10, marginTop: 4 }}>
      <input autoFocus className="input" value={title} onChange={(ev) => setTitle(ev.target.value)} onKeyDown={(ev) => (ev.key === "Enter" ? save() : ev.key === "Escape" && (ev.preventDefault(), setAdding(false)))} placeholder="What, e.g. Practice exam 2" aria-label="New prep" style={{ flex: "1 1 180px", minWidth: 0, fontSize: 13 }} />
      <LengthField value={minutes} onPick={(m) => m && setMinutes(m)} label="How long the new prep takes" amounts={[30, 60, 120, 180, 240, 480]} />
      <button className="btn btn-primary" onClick={save} disabled={!title.trim()} style={{ fontSize: 12 }}>
        Add
      </button>
      <button className="btn btn-ghost" onClick={() => setAdding(false)} style={{ fontSize: 12 }}>
        Done
      </button>
    </div>
  )
}
