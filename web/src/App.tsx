import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { useEffect, useState } from "react"
import { HashRouter } from "react-router"
import { useServerEvents } from "@/api/events"
import { ErrorBoundary } from "@/components/ErrorBoundary"
import { Toasts } from "@/components/Toasts"
import { useCalendar, useStatus } from "@/hooks/queries"
import { nowMin } from "@/hooks/useClock"
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

function Root() {
  useServerEvents()
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

/** The planning date, which starts at `day_start`, as the server counts it. */
function useToday(): string {
  const [today, setToday] = useState(() => fromMin(nowMin()).slice(0, 10))
  const calendar = useCalendar(today, 1).data
  useEffect(() => {
    if (calendar && calendar.today !== today) setToday(calendar.today)
  }, [calendar, today])
  return today
}

function Notice({ children }: { children: React.ReactNode }) {
  return <main style={{ display: "grid", placeItems: "center", height: "100vh", color: "var(--color-neutral-400)" }}>{children}</main>
}
