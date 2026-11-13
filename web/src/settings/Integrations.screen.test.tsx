// Settings → Integrations, the gallery (C96): a search over every box, what's connected on top, then each category; a
// box opens a popup in the middle of the window, closed by its ×, Escape or a click beside it. Here: the boxes that
// aren't connected by a token (TokenIntegration.screen.test.tsx has those): calendar links and the services that
// publish one, the plan on an iPhone, Google's own connection and Gmail, mail by app password, the AI, Ask the AI, a
// syllabus upload, and the how-to boxes. Alex's sample reads Google and Gmail through the demo's stand-ins; a link
// added here is a calendar served on this machine, and nothing reaches a real service.

import { screen, waitFor, within } from "@testing-library/react"
import { afterAll, describe, expect, it, vi } from "vitest"
import { friday, openFriday, waitForSent } from "@/test/friday"
import { standIn } from "./screen.test.helpers"

const ICS = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Friday tests//EN", "BEGIN:VEVENT", "UID:hw1@test", "DTSTAMP:20261101T000000Z", "DTSTART:20261120T170000Z", "DTEND:20261120T180000Z", "SUMMARY:Essay 2 due", "END:VEVENT", "END:VCALENDAR", ""].join("\r\n")
const calendar = await standIn((req) => (req.url?.endsWith(".ics") ? { text: ICS, type: "text/calendar" } : undefined))
afterAll(() => calendar.close())

type Source = { id: number; kind: string; name: string; enabled: boolean; service?: string | null }
const sources = async () => ((await friday.q<{ sources: Source[] }>("inbox")).sources ?? []).filter((s) => s.enabled)

/** The gallery, and the popup of the box whose button is called `box` ("Gmail, Connected") once it's opened. */
async function openBox(box: string) {
  const app = await openFriday("/settings/integrations")
  await app.user.click(await screen.findByRole("button", { name: box }))
  const dialog = await screen.findByRole("dialog", { name: box.split(", ")[0] })
  return { ...app, dialog }
}

describe("the integrations gallery", () => {
  it("puts what's connected on top, then each category, with what each box brings", async () => {
    await openFriday("/settings/integrations")
    const connected = await screen.findByRole("region", { name: "Connected" })
    // Alex reads Google Calendar and Gmail through Google, and the AI is ready
    expect(within(connected).getByRole("button", { name: "Google Calendar, 7 connected" })).toBeTruthy()
    expect(within(connected).getByRole("button", { name: "Gmail, Connected" })).toBeTruthy()
    expect(within(connected).getByRole("button", { name: "AI, Ready" })).toBeTruthy()
    for (const category of ["Calendars", "To-do apps", "School", "Work schedules", "Mail", "Messages", "AI", "Automation"]) {
      expect(screen.getByRole("region", { name: category })).toBeTruthy()
    }
    const todo = screen.getByRole("region", { name: "To-do apps" })
    expect(within(todo).getByRole("button", { name: "Todoist" }).textContent).toContain("Your Todoist to-dos planned into your week")
    expect(within(todo).queryByRole("button", { name: /Google Calendar/ })).toBeNull()
    // a backup to download, and where the assistants' tokens went
    expect(screen.getByRole("link", { name: "Download" }).getAttribute("href")).toBe("/api/backup")
    expect(screen.getAllByRole("link", { name: "Tokens" }).some((a) => a.getAttribute("href") === "#/settings/tokens")).toBe(true)
  })

  it("finds boxes by name or by what people call them, and says when nothing matches", async () => {
    const { user } = await openFriday("/settings/integrations")
    const search = await screen.findByRole("searchbox", { name: "Search integrations" })
    await user.type(search, "kanban")
    expect(screen.getByRole("button", { name: "Trello" })).toBeTruthy()
    expect(screen.queryByRole("button", { name: "Todoist" })).toBeNull()
    await user.clear(search)
    await user.type(search, "imap")
    expect(screen.getByRole("button", { name: "Other mail (IMAP)" })).toBeTruthy()
    expect(screen.queryByRole("region", { name: "Calendars" })).toBeNull()
    await user.clear(search)
    await user.type(search, "fax machine")
    expect(screen.getByText("Nothing called “fax machine” yet.")).toBeTruthy()
    expect(screen.queryAllByRole("region")).toHaveLength(0)
    await user.clear(search)
    expect(await screen.findByRole("region", { name: "Connected" })).toBeTruthy()
  })

  it("opens a box as a popup that its ×, Escape or a click beside it closes", async () => {
    const { user, dialog } = await openBox("Todoist")
    expect(within(dialog).getByText("To-do apps")).toBeTruthy()
    expect(within(dialog).getByText("Your Todoist to-dos planned into your week; done goes both ways.")).toBeTruthy()
    await user.click(within(dialog).getByRole("button", { name: "Close" }))
    expect(screen.queryByRole("dialog")).toBeNull()

    await user.click(screen.getByRole("button", { name: "Notion" }))
    expect(screen.getByRole("dialog", { name: "Notion" })).toBeTruthy()
    await user.keyboard("{Escape}")
    expect(screen.queryByRole("dialog")).toBeNull()

    await user.click(screen.getByRole("button", { name: "Asana" }))
    const scrim = screen.getByRole("dialog", { name: "Asana" }).parentElement!.querySelector('[role="presentation"]')!
    await user.click(scrim)
    expect(screen.queryByRole("dialog")).toBeNull()
  })

  it("keeps Tab and Shift-Tab inside a box's popup, and Escape gives the focus back to the box", async () => {
    // the audit, 12 Nov: "integration panel has no focus trap"
    const { user, dialog } = await openBox("Todoist")
    const box = screen.getByRole("button", { name: "Todoist" })
    expect(dialog.contains(document.activeElement)).toBe(true)
    for (let i = 0; i < 25; i++) {
      await user.tab()
      expect(dialog.contains(document.activeElement)).toBe(true)
    }
    for (let i = 0; i < 25; i++) {
      await user.tab({ shift: true })
      expect(dialog.contains(document.activeElement)).toBe(true)
    }
    await user.keyboard("{Escape}")
    expect(screen.queryByRole("dialog")).toBeNull()
    expect(document.activeElement).toBe(box)

    // a box that's connected, closed by its ×
    await user.click(screen.getByRole("button", { name: "Gmail, Connected" }))
    const gmail = screen.getByRole("dialog", { name: "Gmail" })
    await user.tab({ shift: true })
    expect(gmail.contains(document.activeElement)).toBe(true)
    await user.click(within(gmail).getByRole("button", { name: "Close" }))
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Gmail, Connected" }))
  })

  it("says what a connected box is, in its popup's heading", async () => {
    const { dialog } = await openBox("Google Calendar, 7 connected")
    expect(within(dialog).getByText("Calendars · 7 connected")).toBeTruthy()
  })
})

describe("boxes with nothing to connect", () => {
  it("Shortcuts & Siri says how, with the links Friday answers to", async () => {
    const { dialog } = await openBox("Shortcuts & Siri")
    expect(within(dialog).getByText(/Open the Shortcuts app on this Mac/)).toBeTruthy()
    expect(within(dialog).getByText("friday://open?page=inbox")).toBeTruthy()
    expect(within(dialog).getByText("adds a to-do, read the way the add box reads it")).toBeTruthy()
    expect(within(dialog).getByText(/These links work while Friday's Mac app is installed/)).toBeTruthy()
  })

  it("Homebase sends you to the Mac's calendars, whose box opens in its place", async () => {
    const { user, dialog } = await openBox("Homebase")
    expect(within(dialog).getByText(/Homebase puts shifts in your phone's calendar/)).toBeTruthy()
    expect(within(dialog).getByRole("link", { name: "Homebase's own help on this" }).getAttribute("href")).toContain("joinhomebase.com")
    await user.click(within(dialog).getByRole("button", { name: "Calendars on this Mac" }))
    const mac = screen.getByRole("dialog", { name: "Calendars on this Mac" })
    // in a browser, not the Mac app: how the Mac's calendars come in, and a calendar's private link instead
    expect(within(mac).getByText("Your calendars")).toBeTruthy()
    expect(within(mac).getByRole("link", { name: /Find your Google calendar's private link/ })).toBeTruthy()
  })

  it("Homebase's other button opens Settings → Calendars", async () => {
    const { user, dialog } = await openBox("Homebase")
    await user.click(within(dialog).getByRole("button", { name: "Choose which calendars Friday reads" }))
    await waitFor(() => expect(window.location.hash).toBe("#/settings/calendars"))
  })
})

describe("your plan on your iPhone", () => {
  it("is switched on in its box, and says it needs the Mac app", async () => {
    const { user, dialog, client } = await openBox("Your plan on your iPhone")
    expect(within(dialog).getByText("This needs Friday's Mac app open, with Calendars on this Mac allowed.")).toBeTruthy()
    const toggle = within(dialog).getByRole("switch", { name: "Show my plan in Calendar" })
    expect(toggle.getAttribute("aria-checked")).toBe("false")
    await user.click(toggle)
    expect((await waitForSent("settings_set")).body).toEqual({ key: "mac_plan", value: true })
    await screen.findByText("Saved")
    await client.invalidateQueries() // as the server's events would
    await waitFor(() => expect(within(dialog).getByRole("switch", { name: "Show my plan in Calendar" }).getAttribute("aria-checked")).toBe("true"))
    await user.click(within(dialog).getByRole("button", { name: "Close" }))
    expect(await screen.findByRole("button", { name: "Your plan on your iPhone, On" })).toBeTruthy()
  })
})

describe("calendar links", () => {
  it("adds a course feed by its link, named after its site, and removes it", async () => {
    const { user, dialog } = await openBox("Calendar links")
    const link = within(dialog).getByRole("textbox", { name: "Calendar link" })
    const add = within(dialog).getByRole("button", { name: "Add feed" })
    await user.type(link, "not a link")
    expect((add as HTMLButtonElement).disabled).toBe(true)
    await user.clear(link)
    await user.type(link, `${calendar.url}/course.ics`)
    await user.click(add)
    expect((await waitForSent("source_add")).body).toEqual({ kind: "ics", name: "127", url: `${calendar.url}/course.ics`, trusted: false })
    await waitFor(() => expect((link as HTMLInputElement).value).toBe(""))
    const row = await within(dialog).findByText("127")
    const added = (await sources()).find((s) => s.kind === "ics" && s.name === "127")!
    expect(added.service ?? null).toBeNull()
    await user.click(within(row.closest(".fr-row") as HTMLElement).getByRole("button", { name: "Remove" }))
    expect((await waitForSent("source_remove")).body).toEqual({ id: added.id, forget: true })
    await waitFor(async () => expect((await sources()).some((s) => s.id === added.id)).toBe(false))
  })

  it("reads a webcal:// link as the same address over https, and adds one removed before again", async () => {
    const { user, dialog } = await openBox("Calendar links")
    const here = calendar.url.slice("http://".length)
    await user.type(within(dialog).getByRole("textbox", { name: "Calendar link" }), `webcal://${here}/course.ics`)
    await user.click(within(dialog).getByRole("button", { name: "Add feed" }))
    expect((await waitForSent("source_add")).body).toMatchObject({ name: "127", url: `https://${here}/course.ics` })
    await waitFor(async () => expect((await sources()).some((s) => s.kind === "ics" && s.name === "127")).toBe(true))
  })
})

describe("a service that publishes a calendar link (Blackboard)", () => {
  it("shows its steps, takes only a link, and lists what it added with a way to remove it", async () => {
    const { user, dialog } = await openBox("Blackboard")
    expect(within(dialog).getByText(/In Blackboard, open Calendar from the menu on the left/)).toBeTruthy()
    expect(within(dialog).getByRole("link", { name: "Blackboard's own help on this" }).getAttribute("href")).toContain("anthology.com")
    expect(within(dialog).getByText(/Its due dates, assignments and exams come to your Inbox/)).toBeTruthy()
    const box = within(dialog).getByLabelText("Blackboard's calendar link")
    const add = within(dialog).getByRole("button", { name: "Add" })
    await user.type(box, "blackboard calendar")
    expect((add as HTMLButtonElement).disabled).toBe(true)
    await user.clear(box)
    await user.type(box, `${calendar.url}/blackboard.ics{Enter}`)
    expect((await waitForSent("source_add")).body).toEqual({ name: "Blackboard", url: `${calendar.url}/blackboard.ics`, service: "blackboard" })
    // its row, and the box asks for another
    expect(await within(dialog).findByText(/^Blackboard: /)).toBeTruthy()
    expect(within(dialog).getByLabelText("Another Blackboard link")).toBeTruthy()
    await user.click(within(dialog).getByRole("button", { name: "Close" }))
    expect(await screen.findByRole("button", { name: "Blackboard, Connected" })).toBeTruthy()
  })

  it("names a second link after the first, and removes one", async () => {
    const { user, dialog } = await openBox("Blackboard, Connected")
    await user.type(within(dialog).getByLabelText("Another Blackboard link"), `webcal://${calendar.url.slice(7)}/second.ics`)
    await user.click(within(dialog).getByRole("button", { name: "Add" }))
    expect((await waitForSent("source_add")).body).toEqual({ name: "Blackboard 2", url: `https://${calendar.url.slice(7)}/second.ics`, service: "blackboard" })
    await within(dialog).findByText(/^Blackboard 2: /)
    const removes = within(dialog).getAllByRole("button", { name: "Remove" })
    expect(removes).toHaveLength(2)
    await user.click(removes[1])
    const removed = (await waitForSent("source_remove")).body as { id: number }
    await waitFor(async () => expect((await sources()).some((s) => s.id === removed.id)).toBe(false))
  })
})

describe("Google's own connection and Gmail", () => {
  it("shows the account, its calendars to read, publishing and Sync now", async () => {
    const { user, dialog } = await openBox("Google Calendar, 7 connected")
    const more = await within(dialog).findByRole("button", { name: "More: Gmail, and connecting to Google directly" })
    expect(more.getAttribute("aria-expanded")).toBe("true") // open: it's in use
    expect(within(dialog).getByText("Events become fixed time. Friday plans around them.")).toBeTruthy()
    expect(await within(dialog).findByText("Reads 7 of its 7 calendars. Its mail is read.")).toBeTruthy()
    // the demo's stand-in account can't be removed or signed in again
    expect(within(dialog).queryByRole("button", { name: /^Remove aj452/ })).toBeNull()
    const list = within(dialog).getByRole("button", { name: /^Calendars \d+ of \d+ read/ })
    await user.click(list)
    const canvas = within(dialog).getByRole("switch", { name: "Read Canvas" })
    expect(canvas.getAttribute("aria-checked")).toBe("true")
    await user.click(within(dialog).getByRole("switch", { name: "Canvas straight to the plan" }))
    expect((await waitForSent("calendar_set")).body).toEqual({ id: "canvas@g", trusted: true, mac: false })
    await user.click(within(dialog).getByRole("switch", { name: "Publish the plan" }))
    expect((await waitForSent("settings_set")).body).toMatchObject({ key: "gcal", value: { publish: true, read: ["primary"] } })
    await user.click(within(dialog).getAllByRole("button", { name: "Sync now" })[0])
    await waitForSent("sync_now")
    await user.click(more)
    expect(within(dialog).queryByText("Gmail through Google's connection")).toBeNull()
  })

  it("lists which mail the AI reads, saves the words and senders, and shows what came in", async () => {
    const { user, dialog } = await openBox("Google Calendar, 7 connected")
    expect(await within(dialog).findByText("Gmail through Google's connection")).toBeTruthy()
    expect(await within(dialog).findByText("Its mail is read")).toBeTruthy()
    const words = (await within(dialog).findByRole("textbox", { name: "Words" })) as HTMLInputElement
    expect(words.value.startsWith("due, deadline, exam")).toBe(true)
    await user.clear(words)
    await user.type(words, "due, prelim,  lab report ,{Enter}")
    expect((await waitForSent("settings_set")).body).toMatchObject({ key: "gmail", value: { keywords: ["due", "prelim", "lab report"] } })
    const senders = within(dialog).getByRole("textbox", { name: "Always read mail from" })
    await user.type(senders, "cornell.edu")
    await user.tab()
    expect((await waitForSent("settings_set")).body).toMatchObject({ key: "gmail", value: { sender_domains: ["cornell.edu"] } })
    // the mail it read lately, the skipped ones to read anyway
    expect(within(dialog).getByText(/^Recent mail · \d+ read, \d+ skipped/)).toBeTruthy()
    const skipped = within(dialog).getByText("Rocketry newsletter #7").closest(".fr-row") as HTMLElement
    expect(within(skipped).getByText(/Bulk mail, no keyword in its subject/)).toBeTruthy()
    await user.click(within(skipped).getByRole("button", { name: "Read it anyway" }))
    expect((await waitForSent("mail_retry")).body).toEqual({ id: 152 })
  })

  it("switches Gmail off and on", async () => {
    const { user, dialog, client } = await openBox("Google Calendar, 7 connected")
    const gmail = await within(dialog).findByRole("switch", { name: "Read my Gmail" })
    await user.click(gmail)
    expect((await waitForSent("settings_set")).body).toMatchObject({ key: "gmail", value: { enabled: false } })
    await screen.findByText("Gmail is off")
    await client.invalidateQueries()
    await waitFor(() => expect(within(dialog).getByRole("switch", { name: "Read my Gmail" }).getAttribute("aria-checked")).toBe("false"))
    expect(within(dialog).queryByRole("textbox", { name: "Words" })).toBeNull()
    await user.click(within(dialog).getByRole("switch", { name: "Read my Gmail" }))
    expect((await waitForSent("settings_set")).body).toMatchObject({ key: "gmail", value: { enabled: true } })
    await waitFor(async () => expect((await friday.q<{ gmail: { enabled: boolean } }>("settings")).gmail.enabled).toBe(true))
  })
})

describe("Gmail by app password", () => {
  it("asks for the address and the app password, and says the server's words when they're refused", async () => {
    const { user, dialog } = await openBox("Gmail, Connected")
    expect(within(dialog).getByRole("link", { name: "myaccount.google.com/apppasswords" }).getAttribute("href")).toBe("https://myaccount.google.com/apppasswords")
    const connect = within(dialog).getByRole("button", { name: "Connect" }) as HTMLButtonElement
    expect(connect.disabled).toBe(true)
    await user.type(within(dialog).getByRole("textbox", { name: "Gmail address" }), "alex@gmail.com")
    await user.type(within(dialog).getByLabelText("App password"), "hunter2")
    await user.click(connect)
    expect((await waitForSent("gmail_app_set")).body).toEqual({ address: "alex@gmail.com", password: "hunter2" })
    expect(await screen.findByText(/An app password is 16 letters/)).toBeTruthy()
    // kept in the boxes to correct
    expect((within(dialog).getByRole("textbox", { name: "Gmail address" }) as HTMLInputElement).value).toBe("alex@gmail.com")
  })
})

describe("mail by app password (C99)", () => {
  it("iCloud Mail says its steps and connects only with an address and a password", async () => {
    const { user, dialog } = await openBox("iCloud Mail")
    expect(within(dialog).getByText(/App-Specific Passwords/)).toBeTruthy()
    expect(within(dialog).getByRole("link", { name: "iCloud Mail's own help on this" })).toBeTruthy()
    expect(within(dialog).queryByRole("textbox", { name: "IMAP server" })).toBeNull()
    const connect = within(dialog).getByRole("button", { name: "Connect" }) as HTMLButtonElement
    await user.type(within(dialog).getByRole("textbox", { name: "Address" }), "alex")
    await user.type(within(dialog).getByLabelText("App password"), "abcd")
    expect(connect.disabled).toBe(true) // not an address yet
  })

  it("other mail asks for its server too, and a server Friday can't use is refused in words", async () => {
    const { user, dialog } = await openBox("Other mail (IMAP)")
    const connect = within(dialog).getByRole("button", { name: "Connect" }) as HTMLButtonElement
    await user.type(within(dialog).getByRole("textbox", { name: "Address" }), "alex@example.edu")
    await user.type(within(dialog).getByLabelText("App password"), "secret-password")
    expect(connect.disabled).toBe(true)
    await user.type(within(dialog).getByRole("textbox", { name: "IMAP server" }), "127.0.0.1")
    await user.click(connect)
    expect((await waitForSent("mail_app_set")).body).toEqual({ provider: "other", address: "alex@example.edu", password: "secret-password", host: "127.0.0.1" })
    expect(await screen.findByText(/The IMAP server's name, like imap.example.com/)).toBeTruthy()
    expect(await friday.q("mail_app_accounts")).toEqual([])
  })
})

describe("the AI", () => {
  it("says it's ready, sets the day's limit, and checks each model works", async () => {
    const { user, dialog } = await openBox("AI, Ready")
    expect(await within(dialog).findByText("Friday reads with Claude.")).toBeTruthy()
    const which = within(dialog).getByRole("radiogroup", { name: "Which AI" })
    expect(within(which).getByRole("radio", { name: /^Claude/ }).getAttribute("aria-checked")).toBe("true")
    expect(within(dialog).getByText("50 reads")).toBeTruthy()
    const { fireEvent } = await import("@testing-library/react")
    fireEvent.change(within(dialog).getByRole("slider", { name: "Daily reads" }), { target: { value: "80" } })
    fireEvent.pointerUp(within(dialog).getByRole("slider", { name: "Daily reads" }))
    expect((await waitForSent("settings_set")).body).toEqual({ key: "llm", value: { daily_calls: 80 } })
    await user.click(within(dialog).getByRole("button", { name: "Check it works" }))
    const checks = await within(dialog).findAllByText(/: works$/)
    expect(checks.length).toBe(2)
    expect(within(dialog).getByText("(reads mail and documents)")).toBeTruthy()
  })

  it("Ask the AI changes calendar events without asking, once you say so", async () => {
    const { user, dialog, client } = await openBox("Ask the AI")
    expect(within(dialog).getByText("Ask Claude")).toBeTruthy()
    expect(within(dialog).getByText(/Off: Claude asks before every change/)).toBeTruthy()
    await user.click(within(dialog).getByRole("switch", { name: "Change calendar events without asking" }))
    expect((await waitForSent("settings_set")).body).toEqual({ key: "claude", value: { events_without_asking: true } })
    await screen.findByText("Saved")
    await client.invalidateQueries()
    expect(await within(dialog).findByText(/Event changes apply as soon as Claude answers, with Undo/)).toBeTruthy()
  })
})

describe("a syllabus upload", () => {
  it("sends a page's text to be read, and lists what was uploaded", async () => {
    const { user, dialog, client } = await openBox("Syllabus upload")
    expect(within(dialog).getByRole("button", { name: "Upload PDF or page" })).toBeTruthy()
    const input = dialog.querySelector('input[type="file"]') as HTMLInputElement
    const click = vi.spyOn(input, "click")
    await user.click(within(dialog).getByRole("button", { name: "Upload PDF or page" }))
    expect(click).toHaveBeenCalled()
    const file = new File(["CHEM 2090 syllabus\nProblem set 9 due 20 November"], "chem-syllabus.txt", { type: "text/plain" })
    await user.upload(input, file)
    expect((await waitForSent("document_add")).body).toEqual({ name: "chem-syllabus.txt", media_type: "text/plain", content: "CHEM 2090 syllabus\nProblem set 9 due 20 November" })
    await waitFor(async () => expect(await friday.q<unknown[]>("documents")).toHaveLength(1))
    await client.invalidateQueries()
    expect(await within(dialog).findByText("Uploaded (1)")).toBeTruthy()
    expect(within(dialog).getByText("chem-syllabus.txt")).toBeTruthy()
  })

  it("sends a saved web page as HTML", async () => {
    const { user, dialog } = await openBox("Syllabus upload")
    const input = dialog.querySelector('input[type="file"]') as HTMLInputElement
    await user.upload(input, new File(["<h1>MATH 1910</h1>"], "course.html", { type: "" }))
    expect((await waitForSent("document_add")).body).toMatchObject({ name: "course.html", media_type: "text/html", content: "<h1>MATH 1910</h1>" })
  })
})
