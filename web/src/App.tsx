import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { useEffect, useState } from "react"
import { HashRouter } from "react-router"
import { useServerEvents } from "@/api/events"
import { Toasts } from "@/components/Toasts"
import { useCalendar, useStatus } from "@/hooks/queries"
import { nowMin } from "@/hooks/useClock"
import { fromMin } from "@/lib/time"
import { Shell } from "@/shell/Shell"
import { ShellProvider } from "@/shell/ShellContext"
import { LookProvider } from "@/theme/LookProvider"

const client = new QueryClient({ defaultOptions: { queries: { staleTime: 30_000, retry: 1 } } })

export default function App() {
  return (
    <QueryClientProvider client={client}>
      <LookProvider>
        <Toasts>
          <HashRouter>
            <Root />
          </HashRouter>
        </Toasts>
      </LookProvider>
    </QueryClientProvider>
  )
}

function Root() {
  useServerEvents()
  const status = useStatus()
  const today = useToday()
  if (status.isError) return <Notice>Can't reach fridayd. Is it running?</Notice>
  if (status.data && !status.data.ready) return <Notice>Friday isn't set up yet: run `fridayd init`.</Notice>
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
