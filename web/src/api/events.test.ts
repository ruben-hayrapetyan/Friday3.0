import { QueryClient } from "@tanstack/react-query"
import { describe, expect, it } from "vitest"
import { GHOSTS, refreshFor, refreshMissed } from "./events"

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
})
