import { describe, expect, it } from "vitest"
import { categoryPaint, newEventTargets } from "./calendars"

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

describe("the category a new event wears before the server answers", () => {
  // The categories of 28 Oct, in order: the first whose pattern finds the title wins, without regard to case.
  const categories = [
    { color: "red", pattern: "prelim|quiz|exam\\b|\\bdue\\b" },
    { color: "blue", pattern: "\\b(lec|disc|lab)\\b|psych 1130" },
    { color: "green", pattern: "office hours|advising" },
    { color: "pink", pattern: "salsa|poker" },
  ]
  it("takes the first category whose pattern finds the title", () => {
    expect(categoryPaint("Math 1920 Quiz 4", categories)).toBe("red")
    expect(categoryPaint("PSYCH 1130 review", categories)).toBe("blue")
    expect(categoryPaint("Exam office hours", categories)).toBe("red") // listed first
    expect(categoryPaint("Salsa", categories)).toBe("pink")
  })
  it("has none when no pattern finds it, or a pattern can't be read here", () => {
    expect(categoryPaint("Bike Inspection", categories)).toBeNull()
    expect(categoryPaint("anything", [{ color: "red", pattern: "(?<" }, { color: "", pattern: "" }])).toBeNull()
  })
})
