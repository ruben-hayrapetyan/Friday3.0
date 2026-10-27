// What a block's card does, done to every block and event picked on the calendar (plan/picks.ts): done, kept or
// locked where they are or left to Friday, a due, the estimate, a tag, a kind, the rest of a to-do's detail, deleted.
// Dragging one of them moves them all, and ↑ ↓ move them a quarter hour; Esc or a plain click lets go.

import { useQueryClient } from "@tanstack/react-query"
import { useEffect } from "react"
import type { Item, Schemas } from "@/api/client"
import { Dropdown, MenuRow } from "@/components/fr/Dropdown"
import { useToast } from "@/components/Toasts"
import { useItems } from "@/hooks/queries"
import { runCommand } from "@/hooks/useCommand"
import { moveBlock } from "@/hooks/useDrop"
import { DeleteButton, DoneButton, DueAction, EstimateAction, GroupBar, KindAction, menuOpen, MoreAction, TagAction, useGroup } from "@/todo/Bulk"
import { current, itemsOf, picks, usePicks } from "./picks"

const many = (n: number, one: string) => `${n} ${one}${n === 1 ? "" : "s"}`

export function PickBar({ plan }: { plan: Schemas["PlanOut"] }) {
  const client = useQueryClient()
  const toast = useToast()
  const list = usePicks()
  const open = useItems().data ?? []
  const byId = new Map<number, Item>([...plan.fixed, ...open].map((i) => [i.id, i]))
  const items = itemsOf(list)
    .map((id) => byId.get(id))
    .filter((i): i is Item => !!i)
  const tasks = items.filter((i) => i.when !== "fixed")
  const all = useGroup(items, picks.clear)
  const work = useGroup(tasks, picks.clear)
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLElement && e.target.closest("input, textarea, select, [contenteditable]")) return
      if (e.key === "Escape" && !menuOpen()) picks.clear()
    }
    window.addEventListener("keydown", key)
    return () => (window.removeEventListener("keydown", key), picks.clear()) // leaving the calendar lets go
  }, [])
  useEffect(() => {
    const now = current(picks.get(), plan.blocks, plan.fixed)
    if (now !== picks.get()) picks.set(now)
  }, [plan])
  if (!list.length) return null
  const blocks = list.filter((p) => !p.event)
  const events = list.length - blocks.length
  const label = [blocks.length ? many(blocks.length, "block") : "", events ? many(events, "event") : ""].filter(Boolean).join(", ")
  // Where each block is, as dragging it there pins it; the picks keep their new pins.
  const pinHere = (kind: "preferred" | "locked") =>
    work.together(
      "pin",
      `${kind === "locked" ? "Locked" : "Kept"} ${many(blocks.length, "block")} where ${blocks.length === 1 ? "it is" : "they are"}`,
      blocks.map((p) => () => runCommand(client, toast, "pin", { id: p.itemId, start: p.start, end: p.end, kind, from_start: p.start, from_end: p.end }, { quiet: true, optimistic: (c) => moveBlock(c, p.key, p.start, p.end, kind) })),
    ).then(() => picks.set(picks.get().map((p) => (p.event ? p : { ...p, pinned: kind }))))
  const pinned = itemsOf(blocks.filter((p) => p.pinned), true)
  return (
    <GroupBar label={label} onClear={picks.clear} place="calendar" hint="Drag one to move them all · ↑ ↓ a quarter hour">
      {tasks.length > 0 && <DoneButton g={work} />}
      {blocks.length > 0 && (
        <Dropdown icon="push-pin" label={work.working("pin", "Pin")} wide up>
          {(close) => (
            <>
              <MenuRow icon="push-pin" label="Keep them here" note="Friday plans around them and moves them only if work would be late" onClick={() => (close(), pinHere("preferred"))} />
              <MenuRow icon="lock-simple" label="Lock them here" note="They don't move, whatever else changes" onClick={() => (close(), pinHere("locked"))} />
              {pinned.length > 0 && (
                <MenuRow
                  icon="sparkle"
                  label="Let Friday decide"
                  note="Their pins come off, and Friday finds them the best times again"
                  onClick={() => (close(), work.together("pin", `Friday decides ${many(pinned.length, "task")} again`, pinned.map((id) => () => runCommand(client, toast, "unpin", { id }, { quiet: true })), true))}
                />
              )}
            </>
          )}
        </Dropdown>
      )}
      {tasks.length > 0 && <DueAction g={work} />}
      {tasks.length > 0 && <EstimateAction g={work} />}
      <TagAction g={all} />
      {tasks.length > 0 && <KindAction g={work} />}
      <MoreAction g={all} />
      <DeleteButton g={all} label={events && !tasks.length ? "Delete these" : "Delete"} />
    </GroupBar>
  )
}
