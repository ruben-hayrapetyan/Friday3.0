// Projects & exams: the exams ahead, each with its prep and how ready you are, then the open projects with their
// progress. A project opens to its steps and timeline (ProjectDetail); `?id=` names it, so links keep working.

import { useState } from "react"
import { useSearchParams } from "react-router"
import type { Block } from "@/api/client"
import { H, Icon } from "@/components/fr/controls"
import { useExams, useHorizon, useProjects, useSettings } from "@/hooks/queries"
import { dur, when } from "@/lib/format"
import { useLook } from "@/theme/LookProvider"
import { useShell } from "@/shell/ShellContext"
import { ExamCard } from "./ExamCard"
import { away, soonAndLater } from "./exams"
import { NewExam } from "./NewExam"
import { NewProject } from "./NewProject"
import { ProjectDetail } from "./ProjectDetail"
import { Bar, card, PROJECT_STATUS, type Project, projectPct, RULE, Section, StatusTag } from "./parts"

const GRID = (min: number) => ({ display: "grid", gridTemplateColumns: `repeat(auto-fill, minmax(min(100%, ${min}px), 1fr))`, gap: 16, alignItems: "start" }) as const

export function ProjectsPage() {
  const projects = useProjects().data ?? []
  const exams = useExams().data
  const blocks = useHorizon().data?.blocks ?? []
  const [params, setParams] = useSearchParams()
  const { layout } = useShell()
  const [creating, setCreating] = useState<"project" | "exam" | null>(null)
  const current = projects.find((p) => p.item.id === Number(params.get("id"))) ?? null
  const behind = projects.filter((p) => p.status === "late").length
  const note = [exams && `${exams.length} ${exams.length === 1 ? "exam" : "exams"} ahead`, `${projects.length} ${projects.length === 1 ? "project" : "projects"} open`, behind && `${behind} behind`].filter(Boolean).join(" · ")
  const icons = layout.tight // a narrow window: the two buttons as icons
  return (
    <>
      <div className="fr-page-head">
        <span className="fr-h fr-title">Projects & exams</span>
        <span className="fr-head-note tnum" style={{ color: "var(--color-neutral-500)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", minWidth: 0 }}>
          {note}
        </span>
        <div style={{ flex: 1 }} />
        <button className="btn btn-secondary" onClick={() => setCreating("exam")} aria-label="New exam" title="New exam" style={{ whiteSpace: "nowrap", flex: "none" }}>
          <Icon name="exam" />
          {!icons && "New exam"}
        </button>
        <button className="btn btn-primary" onClick={() => setCreating("project")} aria-label="New project" title="New project" style={{ whiteSpace: "nowrap", flex: "none" }}>
          <Icon name="plus" />
          {!icons && "New project"}
        </button>
      </div>
      <div className="fr-panel" style={{ overflowY: "auto", overflowX: "hidden" }}>
        {current ? (
          <ProjectDetail key={current.item.id} p={current} all={projects} onPick={(id) => setParams({ id: String(id) })} onBack={() => setParams({})} />
        ) : (
          <div className="fr-gutter" style={{ maxWidth: 1180, padding: "28px 40px 120px", display: "flex", flexDirection: "column", gap: 40, minWidth: 0 }}>
            <Exams exams={exams} blocks={blocks} onNew={() => setCreating("exam")} />
            <Projects projects={projects} blocks={blocks} onOpen={(id) => setParams({ id: String(id) })} onNew={() => setCreating("project")} />
          </div>
        )}
      </div>
      {creating === "project" && <NewProject onClose={(newId) => (setCreating(null), newId && setParams({ id: String(newId) }))} />}
      {creating === "exam" && <NewExam onClose={(made) => (setCreating(null), made && setParams({}))} />}
    </>
  )
}

function Exams({ exams, blocks, onNew }: { exams: ReturnType<typeof useExams>["data"]; blocks: Block[]; onNew: () => void }) {
  const { today, askClaude } = useShell()
  const settings = useSettings().data as { exam_focus?: { on: boolean; days_before: number } } | undefined
  const [more, setMore] = useState(false)
  if (!exams) return null
  const [soon, later] = soonAndLater(exams, today)
  const focus = settings?.exam_focus
  const right =
    exams.length > 0 &&
    (focus?.on ? (
      <span className="fr-kicker" style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <Icon name="target" size={12} />
        Exam focus is on, {focus.days_before} {focus.days_before === 1 ? "day" : "days"} before each
      </span>
    ) : (
      <button className="fr-plain fr-link" onClick={() => askClaude("I want to focus on an exam's course in the days before it", "rule")} style={{ fontSize: 12, display: "flex", alignItems: "center", gap: 6 }}>
        <Icon name="target" size={12} />
        Focus on each exam before it…
      </button>
    ))
  return (
    <Section title="Exams" note={soon.length ? "The next three weeks" : undefined} right={right}>
      {!exams.length && (
        <Empty icon="exam" text="No exams ahead. They come in from your class calendar, or add one, with how much prep it needs." action="New exam" onAction={onNew} />
      )}
      {exams.length > 0 && !soon.length && <span className="fr-kicker">Nothing in the next three weeks.</span>}
      {soon.length > 0 && (
        <div style={GRID(340)}>
          {soon.map((e) => (
            <ExamCard key={e.item.id} exam={e} blocks={blocks} />
          ))}
        </div>
      )}
      {later.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <button className="fr-plain fr-link" onClick={() => setMore(!more)} style={{ alignSelf: "flex-start", display: "flex", alignItems: "center", gap: 6, fontSize: 13 }}>
            <Icon name={more ? "caret-down" : "caret-right"} size={12} />
            {more ? "Later this term" : `${later.length} more later this term: ${later.map((e) => e.item.title).slice(0, 2).join(", ")}${later.length > 2 ? "…" : ""}`}
          </button>
          {more && (
            <div style={GRID(340)}>
              {later.map((e) => (
                <ExamCard key={e.item.id} exam={e} blocks={blocks} />
              ))}
            </div>
          )}
        </div>
      )}
    </Section>
  )
}

function Projects({ projects, blocks, onOpen, onNew }: { projects: Project[]; blocks: Block[]; onOpen: (id: number) => void; onNew: () => void }) {
  return (
    <Section title="Projects" note={projects.length ? "Open one for its steps and timeline" : undefined}>
      {!projects.length ? (
        <Empty icon="tree-structure" text="No projects yet. A project is something with steps, like an essay or a presentation." action="New project" onAction={onNew} />
      ) : (
        <div style={GRID(300)}>
          {projects.map((p) => (
            <ProjectCard key={p.item.id} p={p} blocks={blocks} onOpen={() => onOpen(p.item.id)} />
          ))}
          <button className="fr-plain fr-hover-soft" onClick={onNew} style={{ alignSelf: "stretch", minHeight: 120, display: "flex", alignItems: "center", justifyContent: "center", gap: 8, borderRadius: "var(--radius-lg)", border: `1.5px dashed ${RULE}`, color: "var(--color-neutral-400)" }}>
            <Icon name="plus" />
            New project
          </button>
        </div>
      )}
    </Section>
  )
}

/** A project at a glance: its tag, name and due date, how much is done, and the next step with when it's planned. */
function ProjectCard({ p, blocks, onOpen }: { p: Project; blocks: Block[]; onOpen: () => void }) {
  const { today } = useShell()
  const { color, light } = useLook()
  const steps = p.children.filter((c) => c.parent_id === p.item.id)
  const doneSteps = steps.filter((s) => s.status === "done").length
  const next = steps.find((s) => s.status !== "done")
  const nextAt = next && blocks.find((b) => b.item_id === next.id)?.start
  const [label, tone] = PROJECT_STATUS[p.status]
  const tint = color(p.item.area)
  const due = p.item.due
  return (
    <button className="fr-plain fr-hover-soft" onClick={onOpen} style={{ ...card(tint, light), gap: 12, textAlign: "left" }}>
      <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
        <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 6 }}>
          <span className="fr-eyebrow" style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            {p.item.area ?? "No tag"} · {p.item.preset ?? "Project"}
          </span>
          <H size={19} style={{ overflowWrap: "anywhere" }}>
            {p.item.title}
          </H>
        </div>
        <StatusTag label={label} tone={tone} />
      </div>
      {due && (
        <span className="tnum" style={{ fontSize: 12, color: "var(--color-neutral-300)" }}>
          Due {when(due, today)}
          <span style={{ color: away(due, today) === "Overdue" ? "var(--fr-due)" : "var(--color-neutral-500)" }}> · {away(due, today).toLowerCase()}</span>
        </span>
      )}
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        <Bar pct={projectPct(p)} color={tint} height={5} />
        <span className="tnum" style={{ display: "flex", justifyContent: "space-between", gap: 8, fontSize: 11.5, color: "var(--color-neutral-400)" }}>
          <span>
            {doneSteps} of {steps.length} steps
          </span>
          <span>
            {dur(p.done_min)} of {dur(p.done_min + p.remaining_min)}
          </span>
        </span>
      </div>
      {next && (
        <span style={{ display: "flex", gap: 6, alignItems: "baseline", fontSize: 12, color: "var(--color-neutral-400)", minWidth: 0 }}>
          <span style={{ flex: "none" }}>Next</span>
          <span style={{ color: "var(--color-text)", fontWeight: 500, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{next.title}</span>
          <span className="tnum" style={{ flex: "none", marginLeft: "auto", color: nextAt ? "var(--color-neutral-400)" : "var(--fr-warn)" }}>
            {nextAt ? when(nextAt, today) : "not planned"}
          </span>
        </span>
      )}
    </button>
  )
}

function Empty({ icon, text, action, onAction }: { icon: string; text: string; action: string; onAction: () => void }) {
  return (
    <div className="fr-well" style={{ display: "flex", alignItems: "center", gap: 14, padding: "18px 20px", flexWrap: "wrap" }}>
      <Icon name={icon} size={22} style={{ color: "var(--color-neutral-500)" }} />
      <span style={{ flex: 1, minWidth: "min(240px, 100%)", color: "var(--color-neutral-300)", textWrap: "pretty" }}>{text}</span>
      <button className="btn btn-secondary" onClick={onAction}>
        {action}
      </button>
    </div>
  )
}
