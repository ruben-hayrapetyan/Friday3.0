// @vitest-environment happy-dom
// Today, as the server counts it, moves on when day_start passes with Friday left open: it was read only with the
// calendar, so a window left open overnight stayed on yesterday until something changed (audit, 12 Nov).
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, renderHook, waitFor } from "@testing-library/react"
import type { ReactNode } from "react"
import { afterEach, expect, it, vi } from "vitest"
import { TODAY_EVERY, useToday } from "./App"

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

it("moves on to the next day without anything else changing", async () => {
  let serverToday = "2026-11-12"
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ today: serverToday, days: [] }), { headers: { "content-type": "application/json" } })))
  vi.useFakeTimers({ shouldAdvanceTime: true })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>
  const { result } = renderHook(() => useToday(), { wrapper })
  await waitFor(() => expect(result.current).toBe("2026-11-12"))
  serverToday = "2026-11-13" // 4am came
  await act(async () => {
    await vi.advanceTimersByTimeAsync(TODAY_EVERY + 100)
  })
  await waitFor(() => expect(result.current).toBe("2026-11-13"))
})
