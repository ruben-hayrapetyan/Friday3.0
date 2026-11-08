// A task found from its block on the calendar (8 Nov: "make double clicking a scheduled task take you to the task page
// and open up that tasks menu. also have the task briefly flash ... blue"): the To-do page opens on its detail, in the
// list that holds it, scrolls its row into view and flashes it Cerulean, once.

/** Where a double-click on a planned block of task `id` goes. */
export function foundHref(id: number): string {
  return `/todo?item=${id}&found=1`
}

/** The list a task shows in when the one open doesn't hold it: the Due list keeps whatever you were looking at. */
export function listHolding(item: { long_term?: boolean }, open: string, shownThere: boolean): string {
  if (shownThere) return open
  return item.long_term ? "Long term" : "Short term"
}

export const FOUND_MS = 1600 // two pulses, then the row as it was (selected)

/** Scroll the row of task `id` into view and flash it; false while the row isn't drawn yet. */
export function flashRow(id: number, color: string, root: Pick<ParentNode, "querySelector"> = document): boolean {
  const row = root.querySelector<HTMLElement>(`[data-todo-row="${id}"]`)
  if (!row) return false
  row.scrollIntoView?.({ block: "center", behavior: "smooth" })
  row.style.setProperty("--fr-found", color)
  row.classList.remove("fr-found")
  void row.offsetWidth // restart the animation when it's found again
  row.classList.add("fr-found")
  setTimeout(() => row.classList.remove("fr-found"), FOUND_MS)
  return true
}
