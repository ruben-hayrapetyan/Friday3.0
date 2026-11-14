import { QueryClient, QueryClientProvider, useQueryClient } from "@tanstack/react-query"
import { useEffect, useState } from "react"
import { HashRouter } from "react-router"
import { useServerEvents } from "@/api/events"
import { ErrorBoundary } from "@/components/ErrorBoundary"
import { Toasts } from "@/components/Toasts"
import { useCalendar, useSettings, useStatus } from "@/hooks/queries"
import { nowMin } from "@/hooks/useClock"
import { setClock } from "@/lib/clock"
import { setDayStart } from "@/lib/dayStart"
import { fromMin } from "@/lib/time"
import { Shell } from "@/shell/Shell"
import { ShellProvider } from "@/shell/ShellContext"
import { TermsGate, useTerms } from "@/terms/TermsGate"
import { LookProvider } from "@/theme/LookProvider"

const client = new QueryClient({ defaultOptions: { queries: { staleTime: 30_000, retry: 1 } } })

export default function App() {
  return <Friday client={client} />
}

/** The whole app over a query cache of its own (the screen tests give each test a fresh one). */
export function Friday({ client }: { client: QueryClient }) {
  return (
    <QueryClientProvider client={client}>
      <LookProvider>
        <Toasts>
          <HashRouter>
            <ErrorBoundary whole>
              <Root />
            </ErrorBoundary>
          </HashRouter>
        </Toasts>
      </LookProvider>
    </QueryClientProvider>
  )
}

/** Your day start, given to the helpers that place things by day (lib/dayStart.ts): set while rendering, so what
 * draws below already follows it. */
export function useDayStart(): void {
  const settings = useSettings().data as Record<string, { day_start?: string }> | undefined
  setDayStart(settings?.time?.day_start)
}

/** Your clock, given to the helpers that write times (lib/clock.ts): set while rendering, as the day start is, so a
 * change of clock shows on everything drawn below at once. */
export function useClockSetting(): void {
  const settings = useSettings().data as { clock?: unknown } | undefined
  setClock(settings?.clock)
}

function Root() {
  useServerEvents()
  useDayStart()
  useClockSetting()
  const status = useStatus()
  const terms = useTerms()
  const today = useToday()
  if (status.isError) return <Notice>Can't reach fridayd. Is it running?</Notice>
  if (status.data && !status.data.ready) return <Notice>Friday isn't set up yet: run `fridayd init`.</Notice>
  // Friday's terms come first, for everyone (C71): nothing else shows until they're accepted.
  if (terms.isPending) return <Notice>{null}</Notice>
  if (terms.data?.needed) return <TermsGate terms={terms.data} />
  return (
    <ShellProvider today={today}>
      <Shell />
    </ShellProvider>
  )
}

/** The planning date, which starts at `day_start`, as the server counts it. Asked again every few minutes and when
 * the window comes back: read only when the calendar was, a Friday left open overnight stayed on yesterday past
 * day_start until something changed (audit, 12 Nov). */
export function useToday(): string {
  const [today, setToday] = useState(() => fromMin(nowMin()).slice(0, 10))
  const calendar = useCalendar(today, 1).data
  const client = useQueryClient()
  useEffect(() => {
    if (calendar && calendar.today !== today) setToday(calendar.today)
  }, [calendar, today])
  useEffect(() => {
    const ask = () => void client.invalidateQueries({ queryKey: ["calendar", today, 1], exact: true })
    const back = () => document.visibilityState === "visible" && ask()
    const every = window.setInterval(ask, TODAY_EVERY)
    document.addEventListener("visibilitychange", back)
    return () => (window.clearInterval(every), document.removeEventListener("visibilitychange", back))
  }, [client, today])
  return today
}

export const TODAY_EVERY = 5 * 60_000

function Notice({ children }: { children: React.ReactNode }) {
  return <main style={{ display: "grid", placeItems: "center", height: "100vh", color: "var(--color-neutral-400)" }}>{children}</main>
}
