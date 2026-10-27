import { QueryClient } from "@tanstack/react-query"
import { describe, expect, it } from "vitest"
import type { Item } from "@/api/client"
import { eventUnder } from "./useDrop"

const event = (id: number, title: string, start: string, end: string, more: Partial<Item> = {}) => ({ id, title, start, end, when: "fixed", left_out: null, holds: null, event_kind: "other", gives_way_to: null, ...more }) as unknown as Item

describe("the event a task was pinned over", () => {
  const client = new QueryClient()
  client.setQueryData(["plan", "2026-10-27T00:00", "2026-11-03T12:00"], {
    fixed: [
      event(1509, "A4dd", "2026-10-27T21:00", "2026-10-27T23:00"),
      event(2, "Room booking", "2026-10-28T10:00", "2026-10-28T11:00", { left_out: "calendar" }),
      event(3, "Your time", "2026-10-28T14:00", "2026-10-28T15:00", { event_kind: "shove" }),
      event(4, "Gym", "2026-10-28T18:00", "2026-10-28T19:00", { gives_way_to: "Essay" }),
      event(5, "Study block", "2026-10-29T20:00", "2026-10-29T22:00", { holds: { id: 7, title: "Essay" } }),
    ],
  })

  it("is one that keeps work off its time (27 Oct: the design doc over A4dd)", () => {
    expect(eventUnder(client, "2026-10-27T21:30", "2026-10-27T22:30")?.id).toBe(1509)
  })

  it("isn't one that only touches it, keeps nothing off, is shoved time, is skipped for work, or is already for a task", () => {
    expect(eventUnder(client, "2026-10-27T23:00", "2026-10-28T00:00")).toBeNull()
    expect(eventUnder(client, "2026-10-28T10:00", "2026-10-28T11:00")).toBeNull()
    expect(eventUnder(client, "2026-10-28T14:00", "2026-10-28T15:00")).toBeNull()
    expect(eventUnder(client, "2026-10-28T18:00", "2026-10-28T19:00")).toBeNull()
    expect(eventUnder(client, "2026-10-29T20:00", "2026-10-29T21:00")).toBeNull()
  })
})
