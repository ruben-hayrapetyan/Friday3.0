// What a finished drag does (DESIGN §18.4): a block or a to-do row dropped on the calendar is pinned there
// (preferred, or locked with Shift); a block dropped on the to-do pane is unpinned; a selection opens its menu.
// Resizing a block pins it with its new length.

import { type QueryClient, useQueryClient } from "@tanstack/react-query"
import { useCallback } from "react"
import type { Block, Item, Schemas } from "@/api/client"
import type { Drag } from "@/components/calendar/useDrag"
import { type Toast, useToast } from "@/components/Toasts"
import { fromMin } from "@/lib/time"
import { runCommand } from "./useCommand"

export interface Selection {
  start: string
  end: string
  x: number
  y: number
}

/** Show a pinned block where it was dropped until the server's plan arrives. */
export function moveBlock(client: QueryClient, key: string, start: string, end: string, kind: Block["pinned"]): void {
  client.setQueriesData<Schemas["PlanOut"]>({ queryKey: ["plan"] }, (plan) =>
    plan && {
      ...plan,
      // The key names the start, so the moved block gets a new one and stays selectable by it.
      blocks: plan.blocks.map((b) => (b.key === key ? { ...b, key: `T${b.item_id}@${start}`, start, end, pinned: kind } : b)),
    },
  )
}

/** A resized block of a fixed-length item changes the item's length too, by as much as the block grew. */
async function lengthen(client: QueryClient, toast: (t: Toast) => void, id: number, by: number): Promise<void> {
  const item = client.getQueryData<Item[]>(["items"])?.find((i) => i.id === id)
  if (!by || item?.amount !== "fixed" || item.duration_min == null) return
  await runCommand(client, toast, "edit", { id, duration_min: Math.max(15, item.duration_min + by) })
}

export function useDrop(onSelection: (selection: Selection) => void): (drag: Drag) => void {
  const client = useQueryClient()
  const toast = useToast()
  return useCallback(
    async (drag: Drag) => {
      if (!drag.moved) return
      if (drag.kind === "select") {
        if (drag.at) onSelection({ start: fromMin(drag.at.start), end: fromMin(drag.at.end), x: drag.x, y: drag.y })
        return
      }
      if (drag.itemId === null) return
      if (drag.over === "todo" && drag.kind !== "row") {
        runCommand(client, toast, "unpin", { id: drag.itemId })
        return
      }
      if (drag.over !== "calendar" || !drag.at) return
      const start = fromMin(drag.at.start)
      const end = fromMin(drag.at.end)
      const kind = drag.locked ? "locked" : "preferred"
      const key = drag.blockKey
      if (drag.kind === "resize") await lengthen(client, toast, drag.itemId, drag.at.end - drag.at.start - (drag.end - drag.start))
      runCommand(
        client,
        toast,
        "pin",
        // A row keeps the server's length (what's left of the item); a block keeps what was dragged, and its pin
        // replaces the one where it was.
        drag.kind === "row"
          ? { id: drag.itemId, start, kind }
          : { id: drag.itemId, start, end, kind, from_start: fromMin(drag.start), from_end: fromMin(drag.end) },
        { optimistic: key ? (c) => moveBlock(c, key, start, end, kind) : undefined },
      )
    },
    [client, toast, onSelection],
  )
}
