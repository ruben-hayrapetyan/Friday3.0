import { QueryClient } from "@tanstack/react-query"
import { describe, expect, it, vi } from "vitest"
import { GHOSTS, refresh, refreshFor, refreshMissed } from "./events"

describe("server events", () => {
  it("refresh what each changes", () => {
    expect(refreshFor("items.changed")).toEqual(["*"])
    expect(refreshFor("plan.changed")).toEqual(expect.arrayContaining(["plan", "now", "items", "status"]))
    expect(refreshFor("plan.provisional")).toEqual(["plan"])
    expect(refreshFor("updates.changed")).toEqual(["updates"])
  })

  it("the first time the stream opens, what was asked before it may have missed an event and is asked again", () => {
    const client = new QueryClient()
    client.setQueryData(["updates"], { popup: false }, { updatedAt: 1000 }) // asked at launch, before the check
    client.setQueryData(["plan"], { blocks: [] }, { updatedAt: 3000 }) // asked after the stream opened
    client.setQueryData(GHOSTS, [], { updatedAt: 1000 }) // put there by hand, never refetched
    refreshMissed(client, false, 2000)
    expect(client.getQueryState(["updates"])?.isInvalidated).toBe(true)
    expect(client.getQueryState(["plan"])?.isInvalidated).toBe(false)
    expect(client.getQueryState(GHOSTS)?.isInvalidated).toBe(false)
  })

  it("back after dropping, everything is asked again", () => {
    const client = new QueryClient()
    client.setQueryData(["plan"], { blocks: [] }, { updatedAt: 3000 })
    refreshMissed(client, true, 2000)
    expect(client.getQueryState(["plan"])?.isInvalidated).toBe(true)
  })

  it("a command you click often refreshes the work it changed, not settings, rules or terms (12 Nov)", () => {
    const work = refreshFor("items.changed", "suggestion_accept")
    expect(work).toEqual(expect.arrayContaining(["inbox", "items", "status", "to_review"]))
    expect(work).not.toContain("settings")
    expect(work).not.toContain("rules")
    expect(work).not.toContain("terms")
    expect(refreshFor("items.changed", "meal_start")).toContain("meals")
    expect(refreshFor("items.changed", "sleep_mark")).toContain("sleep")
    // any other command, or none named (an older server): everything, as before
    expect(refreshFor("items.changed", "rule_add")).toEqual(["*"])
    expect(refreshFor("items.changed")).toEqual(["*"])
  })

  it("events close together refresh once, together", async () => {
    vi.useFakeTimers()
    try {
      const client = new QueryClient()
      for (const key of ["inbox", "plan", "settings"]) client.setQueryData([key], {}, { updatedAt: 1000 })
      refresh(client, "items.changed", "suggestion_accept")
      refresh(client, "plan.changed")
      expect(client.getQueryState(["inbox"])?.isInvalidated).toBe(false) // gathered for a moment first
      await vi.advanceTimersByTimeAsync(200)
      expect(client.getQueryState(["inbox"])?.isInvalidated).toBe(true)
      expect(client.getQueryState(["plan"])?.isInvalidated).toBe(true)
      expect(client.getQueryState(["settings"])?.isInvalidated).toBe(false)
    } finally {
      vi.useRealTimers()
    }
  })
})
