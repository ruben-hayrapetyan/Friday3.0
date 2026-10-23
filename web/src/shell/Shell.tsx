// The app's frame (v22): sidebar and page, the Now dock, and the overlays any page can open. Desktop only for now
// (your call, M11): it needs about 1100 px.

import { useQueryClient } from "@tanstack/react-query"
import { useEffect, useState } from "react"
import { Navigate, Route, Routes, useLocation, useNavigate, useSearchParams } from "react-router"
import { DragProvider } from "@/components/calendar/useDrag"
import { SelectionMenu } from "@/components/calendar/SelectionMenu"
import { BriefDialog, briefDue, LockDialog, TriageDialog } from "@/dialogs/Dialogs"
import { useToast } from "@/components/Toasts"
import { useNow, useStatus } from "@/hooks/queries"
import { runCommand, undoLast } from "@/hooks/useCommand"
import { type Selection, useDrop } from "@/hooks/useDrop"
import { useKeys } from "@/hooks/useKeys"
import { Dock } from "@/now/Dock"
import { BlockPopover } from "@/plan/BlockPopover"
import { OtherWaysDialog, WayBanner } from "@/plan/OtherWays"
import { PlanPage } from "@/plan/PlanPage"
import { BellPop } from "@/pops/BellPop"
import { PacePop } from "@/pops/PacePop"
import { ShovePop } from "@/pops/ShovePop"
import { InboxPage } from "@/inbox/InboxPage"
import { InsightsPage } from "@/insights/InsightsPage"
import { RulesLab } from "@/lab/rules/RulesLab"
import { ProjectsPage } from "@/projects/ProjectsPage"
import { ReviewPage } from "@/review/ReviewPage"
import { RulesPage } from "@/rules/RulesPage"
import { SettingsPage } from "@/settings/SettingsPage"
import { Search } from "@/search/Search"
import { Drawer, DrawerFrame } from "@/todo/Drawer"
import { EventPane } from "./EventPane"
import { TodoPage } from "@/todo/TodoPage"
import { useShell } from "./ShellContext"
import { Sidebar } from "./Sidebar"

export function Shell() {
  const { today, pop, setPop, dialog, setDialog, drawer, event } = useShell()
  const client = useQueryClient()
  const toast = useToast()
  const shove = (range: string) => runCommand(client, toast, "shove", { range }, { label: (o) => o.result.message ?? "Shoved" })
  const [selection, setSelection] = useState<Selection | null>(null)
  const onDrop = useDrop(setSelection)
  const location = useLocation()
  useShellKeys()
  useTriageLink()
  useEffect(() => {
    if (briefDue(today)) setDialog("brief")
  }, [today, setDialog])
  return (
    <DragProvider onDrop={onDrop}>
      <div style={{ height: "100vh", minWidth: 1100, display: "grid", gridTemplateColumns: "248px minmax(0,1fr)", background: "var(--fr-backdrop)", color: "var(--color-text)", overflow: "hidden", position: "relative" }}>
        <Sidebar showTodos={!location.pathname.startsWith("/todo")} />
        <main style={{ display: "grid", gridTemplateRows: "60px minmax(0,1fr)", minHeight: 0, minWidth: 0 }}>
          <Routes>
            <Route path="/" element={<PlanPage />} />
            <Route path="/todo" element={<TodoPage />} />
            <Route path="/projects" element={<ProjectsPage />} />
            <Route path="/review" element={<ReviewPage />} />
            <Route path="/inbox" element={<InboxPage />} />
            <Route path="/insights" element={<InsightsPage />} />
            <Route path="/rules" element={<RulesPage />} />
            <Route path="/lab/rules/:slug?" element={<RulesLab />} />
            <Route path="/settings/:section?" element={<SettingsPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
        {event && location.pathname === "/" ? (
          <DrawerFrame>
            <EventPane draft={event} />
          </DrawerFrame>
        ) : (
          drawer && location.pathname === "/" && <Drawer />
        )}
        {!location.pathname.startsWith("/settings") && <Dock />}
        <BlockPopover />
        {location.pathname === "/" && <WayBanner />}
        {pop && <div onClick={() => setPop(null)} style={{ position: "absolute", inset: 0, zIndex: 9 }} />}
        {pop === "shove" && <ShovePop />}
        {pop === "pace" && <PacePop />}
        {pop === "bell" && <BellPop />}
      </div>
      {selection && <SelectionMenu selection={selection} today={today} onShove={(range) => (setSelection(null), shove(range))} onClose={() => setSelection(null)} />}
      {dialog === "conflicts" && <LockDialog onClose={() => setDialog(null)} />}
      {dialog === "triage" && <TriageDialog onClose={() => setDialog(null)} />}
      {dialog === "brief" && <BriefDialog onClose={() => setDialog(null)} />}
      {dialog === "search" && <Search />}
      {dialog === "ways" && <OtherWaysDialog onClose={() => setDialog(null)} />}
    </DragProvider>
  )
}

/** Keys that work on every page: search, shove, pace, the timer, undo, a new to-do, Escape. */
function useShellKeys() {
  const { setPop, setDialog, select, setDrawer, drawer } = useShell()
  const client = useQueryClient()
  const toast = useToast()
  const navigate = useNavigate()
  const location = useLocation()
  const now = useNow().data
  const running = useStatus().data?.timer
  useKeys({
    palette: () => setDialog("search"),
    shove: () => setPop("shove"),
    pace: () => setPop("pace"),
    undo: () => undoLast(client, toast),
    drawer: () => setDrawer(!drawer),
    quickAdd: () => (location.pathname === "/" ? setDrawer(true) : navigate("/todo")),
    timer: () => {
      if (running) runCommand(client, toast, "stop", {})
      else if (now?.current && !now.current.fixed) runCommand(client, toast, "start", { id: now.current.item_id })
    },
  })
  useEffect(() => {
    const press = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setPop(null)
        select(null)
      }
    }
    window.addEventListener("keydown", press)
    return () => window.removeEventListener("keydown", press)
  }, [setPop, select, setDrawer, drawer])
}

/** A notification's "Options" opens the app at /?triage. */
function useTriageLink() {
  const { setDialog } = useShell()
  const [params, setParams] = useSearchParams()
  useEffect(() => {
    if (params.has("triage")) {
      setDialog("triage")
      setParams({}, { replace: true })
    }
  }, [params, setParams, setDialog])
}
