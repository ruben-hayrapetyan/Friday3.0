// The boxes connected by a token, a sign-in, a script or the Mac app (C96–C130): Todoist's, Notion's, Jira's and
// Canvas's token forms, the sign-in boxes (Microsoft To Do, Outlook, Slack), Apple Reminders on the Mac, and the Google
// Tasks script; then a connected one's row: how new to-dos arrive, Sync now, Disconnect (keep or remove what it brought
// in), and Notion's lists. The services are stand-ins on this machine that the Friday under test is pointed at
// (FRIDAY_API_*), so a refused token is the server's own refusal, in its words; nothing reaches a real service.

import { fireEvent, screen, waitFor, within } from "@testing-library/react"
import { afterAll, afterEach, describe, expect, it, vi } from "vitest"
import { friday, openFriday, waitForSent } from "@/test/friday"
import { answer, refused, standIn } from "./screen.test.helpers"

type Connected = { id: number; kind: string; name: string; arrival: string; last_error: string | null; made: number; waiting: number; lists: boolean; last_sync: string | null }

const GOOD = "good-token"
const todoist = await standIn((req) => {
  if (req.headers.authorization !== `Bearer ${GOOD}`) return { status: 401, json: { error: "Unauthorized" } }
  if (req.url?.includes("/projects")) return { json: { results: [], next_cursor: null } }
  if (req.url?.includes("/tasks")) return { json: { results: [{ id: "t1", content: "Read chapter 4", due: { date: "2026-11-20" } }], next_cursor: null } }
  return undefined
})
const notion = await standIn((req) => {
  if (req.url === "/users/me") return { json: { type: "bot", bot: { workspace_name: "Alex's notes" } } }
  if (req.url === "/search")
    return {
      json: {
        has_more: false,
        results: [
          { object: "data_source", id: "ds-home", title: [{ plain_text: "Homework" }], properties: { Name: { type: "title" }, Done: { type: "checkbox" } } },
          { object: "data_source", id: "ds-team", title: [{ plain_text: "Team board" }], properties: { Name: { type: "title" }, Done: { type: "checkbox" }, Assignee: { type: "people" } } },
        ],
      },
    }
  if (req.url?.endsWith("/query")) return { json: { results: [], has_more: false } }
  return undefined
})
// the Friday under test reads these services here (src/friday/integrations/*.py)
process.env.FRIDAY_API_TODOIST = todoist.url
process.env.FRIDAY_API_NOTION = notion.url
afterAll(() => (todoist.close(), notion.close()))

// A sign-in page is never opened here, not even after a test has ended: each call is only noted.
const opened: unknown[][] = []
window.open = ((...args: unknown[]) => (opened.push(args), null)) as typeof window.open

const undo: (() => void)[] = []
afterEach(() => {
  while (undo.length) undo.pop()!()
  vi.restoreAllMocks()
})

const connected = () => friday.q<Connected[]>("integrations")

/** The gallery, and the popup of the box whose button is called `box`. */
async function openBox(box: string) {
  const app = await openFriday("/settings/integrations")
  await app.user.click(await screen.findByRole("button", { name: box }))
  const dialog = await screen.findByRole("dialog", { name: box.split(", ")[0] })
  return { ...app, dialog }
}

describe("a token form (Todoist)", () => {
  it("says the steps, links the token page, and connects only with a token", async () => {
    const { dialog } = await openBox("Todoist")
    expect(within(dialog).getByText(/Open Todoist's Settings → Integrations → Developer/)).toBeTruthy()
    expect(within(dialog).getByRole("link", { name: "Open Todoist's token page" }).getAttribute("href")).toBe("https://app.todoist.com/app/settings/integrations/developer")
    expect(within(dialog).getByLabelText("Todoist API token").getAttribute("type")).toBe("password")
    expect((within(dialog).getByRole("button", { name: "Connect" }) as HTMLButtonElement).disabled).toBe(true)
    expect(within(dialog).getByText(/Friday checks it with Todoist first/)).toBeTruthy()
  })

  it("says a refused token in Todoist's words and keeps it in the box to correct", async () => {
    const { user, dialog } = await openBox("Todoist")
    const box = within(dialog).getByLabelText("Todoist API token") as HTMLInputElement
    await user.type(box, "wrong-token{Enter}")
    expect((await waitForSent("integration_connect")).body).toEqual({ kind: "todoist", token: "wrong-token", fields: {} })
    expect(await screen.findByText("Todoist didn't accept the token: make a new one and paste it again")).toBeTruthy()
    expect(box.value).toBe("wrong-token")
    expect(await connected()).toEqual([])
  })

  it("connects with a good token, and the box turns into its settings", async () => {
    const { user, dialog } = await openBox("Todoist")
    await user.type(within(dialog).getByLabelText("Todoist API token"), GOOD)
    await user.click(within(dialog).getByRole("button", { name: "Connect" }))
    // an unlogged command (a token is never logged) says nothing more: the box turns connected
    expect(await within(dialog).findByText("Connected: reading it within the minute.")).toBeTruthy()
    const arrivals = within(dialog).getByRole("radiogroup", { name: "How new to-dos arrive" })
    expect(within(arrivals).getByRole("radio", { name: /^Review the first, then straight in/ }).getAttribute("aria-checked")).toBe("true")
    const [row] = await connected()
    expect(row).toMatchObject({ kind: "todoist", name: "Todoist", arrival: "inbox_first" })
    await user.click(within(dialog).getByRole("button", { name: "Close" }))
    expect(screen.getByRole("button", { name: "Todoist, Connected" })).toBeTruthy()
  })

  it("chooses how new to-dos arrive, and syncs now", async () => {
    const { user, dialog } = await openBox("Todoist, Connected")
    const [row] = await connected()
    await user.click(await within(dialog).findByRole("radio", { name: /^Always straight in/ }))
    expect((await waitForSent("integration_set")).body).toEqual({ id: row.id, arrival: "straight" })
    await waitFor(async () => expect((await connected())[0].arrival).toBe("straight"))
    await waitFor(() => expect(within(dialog).getByRole("radio", { name: /^Always straight in/ }).getAttribute("aria-checked")).toBe("true"))
    await user.click(within(dialog).getByRole("button", { name: "Sync now" }))
    await waitForSent("sync_now")
  })

  it("shows what it brought in and what waits in the Inbox, and a reading problem", async () => {
    const [row] = await connected()
    undo.push(answer("integrations", () => ({ json: [{ ...row, last_sync: "2026-11-11T09:00", made: 1, waiting: 2 }] })))
    const { user, dialog, unmount } = await openBox("Todoist, Connected")
    expect(await within(dialog).findByText(/^Read .*: 1 open to-do from it in your plan\.$/)).toBeTruthy()
    await user.click(within(dialog).getByRole("button", { name: "2 waiting in your Inbox to review" }))
    await waitFor(() => expect(window.location.hash).toBe("#/inbox"))
    unmount()
    undo.pop()!()
    undo.push(answer("integrations", () => ({ json: [{ ...row, last_error: "Todoist is having trouble (500): Friday tries again" }] })))
    const again = await openBox("Todoist, Needs a look")
    expect(within(again.dialog).getByText("Todoist is having trouble (500): Friday tries again")).toBeTruthy()
  })

  it("asks on Disconnect whether what it brought in stays; Cancel keeps it connected", async () => {
    const [row] = await connected()
    undo.push(answer("integrations", (_, url) => (url.pathname.endsWith("integrations") ? { json: [{ ...row, made: 3 }] } : undefined)))
    const { user, dialog } = await openBox("Todoist, Connected")
    await user.click(await within(dialog).findByRole("button", { name: "Disconnect" }))
    const asking = within(dialog).getByRole("alertdialog", { name: "Disconnect Todoist" })
    expect(within(asking).getByText("Keep the 3 to-dos Todoist brought in, or remove them from Friday? Nothing changes in Todoist.")).toBeTruthy()
    await user.click(within(asking).getByRole("button", { name: "Cancel" }))
    expect(within(dialog).queryByRole("alertdialog")).toBeNull()
    expect((await connected()).length).toBe(1)
  })

  it("disconnects keeping what it brought in, and the token form comes back", async () => {
    const { user, dialog } = await openBox("Todoist, Connected")
    const [row] = await connected()
    await user.click(await within(dialog).findByRole("button", { name: "Disconnect" }))
    await user.click(within(dialog).getByRole("button", { name: "Keep them" }))
    expect((await waitForSent("integration_disconnect")).body).toEqual({ id: row.id, keep: true })
    expect(await screen.findByText("Todoist disconnected")).toBeTruthy()
    expect(await within(dialog).findByLabelText("Todoist API token")).toBeTruthy()
    expect(await connected()).toEqual([])
  })

  it("disconnects removing what it brought in", async () => {
    const { user, dialog } = await openBox("Todoist")
    await user.type(within(dialog).getByLabelText("Todoist API token"), `${GOOD}{Enter}`)
    await user.click(await within(dialog).findByRole("button", { name: "Disconnect" }))
    const [row] = await connected()
    await user.click(within(dialog).getByRole("button", { name: "Remove them" }))
    expect((await waitForSent("integration_disconnect")).body).toEqual({ id: row.id, keep: false })
    await waitFor(async () => expect(await connected()).toEqual([]))
  })
})

describe("token forms that ask for more (Jira, Canvas)", () => {
  it("Jira asks for your site and email beside the token, and says what's missing in its words", async () => {
    const { user, dialog } = await openBox("Jira")
    const connect = within(dialog).getByRole("button", { name: "Connect" }) as HTMLButtonElement
    await user.type(within(dialog).getByLabelText("Atlassian API token"), "jira-token")
    expect(connect.disabled).toBe(true) // the site and email first
    await user.type(within(dialog).getByLabelText("Your Jira site"), "acme")
    expect(connect.disabled).toBe(true)
    const email = within(dialog).getByLabelText("The email you sign in to Jira with")
    expect(email.getAttribute("type")).toBe("email")
    await user.type(email, "alex")
    await user.click(connect)
    expect((await waitForSent("integration_connect")).body).toEqual({ kind: "jira", token: "jira-token", fields: { site: "acme", email: "alex" } })
    expect(await screen.findByText("Give the email you sign in to Jira with: Jira's token needs it")).toBeTruthy()
  })

  it("Canvas links its own help, and says when the school's address isn't one", async () => {
    const { user, dialog } = await openBox("Canvas")
    expect(within(dialog).getByRole("link", { name: "Canvas's own help on this" }).getAttribute("href")).toContain("community.canvaslms.com")
    expect(within(dialog).getByText(/No New Access Token button\? Your school has turned tokens off/)).toBeTruthy()
    await user.type(within(dialog).getByLabelText("Your school's Canvas address"), "my school")
    await user.type(within(dialog).getByLabelText("Canvas access token"), "canvas-token{Enter}")
    expect((await waitForSent("integration_connect")).body).toEqual({ kind: "canvas", token: "canvas-token", fields: { site: "my school" } })
    expect(await screen.findByText("Give your school's Canvas address, like canvas.yourschool.edu")).toBeTruthy()
  })
})

describe("Notion's lists (C101)", () => {
  it("connects and lists its to-do lists, your own read and a team's not", async () => {
    const { user, dialog } = await openBox("Notion")
    await user.type(within(dialog).getByLabelText("Notion personal access token"), "notion-token{Enter}")
    expect(await within(dialog).findByText("Lists Friday reads")).toBeTruthy()
    expect(await within(dialog).findByText("Homework")).toBeTruthy()
    expect(within(dialog).getByRole("switch", { name: "Read Homework" }).getAttribute("aria-checked")).toBe("true")
    expect(within(dialog).getByText("A team's list: only what's assigned to you")).toBeTruthy()
    const team = within(dialog).getByRole("switch", { name: "Read Team board" })
    expect(team.getAttribute("aria-checked")).toBe("false")
    await user.click(team)
    const [row] = (await connected()).filter((c) => c.kind === "notion")
    expect((await waitForSent("integration_list_set")).body).toEqual({ id: row.id, list: "ds-team", on: true, keep: true })
    expect(within(dialog).getByRole("switch", { name: "Read Team board" }).getAttribute("aria-checked")).toBe("true")
  })

  it("asks before it stops reading a list that brought to-dos in", async () => {
    const [row] = (await connected()).filter((c) => c.kind === "notion")
    undo.push(answer("integration_lists", () => ({ json: [{ id: "ds-home", name: "Homework", on: true, team: false, made: 1 }] })))
    const { user, dialog } = await openBox("Notion, Connected")
    expect(await within(dialog).findByText("1 in your plan")).toBeTruthy()
    await user.click(within(dialog).getByRole("switch", { name: "Read Homework" }))
    const asking = within(dialog).getByRole("alertdialog", { name: "Stop reading Homework" })
    expect(within(asking).getByText("Keep the to-do Homework brought in, or remove it from Friday? Nothing changes in Notion.")).toBeTruthy()
    await user.click(within(asking).getByRole("button", { name: "Cancel" }))
    await user.click(within(dialog).getByRole("switch", { name: "Read Homework" }))
    await user.click(within(dialog).getByRole("button", { name: "Remove them" }))
    expect((await waitForSent("integration_list_set")).body).toEqual({ id: row.id, list: "ds-home", on: false, keep: false })
  })

  it("says when the service can't list them, and when there are none", async () => {
    undo.push(answer("integration_lists", () => refused("id", "Notion is having trouble (502): Friday tries again")))
    const first = await openBox("Notion, Connected")
    expect(await within(first.dialog).findByText("Notion is having trouble (502): Friday tries again")).toBeTruthy()
    first.unmount()
    undo.pop()!()
    undo.push(answer("integration_lists", () => ({ json: [] })))
    const { dialog } = await openBox("Notion, Connected")
    expect(await within(dialog).findByText(/^No to-do lists yet: a database with a Done checkbox or a Status is one/)).toBeTruthy()
  })
})

describe("a sign-in box", () => {
  it("opens Microsoft's page in the browser and waits for you to come back", async () => {
    opened.length = 0
    const { user, dialog } = await openBox("Microsoft To Do")
    expect(within(dialog).getByText(/Some schools and workplaces let only an administrator approve new apps/)).toBeTruthy()
    expect(within(dialog).getByText(/Your sign-in stays on this Mac/)).toBeTruthy()
    const sign = await within(dialog).findByRole("button", { name: "Sign in with Microsoft" })
    await waitFor(() => expect((sign as HTMLButtonElement).disabled).toBe(false))
    await user.click(sign)
    expect((await waitForSent("integration_sign_in")).body).toEqual({ kind: "microsoft_todo", origin: friday.base })
    await waitFor(() => expect(opened).toHaveLength(1))
    const [url, target] = opened[0] as [string, string]
    expect(url).toMatch(/^https:\/\/login\.microsoftonline\.com\//)
    expect(target).toBe("_blank")
    expect(within(dialog).getByText(/Finish on Microsoft To Do's page in your browser/)).toBeTruthy()
    expect(within(dialog).getByRole("link", { name: "Open it again" }).getAttribute("href")).toBe(url)
  })

  it("Outlook reads mailboxes signed in with Microsoft", async () => {
    opened.length = 0
    const { user, dialog } = await openBox("Outlook")
    expect(within(dialog).getByText(/Nothing is sent, moved, deleted or marked read/)).toBeTruthy()
    const sign = await within(dialog).findByRole("button", { name: "Sign in with Outlook" })
    await waitFor(() => expect((sign as HTMLButtonElement).disabled).toBe(false))
    await user.click(sign)
    expect((await waitForSent("integration_sign_in")).body).toEqual({ kind: "outlook_mail", origin: friday.base })
    await waitFor(() => expect(opened).toHaveLength(1))
    expect(within(dialog).getByText(/Finish on Outlook's page in your browser/)).toBeTruthy()
  })

  it("lists the Outlook mailboxes it reads, each with Remove", async () => {
    undo.push(answer("mail_app_accounts", () => ({ json: [{ provider: "outlook", address: "alex@outlook.com" }] })))
    undo.push(answer("mail_app_forget", () => ({ json: { command_id: null, result: { message: "Stopped reading alex@outlook.com" } } })))
    const { user, dialog } = await openBox("Outlook, Connected")
    expect(within(dialog).getByText("Reading alex@outlook.com")).toBeTruthy()
    await user.click(within(dialog).getByRole("button", { name: "Remove" }))
    expect((await waitForSent("mail_app_forget")).body).toEqual({ address: "alex@outlook.com" })
  })

  it("says a service isn't ready in this copy of Friday", async () => {
    undo.push(answer("integration_token_page", () => ({ json: { url: null, ready: false } })))
    const { dialog } = await openBox("Slack")
    expect(await within(dialog).findByText("Slack isn't ready in this copy of Friday yet: it comes with the next update.")).toBeTruthy()
    expect(within(dialog).queryByRole("button", { name: "Sign in with Slack" })).toBeNull()
  })
})

describe("one the Mac app reads (Apple Reminders)", () => {
  it("in a browser, says to open Friday on the Mac, and can't connect", async () => {
    const { dialog } = await openBox("Apple Reminders")
    expect(within(dialog).getByText(/macOS asks once whether Friday may see your reminders/)).toBeTruthy()
    expect((within(dialog).getByRole("button", { name: "Connect" }) as HTMLButtonElement).disabled).toBe(true)
    expect(within(dialog).getByText("Open Friday on your Mac to connect Apple Reminders.")).toBeTruthy()
  })

  it("in the Mac app, connects with no token, and points to macOS's privacy page when it's needed", async () => {
    const agent = vi.spyOn(window.navigator, "userAgent", "get").mockReturnValue("Mozilla/5.0 FridayMac/1.0")
    const { user, dialog, unmount } = await openBox("Apple Reminders")
    expect(within(dialog).getByText(/Friday's Mac app reads .+ while it's open; nothing leaves this Mac/)).toBeTruthy()
    await user.click(within(dialog).getByRole("button", { name: "Connect" }))
    expect((await waitForSent("integration_connect")).body).toEqual({ kind: "reminders", token: "" })
    expect(await within(dialog).findByText("Connected: reading it within the minute.")).toBeTruthy()
    const [row] = (await connected()).filter((c) => c.kind === "reminders")
    expect(row.name).toBe("Apple Reminders")
    agent.mockRestore()
    unmount()
    undo.push(answer("integrations", () => ({ json: [{ ...row, last_error: "Friday isn't allowed to see your reminders: open System Settings → Privacy & Security → Reminders" }] })))
    const again = await openBox("Apple Reminders, Needs a look")
    expect(within(again.dialog).getByRole("link", { name: "Open Privacy & Security → Reminders" }).getAttribute("href")).toBe("x-apple.systempreferences:com.apple.preference.security?Privacy_Reminders")
  })
})

describe("the Google Tasks script (C130)", () => {
  const LINK = "https://script.google.com/macros/s/AKfycbx0123456789abcdefghijklmnop/exec"

  it("copies the script with this Friday's key, and shows it to read", async () => {
    const { user, dialog } = await openBox("Google Tasks")
    expect(within(dialog).getByText("Press Copy script below.")).toBeTruthy()
    expect(within(dialog).getByRole("link", { name: "Open Google Apps Script" }).getAttribute("href")).toBe("https://script.new")
    await user.click(within(dialog).getByRole("button", { name: "Copy script" }))
    expect(within(dialog).getByRole("button", { name: "Copied" })).toBeTruthy()
    const key = window.localStorage.getItem("friday.googleTasksKey")!
    expect(key).toMatch(/^[\w-]{20,}$/)
    const copied = await navigator.clipboard.readText()
    expect(copied).toContain(`const KEY = "${key}";`)
    await user.click(within(dialog).getByRole("button", { name: "Read the script" }))
    const shown = within(dialog).getByRole("textbox", { name: "Friday's Google Tasks script" }) as HTMLTextAreaElement
    expect(shown.value).toBe(copied)
    expect(shown.readOnly).toBe(true)
    await user.click(within(dialog).getByRole("button", { name: "Hide the script" }))
    expect(within(dialog).queryByRole("textbox", { name: "Friday's Google Tasks script" })).toBeNull()
  })

  it("shows the script selected to copy by hand when there's no clipboard", async () => {
    const { user, dialog } = await openBox("Google Tasks")
    vi.spyOn(navigator.clipboard, "writeText").mockRejectedValue(new Error("not allowed"))
    await user.click(within(dialog).getByRole("button", { name: "Copy script" }))
    expect(await within(dialog).findByRole("textbox", { name: "Friday's Google Tasks script" })).toBeTruthy()
    expect(within(dialog).getByRole("button", { name: "Copy script" })).toBeTruthy()
  })

  it("says Google's warning before you meet it, with what to press", async () => {
    const { dialog } = await openBox("Google Tasks")
    const note = within(dialog).getByRole("note")
    expect(within(note).getByText("At step 6 Google shows a warning. It's expected.")).toBeTruthy()
    expect(within(note).getByText("“Google hasn't verified this app”")).toBeTruthy()
    expect(within(note).getByText("Press Go to Friday Tasks (unsafe).")).toBeTruthy()
  })

  it("takes only the Web app link, saying what's wrong with another", async () => {
    const { user, dialog } = await openBox("Google Tasks")
    const box = within(dialog).getByLabelText("The script's Web app URL")
    const connect = within(dialog).getByRole("button", { name: "Connect" }) as HTMLButtonElement
    await user.type(box, "https://script.google.com/macros/s/AKfycbx0123456789abcdefghijklmnop/dev")
    expect(within(dialog).getByText("That's the test link: use the Web app URL, the one ending in /exec.")).toBeTruthy()
    expect(connect.disabled).toBe(true)
    await user.clear(box)
    await user.type(box, "https://docs.google.com/document/d/1")
    expect(within(dialog).getByText("That isn't the Web app URL yet: it starts https://script.google.com/ and ends in /exec.")).toBeTruthy()
    await user.clear(box)
    await user.type(box, LINK)
    expect(within(dialog).queryByText(/That isn't the Web app URL yet/)).toBeNull()
    expect(connect.disabled).toBe(false)
  })

  it("connects with the link and the key together, and keeps the link when the script refuses", async () => {
    undo.push(answer("integration_connect", () => refused("token", "token: The script's key isn't this Friday's: copy the script from Friday's Google Tasks box again")))
    const { user, dialog } = await openBox("Google Tasks")
    const box = within(dialog).getByLabelText("The script's Web app URL") as HTMLInputElement
    await user.type(box, ` ${LINK} {Enter}`)
    const key = window.localStorage.getItem("friday.googleTasksKey")
    expect((await waitForSent("integration_connect")).body).toEqual({ kind: "google_tasks", token: `${LINK}#${key}`, fields: {} })
    expect(await screen.findByText("The script's key isn't this Friday's: copy the script from Friday's Google Tasks box again")).toBeTruthy()
    expect(box.value.trim()).toBe(LINK)
  })

  it("empties the box once the script is connected", async () => {
    undo.push(answer("integration_connect", () => ({ json: { command_id: null, result: { message: "Google Tasks connected (your Google Tasks)" } } })))
    const { user, dialog } = await openBox("Google Tasks")
    const box = within(dialog).getByLabelText("The script's Web app URL") as HTMLInputElement
    fireEvent.change(box, { target: { value: LINK } })
    await user.click(within(dialog).getByRole("button", { name: "Connect" }))
    await waitFor(() => expect(box.value).toBe(""))
  })
})
