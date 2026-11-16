// A new Projects & exams page, tried beside the current one (/projects-v2): shelves and timelines. Three shelves:
// everything with a deadline on six weeks across (projects, exams and big to-dos, soonest first), ongoing projects
// with hours a week, and what's finished.
// Things open as they do elsewhere in Friday: a project, an exam or an ongoing project in place, with its address
// (?id=, ?exam=, ?ongoing=) so Back and links work; a big to-do on the To-do page, as the drawer opens one.

import { useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { Link, useNavigate, useSearchParams } from "react-router"
import { Icon } from "@/components/fr/controls"
import { useExams, useHorizon, useItems, useProjects } from "@/hooks/queries"
import { useCommand } from "@/hooks/useCommand"
import { useClock } from "@/hooks/useClock"
import { fromMin } from "@/lib/time"
import { dockRoom } from "@/now/dockRoom"
import { ExamCard } from "@/projects/ExamCard"
import { NewExam } from "@/projects/NewExam"
import { NewProject } from "@/projects/NewProject"
import { ProjectDetail } from "@/projects/ProjectDetail"
import { useShell } from "@/shell/ShellContext"
import { Deadlines } from "./Deadlines"
import { Finished } from "./Finished"
import { deadlineRows, type Project, type Row } from "./model"
import { NewOngoing } from "./NewOngoing"
import { OngoingDetail, OngoingShelf, useOngoing } from "./Ongoing"

export function ProjectsV2Page() {
  const { today, layout } = useShell()
  const navigate = useNavigate()
  const now = fromMin(useClock()) // the server's local time, as the calendar keeps it
  const projects = useProjects().data ?? []
  const exams = useExams().data ?? []
  const items = useItems().data ?? []
  const blocks = useHorizon().data?.blocks ?? []
  const ongoing = useOngoing().data ?? []
  const [params, setParams] = useSearchParams()
  const [creating, setCreating] = useState<"project" | "exam" | "ongoing" | null>(null)
  const rows = deadlineRows(projects, exams, items, blocks, now)
  const project = projects.find((p) => p.item.id === Number(params.get("id"))) ?? null
  const exam = exams.find((e) => e.item.id === Number(params.get("exam"))) ?? null
  const steady = ongoing.find((o) => o.id === Number(params.get("ongoing"))) ?? null
  const back = () => setParams({})
  const open = (r: Row) => (r.kind === "item" ? navigate(`/todo?item=${r.id}`) : setParams(r.kind === "exam" ? { exam: String(r.id) } : { id: String(r.id) }))
  const behind = rows.filter((r) => r.status === "late").length
  const note = [`${rows.length} with a deadline`, `${ongoing.length} ongoing`, behind && `${behind} behind`].filter(Boolean).join(" · ")
  const icons = layout.tight // a narrow window: the buttons as icons
  return (
    <>
      <div className="fr-page-head">
        <span className="fr-h fr-title">Projects & exams</span>
        <span className="fr-head-note tnum" style={{ color: "var(--color-neutral-400)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", minWidth: 0 }}>
          {note}
        </span>
        <div style={{ flex: 1 }} />
        <span style={{ display: "flex", gap: "inherit", flex: "none" }}>
          <Link to="/projects" className="btn btn-ghost" title="The Projects & exams page as it is now" style={{ whiteSpace: "nowrap" }}>
            <Icon name="arrow-left" />
            {!icons && "Current page"}
          </Link>
          <button className="btn btn-secondary" onClick={() => setCreating("exam")} aria-label="New exam" title="New exam" style={{ whiteSpace: "nowrap" }}>
            <Icon name="exam" />
            {!icons && "New exam"}
          </button>
          <button className="btn btn-secondary" onClick={() => setCreating("ongoing")} aria-label="New ongoing project" title="New ongoing project: hours a week, no deadline" style={{ whiteSpace: "nowrap" }}>
            <Icon name="repeat" />
            {!icons && "New ongoing"}
          </button>
          <button className="btn btn-primary" onClick={() => setCreating("project")} aria-label="New project" title="New project" style={{ whiteSpace: "nowrap" }}>
            <Icon name="plus" />
            {!icons && "New project"}
          </button>
        </span>
      </div>
      <div className="fr-panel" style={{ overflowY: "auto", overflowX: "hidden" }}>
        {project ? (
          <Opened>
            <ArchiveBar p={project} onArchived={back} />
            <ProjectDetail key={project.item.id} p={project} all={projects} onPick={(id) => setParams({ id: String(id) })} onBack={back} />
          </Opened>
        ) : exam ? (
          <Opened>
            <BackLink onBack={back} />
            <div style={{ maxWidth: 640 }}>
              <ExamCard exam={exam} blocks={blocks} />
            </div>
          </Opened>
        ) : steady ? (
          <Opened>
            <BackLink onBack={back} />
            <OngoingDetail key={steady.id} o={steady} today={today} onDeleted={back} />
          </Opened>
        ) : (
          <div className="fr-gutter" style={{ maxWidth: 1180, padding: `28px 40px ${dockRoom(120)}`, display: "flex", flexDirection: "column", gap: 36, minWidth: 0 }}>
            <Deadlines rows={rows} today={today} opened={null} onOpen={open} />
            <OngoingShelf ongoing={ongoing} today={today} opened={null} onOpen={(id) => setParams({ ongoing: String(id) })} />
            <Finished today={today} />
          </div>
        )}
      </div>
      {creating === "project" && <NewProject onClose={(id) => (setCreating(null), id && setParams({ id: String(id) }))} />}
      {creating === "exam" && <NewExam onClose={() => setCreating(null)} />}
      {creating === "ongoing" && <NewOngoing onClose={(id) => (setCreating(null), id && setParams({ ongoing: String(id) }))} />}
    </>
  )
}

function Opened({ children }: { children: React.ReactNode }) {
  return <div style={{ padding: `20px 40px ${dockRoom(120)}`, display: "flex", flexDirection: "column", gap: 12, minWidth: 0 }}>{children}</div>
}

function BackLink({ onBack }: { onBack: () => void }) {
  return (
    <button className="fr-plain fr-link" onClick={onBack} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, alignSelf: "flex-start" }}>
      <Icon name="arrow-left" size={13} /> All projects & exams
    </button>
  )
}

/** Archive, over a project's page: it's done, its open steps put away, and it moves to Finished (Undo, or Open again
 * there, brings it back). */
function ArchiveBar({ p, onArchived }: { p: Project; onArchived: () => void }) {
  const client = useQueryClient()
  const archive = useCommand("project_archive", {
    label: (o) => `${o.result.message}; it's under Finished`,
    optimistic: (c, input) => c.setQueryData<Project[]>(["projects"], (list) => list?.filter((x) => x.item.id !== input.id)),
  })
  return (
    <span style={{ display: "flex", justifyContent: "flex-end" }}>
      <button
        className="btn btn-ghost"
        onClick={() => (onArchived(), archive({ id: p.item.id }).then(() => client.invalidateQueries({ queryKey: ["projects_finished"] })))}
        title="Done with it: its open steps are put away and it moves to Finished"
        style={{ fontSize: 12.5 }}
      >
        <Icon name="archive" size={13} /> Archive
      </button>
    </span>
  )
}
