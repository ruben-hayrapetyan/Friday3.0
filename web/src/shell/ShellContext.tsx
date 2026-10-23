// What the shell's overlays share: the open pop-up, the selected block, the to-do drawer and the dialogs. Pages
// open them; the shell draws them.

import { createContext, type ReactNode, useContext, useMemo, useState } from "react"
import type { Block } from "@/api/client"

export type Pop = "shove" | "pace" | "bell" | null
export type Dialog = "brief" | "search" | "triage" | "conflicts" | null

interface Shell {
  today: string
  pop: Pop
  setPop: (pop: Pop) => void
  selected: Block | null
  select: (block: Block | null) => void
  drawer: boolean
  setDrawer: (open: boolean) => void
  dialog: Dialog
  setDialog: (dialog: Dialog) => void
}

const Ctx = createContext<Shell | null>(null)

export function ShellProvider({ today, children }: { today: string; children: ReactNode }) {
  const [pop, setPop] = useState<Pop>(null)
  const [selected, select] = useState<Block | null>(null)
  const [drawer, setDrawer] = useState(false)
  const [dialog, setDialog] = useState<Dialog>(null)
  const value = useMemo(
    () => ({ today, pop, setPop, selected, select, drawer, setDrawer, dialog, setDialog }),
    [today, pop, selected, drawer, dialog],
  )
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useShell(): Shell {
  const value = useContext(Ctx)
  if (!value) throw new Error("useShell outside ShellProvider")
  return value
}
