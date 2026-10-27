import { describe, expect, it } from "vitest"
import { newEventTargets } from "./calendars"

// Your calendars on 27 Oct, in part: Gmail read through the Mac, Cornell through Google.
const google = [
  { id: "you@gmail.com", name: "you@gmail.com", writable: true, on: false, account: "you@gmail.com" },
  { id: "student@school.edu", name: "student@school.edu", writable: true, on: true, account: "student@school.edu" },
  { id: "family@group", name: "Family", writable: true, on: false, account: "you@gmail.com" },
  { id: "holidays@group", name: "Holidays in United States", writable: false, on: false },
]
const mac = [
  { id: "MAC-GMAIL", name: "you@gmail.com", writable: true, on: true, account: "Google" },
  { id: "MAC-FAMILY-G", name: "Family (Google)", writable: true, on: false, account: "Google" },
  { id: "MAC-HOME", name: "Home", writable: true, on: false, account: "iCloud" },
  { id: "MAC-BDAY", name: "Birthdays", writable: false, on: false },
]

describe("the calendars a new event can go to", () => {
  const targets = newEventTargets(google, mac)
  const byName = (name: string) => targets.filter((t) => t.name.startsWith(name))

  it("your Gmail calendar, read through the Mac, is offered once, through the Mac (27 Oct)", () => {
    expect(byName("you@gmail.com")).toEqual([expect.objectContaining({ id: "MAC-GMAIL", via: "mac" })])
  })

  it("one read through Google goes through Google", () => {
    expect(byName("student@school.edu")).toEqual([expect.objectContaining({ id: "student@school.edu", via: "google" })])
  })

  it("one on both and read through neither goes through Google, which needs no Mac app", () => {
    expect(byName("Family")).toEqual([expect.objectContaining({ id: "family@group", via: "google" })])
  })

  it("a Mac-only calendar is offered, and none that can't be changed", () => {
    expect(byName("Home")).toEqual([expect.objectContaining({ id: "MAC-HOME", via: "mac" })])
    expect(targets.some((t) => t.name.startsWith("Holidays") || t.name === "Birthdays")).toBe(false)
  })
})
