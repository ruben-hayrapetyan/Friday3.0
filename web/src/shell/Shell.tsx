// The app's frame (v22): sidebar and page, the Now dock, and the overlays any page can open. Desktop only for now
// (your call, M11): it needs about 1100 px.

import { useQueryClient } from "@tanstack/react-query"
import { useEffect, useState } from "react"
import { Navigate, Route, Routes, useLocation, useNavigate, useSearchParams } from "react-router"
import { DragProvider } from "@/components/calendar/useDrag"
import { SelectionMenu } from "@/components/calendar/SelectionMenu"
import { AskClaudeDialog } from "@/dialogs/AskClaude"
import { BriefDialog, briefDue, TriageDialog, useBriefSwitch } from "@/dialogs/Dialogs"
import { useDecisionsTitle } from "@/inbox/Decisions"
import { SetupDialog, useSetup } from "@/dialogs/Setup"
import { useToast } from "@/components/Toasts"
import { useNow, useStatus } from "@/hooks/queries"
import { runCommand, undoLast } from "@/hooks/useCommand"
import { type Selection, useDrop } from "@/hooks/useDrop"
import { useKeys } from "@/hooks/useKeys"
import { Dock } from "@/now/Dock"
import { BlockPopover } from "@/plan/BlockPopover"
import { OtherWaysDialog, WayBanner } from "@/plan/OtherWays"
import { PlanPage } from "@/plan/PlanPage"
import { PacePop } from "@/pops/PacePop"
import { markShoved } from "@/pops/shoved"
import { ShovePop } from "@/pops/ShovePop"
import { InboxPage } from "@/inbox/InboxPage"
import { InsightsPage } from "@/insights/InsightsPage"
import { BodyPage } from "@/body/BodyPage"
import { RulesLab } from "@/lab/rules/RulesLab"
import { ProjectsPage } from "@/projects/ProjectsPage"
import { RulesPage } from "@/rules/RulesPage"
import { SettingsPage } from "@/settings/SettingsPage"
import { Search } from "@/search/Search"
import { Drawer, DrawerFrame } from "@/todo/Drawer"
import { useWhatIf, whatIf } from "@/whatif/store"
import { WhatIfPanel } from "@/whatif/WhatIfPanel"
import { draftAt, EventPane } from "./EventPane"
import { TodoPage } from "@/todo/TodoPage"
import { nextHour, placeAfter, useHost } from "./host"
import { SIDEBAR } from "./layout"
import { useShell } from "./ShellContext"
import { FirstTour, Tour } from "./Tour"
import { Icon } from "@/components/fr/controls"
import { nowMin } from "@/hooks/useClock"
import { Sidebar } from "./Sidebar"
import { closes, type Opener, wasInFront } from "./toggles"
import { ErrorBoundary } from "@/components/ErrorBoundary"

export function Shell() {
  const { today, pop, setPop, dialog, setDialog, drawer, event, layout, drawerOver, drawerWidth, navOpen, setNavOpen, tour } = useShell()
  const client = useQueryClient()
  const toast = useToast()
  const shove = async (range: string) => {
    const out = await runCommand(client, toast, "shove", { range }, { label: (o) => o.result.message ?? "Shoved" })
    if (out?.result.created?.length) markShoved(out.result.created) // the time glows where it was taken back
  }
  const [selection, setSelection] = useState<Selection | null>(null)
  const onDrop = useDrop(setSelection)
  const location = useLocation()
  useShellKeys()
  useHostActions()
  useTriageLink()
  useDecisionsTitle()
  const setupData = useSetup().data
  const setupDone = setupData?.done
  const toured = setupData?.toured
  const [briefOn] = useBriefSwitch()
  useEffect(() => {
    if (setupDone === false && dialog !== "setup") setDialog("setup") // the first time Friday opens: a few questions before anything else, and back if anything took its place
    else if (setupDone && toured && briefOn && briefDue(today)) setDialog("brief") // not on top of the first quests
  }, [today, setDialog, setupDone, toured, briefOn, dialog])
  useEffect(() => setNavOpen(false), [location.pathname, setNavOpen]) // a page picked from the slid-out sidebar
  const narrow = layout.mode === "narrow"
  const w = useWhatIf()
  const trying = w.on && w.panel // What if's changes, in the drawer's place (whatif/WhatIfPanel.tsx)
  const drawerSpace = (drawer || event || trying) && location.pathname === "/" && !drawerOver ? drawerWidth + 12 : 0
  const vars = { "--fr-side": `${layout.side}px`, "--fr-drawer": `${drawerSpace}px`, "--fr-head-inset": narrow ? "56px" : "12px" } as React.CSSProperties
  return (
    <DragProvider onDrop={onDrop}>
      <div data-layout={layout.mode} data-tight={layout.tight || undefined} style={{ ...vars, height: "100vh", display: "grid", gridTemplateColumns: narrow ? "minmax(0,1fr)" : `${layout.side}px minmax(0,1fr)`, background: "var(--fr-backdrop)", color: "var(--color-text)", overflow: "hidden", position: "relative" }}>
        {!narrow && <Sidebar showTodos={!location.pathname.startsWith("/todo")} rail={layout.mode === "rail"} />}
        {narrow && (
          <button className="btn btn-icon btn-ghost" data-tour="menu" onClick={() => setNavOpen(true)} aria-label="Menu" style={{ position: "absolute", left: 10, top: 14, zIndex: 9, width: 34, height: 34 }}>
            <Icon name="list" size={20} />
          </button>
        )}
        {narrow && navOpen && (
          <>
            <div onClick={() => setNavOpen(false)} style={{ position: "absolute", inset: 0, zIndex: 30, background: "color-mix(in srgb, #000 40%, transparent)" }} />
            <div className="fr-float" style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: `min(${SIDEBAR + 32}px, 86vw)`, zIndex: 31, display: "flex", borderRadius: 0 }}>
              <Sidebar showTodos={false} onClose={() => setNavOpen(false)} />
            </div>
          </>
        )}
        <main style={{ display: "grid", gridTemplateRows: "60px minmax(0,1fr)", minHeight: 0, minWidth: 0 }}>
          <ErrorBoundary resetKey={location.pathname}>
          <Routes>
            <Route path="/" element={<PlanPage />} />
            <Route path="/todo" element={<TodoPage />} />
            <Route path="/projects" element={<ProjectsPage />} />
            <Route path="/exams" element={<Navigate to="/projects" replace />} />
            {/* Review, Your day and Check your tasks are messages in the Inbox now (29 Oct): old links and the Mac
                app's menu still get there */}
            <Route path="/review" element={<Navigate to="/inbox" replace />} />
            <Route path="/inbox" element={<InboxPage />} />
            <Route path="/inbox/day" element={<Navigate to="/inbox" replace />} />
            <Route path="/inbox/check" element={<Navigate to="/inbox" replace />} />
            <Route path="/insights" element={<InsightsPage />} />
            <Route path="/body" element={<BodyPage />} />
            <Route path="/rules" element={<RulesPage />} />
            <Route path="/lab/rules/:slug?" element={<RulesLab />} />
            <Route path="/settings/:section?" element={<SettingsPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
          </ErrorBoundary>
        </main>
        {event && location.pathname === "/" ? (
          <DrawerFrame>
            <EventPane draft={event} />
          </DrawerFrame>
        ) : drawer && location.pathname === "/" ? (
          <Drawer />
        ) : (
          trying &&
          location.pathname === "/" && (
            <DrawerFrame>
              <WhatIfPanel />
            </DrawerFrame>
          )
        )}
        {!location.pathname.startsWith("/settings") && !(drawerOver && (drawer || event || trying) && location.pathname === "/") && <Dock />}
        <BlockPopover />
        {location.pathname === "/" && <WayBanner />}
        {pop && <div onClick={() => setPop(null)} style={{ position: "absolute", inset: 0, zIndex: 9 }} />}
        {pop === "shove" && <ShovePop />}
        {pop === "pace" && <PacePop />}
      </div>
      {selection && <SelectionMenu selection={selection} today={today} onShove={(range) => (setSelection(null), shove(range))} onClose={() => setSelection(null)} />}
      {dialog === "triage" && <TriageDialog onClose={() => setDialog(null)} />}
      {dialog === "brief" && <BriefDialog onClose={() => setDialog(null)} />}
      {dialog === "search" && <Search />}
      {dialog === "ways" && <OtherWaysDialog onClose={() => setDialog(null)} />}
      {dialog === "ask" && <AskClaudeDialog onClose={() => setDialog(null)} />}
      {dialog === "setup" && <SetupDialog onClose={() => setDialog(null)} />}
      {tour && <Tour />}
      <FirstTour ready={setupDone === true && dialog === null} toured={toured} />
    </DragProvider>
  )
}

/** Keys that work on every page: search, shove, pace, the timer, undo, a new to-do, Escape. */
function useShellKeys() {
  const { setPop, setDialog, select, setDrawer, drawer, pop, dialog, event } = useShell()
  const opened = { dialog, pop, newEvent: event?.id === null }
  const client = useQueryClient()
  const toast = useToast()
  const navigate = useNavigate()
  const location = useLocation()
  const now = useNow().data
  const running = useStatus().data?.timer
  useKeys({
    // Each again closes what it opened (shell/toggles.ts): the page has the key, so Friday is in front.
    palette: () => setDialog(closes("search", opened, true) ? null : "search"),
    shove: () => setPop(closes("shove", opened, true) ? null : "shove"),
    pace: () => setPop(closes("pace", opened, true) ? null : "pace"),
    // While trying, ⌘Z takes back the last change you tried, never one of your real ones.
    undo: () => (whatIf.get().on && location.pathname === "/" ? whatIf.undoLast() : undoLast(client, toast)),
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

/** The Mac app's menus and hotkeys (COMBINED.md 5). The calendar's actions bring you to the calendar first. */
function useHostActions() {
  const { today, place, setPlace, setPop, setDialog, setDrawer, drawer, setEvent, askClaude, setTour, pop, dialog, event } = useShell()
  // A menu's shortcut or a hotkey again closes what it opened, when Friday was already in front (shell/toggles.ts).
  const again = (opener: Opener) => closes(opener, { dialog, pop, newEvent: event?.id === null }, wasInFront())
  const navigate = useNavigate()
  const location = useLocation()
  const toPlan = () => location.pathname !== "/" && navigate("/")
  useHost((request) => {
    if (dialog === "setup" && request.action !== "setup") return // setup first: nothing takes its place (the audit, 31 Oct)
    const moved = placeAfter(request, place, today)
    if (moved) return (toPlan(), setPlace(moved))
    switch (request.action) {
      case "newEvent":
        if (again("newEvent")) return setEvent(null)
        toPlan()
        return setEvent(draftAt(nextHour(nowMin())))
      case "newTodo":
        return location.pathname === "/" ? setDrawer(true) : navigate("/todo")
      case "search":
        return setDialog(again("search") ? null : "search")
      case "ask":
        return again("ask") ? setDialog(null) : askClaude()
      case "drawer":
        toPlan()
        return setDrawer(request.argument === "open" || !drawer)
      case "go":
        return navigate(request.argument ?? "/")
      case "ways":
        toPlan()
        return setDialog("ways")
      case "shove":
      case "pace":
        if (again(request.action)) return setPop(null)
        toPlan()
        return setPop(request.action)
      case "brief":
      case "triage":
        return setDialog(request.action)
      case "tour":
        return setTour(true)
      case "setup":
        return setDialog("setup")
    }
  })
}

/** A link to the app at /?triage opens the options for late work. */
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
