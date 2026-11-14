// What a step belongs to (13 Nov: a step's card read "Assignment · Draft · Sat 14 Nov 3pm–5pm", with nothing saying it
// was a step of "CDJ Article"): the project's name, one click from the project on the Projects page.

import { useNavigate } from "react-router"
import type { Item } from "@/api/client"
import { Icon } from "@/components/fr/controls"
import { useItem, useItems } from "@/hooks/queries"
import { projectOf } from "@/lib/todo"

/** The project `item` is a step of, and the project at the top (what Projects opens: a step inside a step is shown
 * there in its project), or nothing for an item on its own. A project already done is asked for by itself. */
export function useProjectOf(item: Pick<Item, "parent_id"> | null | undefined): { project: Item; top: Item } | undefined {
  const open = useItems().data ?? []
  const listed = item ? projectOf(item, open) : undefined
  const fetched = useItem(item?.parent_id != null && !listed ? item.parent_id : null).data?.item
  const project = listed ?? fetched
  if (!project) return undefined
  let top = project
  for (let up = projectOf(top, open), n = 0; up && n < 32; up = projectOf(up, open), n++) top = up
  return { project, top }
}

/** "Step of CDJ Article", opening the project. A long name is cut with an ellipsis on its one line, so nothing beside
 * it moves. */
export function StepOf({ item, onOpen }: { item: Pick<Item, "parent_id"> | null | undefined; onOpen?: () => void }) {
  const navigate = useNavigate()
  const found = useProjectOf(item)
  if (!found) return null
  const { project, top } = found
  return (
    <button
      className="fr-link"
      onClick={() => (onOpen?.(), navigate(`/projects?id=${top.id}`))}
      title={`Open ${top.title} in Projects`}
      style={{ alignSelf: "flex-start", display: "inline-flex", alignItems: "center", gap: 5, maxWidth: "100%", minWidth: 0, fontSize: 12 }}
    >
      <Icon name="tree-structure" size={12} style={{ flex: "none" }} />
      <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>Step of {project.title}</span>
    </button>
  )
}

/** The project's name in a list's row, quiet: the row itself opens the step. */
export function ProjectName({ item, style }: { item: Pick<Item, "parent_id">; style?: React.CSSProperties }) {
  const found = useProjectOf(item)
  if (!found) return null
  return (
    <span title={`A step of ${found.project.title}`} style={{ display: "inline-flex", alignItems: "center", gap: 4, minWidth: 0, ...style }}>
      <Icon name="tree-structure" size={11} style={{ flex: "none" }} />
      <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{found.project.title}</span>
    </span>
  )
}
