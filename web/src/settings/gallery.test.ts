import { describe, expect, it } from "vitest"
import { CATALOG, CATEGORIES, folded, grouped, search } from "./gallery"

const names = (list: { name: string }[]) => list.map((e) => e.name)

describe("the integrations gallery's catalog", () => {
  it("has every entry ready to show: a unique id, a name, one line, a category, an icon and colour", () => {
    expect(new Set(CATALOG.map((e) => e.id)).size).toBe(CATALOG.length)
    for (const e of CATALOG) {
      expect(e.name.length).toBeGreaterThan(1)
      expect(e.line.length).toBeGreaterThan(10)
      expect(e.line.length).toBeLessThan(80) // one line in a box
      expect(CATEGORIES).toContain(e.category)
      expect(e.icon).toMatch(/^[a-z-]+$/)
      expect(e.hue).toMatch(/^#[0-9a-f]{6}$/i)
    }
  })
  it("says, for each one connected by token, where the token is and how to get it", () => {
    for (const e of CATALOG.filter((x) => x.token && x.id !== "trello")) {
      expect(e.token!.page).toMatch(/^https:\/\//)
      expect(e.token!.steps.length).toBeGreaterThanOrEqual(2)
    }
    expect(CATALOG.find((e) => e.id === "todoist")?.token?.page).toContain("todoist.com")
  })
  it("walks Notion through a personal access token, saying an integration's secret works too (C101)", () => {
    const notion = CATALOG.find((e) => e.id === "notion")!
    expect(notion.category).toBe("To-do apps")
    expect(notion.token!.page).toBe("https://www.notion.so/developers/tokens")
    expect(notion.token!.steps.join(" ")).toContain("New token")
    expect(notion.token!.note).toContain("Connections")
    expect(names(search(CATALOG, "notion"))).toEqual(["Notion"])
  })
  it("has Trello's Allow page from the server, which has Friday's app key (C102)", () => {
    const trello = CATALOG.find((e) => e.id === "trello")!
    expect(trello.token!.page).toBe("")
    expect(trello.token!.steps.join(" ")).toContain("Allow")
    expect(trello.token!.note).toContain("cards you're on")
    expect(names(search(CATALOG, "kanban"))).toEqual(["Trello"])
  })
  it("has Asana's own token page and says only your tasks come in (C103)", () => {
    const asana = CATALOG.find((e) => e.id === "asana")!
    expect(asana.token!.page).toBe("https://app.asana.com/0/my-apps")
    expect(asana.token!.note).toContain("assigned to you")
    expect(names(search(CATALOG, "my tasks"))).toEqual(["Asana"])
  })
  it("has Linear's key page and says done moves an issue to Done (C104)", () => {
    const linear = CATALOG.find((e) => e.id === "linear")!
    expect(linear.token!.page).toBe("https://linear.app/settings/account/security")
    expect(linear.token!.note).toContain("Done state")
    expect(names(search(CATALOG, "issues"))).toContain("Linear")
  })
  it("asks Jira for your site and email beside the token (C105)", () => {
    const jira = CATALOG.find((e) => e.id === "jira")!
    expect(jira.token!.fields!.map((f) => f.key)).toEqual(["site", "email"])
    expect(jira.token!.note).toContain("Jira Cloud only")
    expect(names(search(CATALOG, "atlassian"))).toContain("Jira")
  })
  it("walks GitHub through a read-only fine-grained token and says it only reads (C106)", () => {
    const github = CATALOG.find((e) => e.id === "github")!
    expect(github.token!.steps.join(" ")).toContain("Read-only")
    expect(github.token!.note).toContain("only reads")
    expect(names(search(CATALOG, "pull requests"))).toEqual(["GitHub"])
  })
  it("has the Canvas API under School, asking your school's address and saying what happens to the feed (C107)", () => {
    const canvas = CATALOG.find((e) => e.id === "canvas")!
    expect(canvas.category).toBe("School")
    expect(canvas.token!.fields!.map((f) => f.key)).toEqual(["site"])
    expect(canvas.token!.note).toContain("calendar feed keeps bringing only its events")
    expect(names(search(CATALOG, "instructure"))).toEqual(["Canvas"])
  })
  it("has Things as a to-do app on this Mac, saying Someday stays out (C108)", () => {
    const things = CATALOG.find((e) => e.id === "things")!
    expect(things.token).toBeUndefined()
    expect(things.onMac!.steps.join(" ")).toContain("Someday stays out")
    expect(names(search(CATALOG, "things 3"))).toEqual(["Things"])
  })
  it("connects Microsoft To Do by signing in, not a token (C109)", () => {
    const todo = CATALOG.find((e) => e.id === "microsoft_todo")!
    expect(todo.token).toBeUndefined()
    expect(todo.signIn!.steps.join(" ")).toContain("Sign in with Microsoft")
    expect(names(search(CATALOG, "wunderlist"))).toEqual(["Microsoft To Do"])
  })
  it("has Google Tasks riding the Google sign-in (C110)", () => {
    const tasks = CATALOG.find((e) => e.id === "google_tasks")!
    expect(tasks.token).toBeUndefined()
    expect(tasks.signIn!.note).toContain("same Google sign-in")
    expect(names(search(CATALOG, "google tasks"))).toEqual(["Google Tasks"])
  })
  it("connects TickTick by signing in, saying it lasts about six months (C111)", () => {
    const tick = CATALOG.find((e) => e.id === "ticktick")!
    expect(tick.signIn!.note).toContain("six months")
    expect(names(search(CATALOG, "tick"))).toContain("TickTick")
  })
  it("has Apple Reminders as a to-do app with no token, said step by step (C100)", () => {
    const reminders = CATALOG.find((e) => e.id === "reminders")!
    expect(reminders.category).toBe("To-do apps")
    expect(reminders.token).toBeUndefined()
    expect(reminders.onMac!.steps.join(" ")).toContain("Allow")
    expect(names(search(CATALOG, "apple reminders"))).toEqual(["Apple Reminders"])
  })
})

describe("searching the gallery", () => {
  it("finds by name, from the start of any word, whatever the case", () => {
    expect(names(search(CATALOG, "todo"))[0]).toBe("Todoist")
    expect(names(search(CATALOG, "GMAIL"))).toEqual(["Gmail"])
    expect(names(search(CATALOG, "upload"))).toContain("Syllabus upload")
  })
  it("finds by the other names people use", () => {
    expect(names(search(CATALOG, "claude"))).toEqual(expect.arrayContaining(["AI", "Ask the AI"]))
    expect(names(search(CATALOG, "canvas"))).toEqual(expect.arrayContaining(["Calendar links", "Syllabus upload"]))
    expect(names(search(CATALOG, "icloud"))).toContain("Calendars on this Mac")
  })
  it("needs every word to match, and puts a name that starts with them first", () => {
    expect(names(search(CATALOG, "google calendar"))[0]).toBe("Google Calendar")
    expect(search(CATALOG, "gmail todoist")).toEqual([])
  })
  it("matches the start of words, not the middle", () => {
    expect(names(search(CATALOG, "ist"))).not.toContain("Todoist")
  })
  it("shows everything for an empty search, nothing for nonsense, and never breaks on punctuation", () => {
    expect(search(CATALOG, "  ")).toHaveLength(CATALOG.length)
    expect(search(CATALOG, "zzqx")).toEqual([])
    expect(search(CATALOG, "(.*")).toHaveLength(CATALOG.length) // punctuation alone is no search, and no pattern
    expect(search(CATALOG, "todo(")).toEqual(search(CATALOG, "todo"))
  })
  it("ignores accents", () => {
    expect(folded("Calendrié")).toBe("calendrie")
  })
})

describe("the gallery's layout", () => {
  it("puts what you've connected first, then each category in order, with none twice and no empty sections", () => {
    const { connected, sections } = grouped(CATALOG, new Set(["todoist", "gmail"]))
    expect(names(connected)).toEqual(["Gmail", "Todoist"])
    const shown = sections.flatMap(([, list]) => list)
    expect(shown.find((e) => e.id === "todoist")).toBeUndefined()
    expect(shown.length + connected.length).toBe(CATALOG.length)
    expect(sections.map(([c]) => c)).toEqual(CATEGORIES.filter((c) => sections.some(([s]) => s === c)))
    expect(sections.every(([, list]) => list.length > 0)).toBe(true)
  })
})

describe("the boxes for services connected by their calendar link (C96)", () => {
  const links = CATALOG.filter((e) => e.link)
  it("are the eight you chose, each with its own help page and steps, saying what Friday does with it", () => {
    expect(links.map((e) => e.id).sort()).toEqual(["7shifts", "blackboard", "brightspace", "deputy", "moodle", "schoology", "sling", "wheniwork"])
    for (const e of links) {
      expect(e.link!.help).toMatch(/^https:\/\//)
      expect(e.link!.steps.length).toBeGreaterThanOrEqual(3)
      expect(e.link!.reads.length).toBeGreaterThan(20)
    }
  })
  it("puts school systems under School and shift apps under Work schedules", () => {
    expect(CATALOG.filter((e) => e.category === "Work schedules").map((e) => e.id).sort()).toEqual(["7shifts", "deputy", "homebase", "sling", "wheniwork"])
    expect(["blackboard", "moodle", "brightspace", "schoology"].every((id) => CATALOG.find((e) => e.id === id)?.category === "School")).toBe(true)
  })
  it("says how Homebase reaches Friday, as it gives no link", () => {
    const homebase = CATALOG.find((e) => e.id === "homebase")!
    expect(homebase.link).toBeUndefined()
    expect(homebase.viaMac!.steps.join(" ")).toContain("Calendars on this Mac")
  })
  it("are found by the names people use", () => {
    expect(names(search(CATALOG, "d2l"))).toEqual(["Brightspace"])
    expect(names(search(CATALOG, "shifts"))).toEqual(expect.arrayContaining(["When I Work", "Deputy", "7shifts", "Sling", "Homebase"]))
    expect(names(search(CATALOG, "roster"))).toEqual(["Deputy"])
  })
})

describe("the boxes for mail by app password (C99)", () => {
  const mail = CATALOG.filter((e) => e.mail)
  it("are iCloud, Yahoo, Fastmail and other IMAP, under Mail, each with its steps", () => {
    expect(mail.map((e) => e.mail!.provider).sort()).toEqual(["fastmail", "icloud", "other", "yahoo"])
    expect(mail.every((e) => e.category === "Mail" && e.mail!.steps.length >= 3)).toBe(true)
    expect(mail.filter((e) => e.mail!.help).every((e) => e.mail!.help!.startsWith("https://"))).toBe(true)
  })
  it("have Outlook by Microsoft's sign-in, not an app password, which Microsoft refuses (C109)", () => {
    const outlook = CATALOG.find((e) => e.id === "outlook_mail")!
    expect(outlook.mail).toBeUndefined()
    expect(outlook.signIn!.note).toContain("Nothing is sent, moved, deleted or marked read")
    expect(names(search(CATALOG, "hotmail"))).toEqual(["Outlook"])
  })
  it("are found by the names people use", () => {
    expect(names(search(CATALOG, "me.com"))).toEqual(["iCloud Mail"])
    expect(names(search(CATALOG, "imap"))).toContain("Other mail (IMAP)")
  })
})
