// The AI box's choices (Claude through its command or a key, another service by its address, an open model on this
// Mac with its download) and Google's own connection in each state it can be in: no key file yet, signing in, signed
// in again, an account to remove, Gmail to allow. The demo's AI is a stand-in whatever is chosen, and its Google can't
// be signed in to, so Google's answers and the downloads are given here: nothing opens Google's page or downloads a
// model, and no key reaches a service.

import { fireEvent, screen, waitFor, within } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { friday, openFriday, waitForSent } from "@/test/friday"
import { answer, answered, done, refused } from "./screen.test.helpers"

const undo: (() => void)[] = []
afterEach(() => {
  while (undo.length) undo.pop()!()
  vi.restoreAllMocks()
})

type Llm = { provider: string; model: string; base_url: string | null; via?: string }
const llm = async () => (await friday.q<{ llm: Llm }>("settings")).llm

async function openBox(box: string | RegExp, dialog = typeof box === "string" ? box.split(", ")[0] : "Google Calendar") {
  const app = await openFriday("/settings/integrations")
  await app.user.click(await screen.findByRole("button", { name: box }))
  return { ...app, dialog: await screen.findByRole("dialog", { name: dialog }) }
}

describe("the AI box", () => {
  it("asks Claude through Claude Code, with a key kept only as a backup", async () => {
    const { user, dialog } = await openBox("AI, Ready")
    expect(within(dialog).getByText("The demo uses a stand-in AI; nothing you choose here is asked.")).toBeTruthy()
    const via = within(dialog).getByRole("radiogroup", { name: "Ask Claude through" })
    expect(within(via).getByRole("radio", { name: "Claude Code on this Mac" }).getAttribute("aria-checked")).toBe("true")
    expect(within(dialog).getByText(/Uses Claude Code on this Mac, signed in as you: no key needed/)).toBeTruthy()
    expect(within(dialog).getByText("Anthropic API key (optional) · from console.anthropic.com")).toBeTruthy()
    expect(within(dialog).getByText("A backup, used only if Claude Code fails.")).toBeTruthy()
    await user.click(within(via).getByRole("radio", { name: "Claude Code on this Mac" }))
    // the one chosen already: nothing sent
    await user.click(within(via).getByRole("radio", { name: "An API key" }))
    expect((await waitForSent("settings_set")).body).toEqual({ key: "llm", value: { via: "key" } })
    await waitFor(async () => expect((await llm()).via).toBe("key"))
    await waitFor(() => expect(within(dialog).queryByText("A backup, used only if Claude Code fails.")).toBeNull())
    expect(within(dialog).getByText("Anthropic API key · from console.anthropic.com")).toBeTruthy()
    await user.click(within(within(dialog).getByRole("radiogroup", { name: "Ask Claude through" })).getByRole("radio", { name: "Claude Code on this Mac" }))
    await waitFor(async () => expect((await llm()).via).toBe("command"))
  })

  it("keeps a key, says one is saved, and replaces or removes it", async () => {
    const { user, dialog, client } = await openBox("AI, Ready")
    const box = within(dialog).getByLabelText("Anthropic API key") as HTMLInputElement
    expect(box.type).toBe("password")
    await user.type(box, "sk ant with spaces{Enter}")
    expect((await waitForSent("ai_key_set")).body).toEqual({ provider: "claude", key: "sk ant with spaces" })
    expect(await screen.findByText("A key has no spaces or line breaks in it: paste it again")).toBeTruthy()
    await user.clear(box)
    await user.type(box, "sk-ant-test-0000")
    await user.click(within(dialog).getByRole("button", { name: "Save key" }))
    expect((await waitForSent("ai_key_set")).body).toEqual({ provider: "claude", key: "sk-ant-test-0000" })
    await answered(client)
    expect(await within(dialog).findByText("A key is saved (kept in secrets.toml, never shown again).")).toBeTruthy()
    await user.click(within(dialog).getByRole("button", { name: "Replace" }))
    expect(within(dialog).getByLabelText("Anthropic API key")).toBeTruthy()
  })

  it("removes a saved key", async () => {
    const { user, dialog } = await openBox("AI, Ready")
    await user.click(await within(dialog).findByRole("button", { name: "Remove" }))
    expect((await waitForSent("ai_key_set")).body).toEqual({ provider: "claude", key: "" })
    expect(await within(dialog).findByLabelText("Anthropic API key")).toBeTruthy()
  })

  it("chooses another service by its address, and a model from its list or by name", async () => {
    undo.push(answer("ai_models", () => ({ json: { models: ["llama-3.1-70b", "qwen-2.5-32b"], error: null } })))
    const { user, dialog, client } = await openBox("AI, Ready")
    await user.click(within(within(dialog).getByRole("radiogroup", { name: "Which AI" })).getByRole("radio", { name: /^Another service/ }))
    expect((await waitForSent("settings_set")).body).toEqual({ key: "llm", value: { provider: "compatible" } })
    const address = await within(dialog).findByRole("textbox", { name: "Its address" })
    expect(within(dialog).getByText("Its API key (optional)")).toBeTruthy()
    expect(within(dialog).getByText("Leave it empty if the service needs none.")).toBeTruthy()
    await user.type(address, "http://127.0.0.1:9/v1")
    await user.tab()
    expect((await waitForSent("settings_set")).body).toEqual({ key: "llm", value: { base_url: "http://127.0.0.1:9/v1" } })
    await answered(client)
    const model = (await within(dialog).findByRole("combobox", { name: "Model" })) as HTMLSelectElement
    await user.selectOptions(model, "qwen-2.5-32b")
    expect((await waitForSent("settings_set")).body).toEqual({ key: "llm", value: { model: "qwen-2.5-32b", small_model: "qwen-2.5-32b" } })
    await user.type(within(dialog).getByPlaceholderText("Or type its name"), "mixtral-8x7b{Enter}")
    expect((await waitForSent("settings_set")).body).toEqual({ key: "llm", value: { model: "mixtral-8x7b", small_model: "mixtral-8x7b" } })
    await answered(client)
    expect(await within(dialog).findByText("Model: mixtral-8x7b")).toBeTruthy()
  })

  it("says when the service can't list its models", async () => {
    undo.push(answer("ai_models", () => ({ json: { models: [], error: "Connection refused" } })))
    const { dialog } = await openBox("AI, Ready")
    expect(await within(dialog).findByText("Couldn't list its models: Connection refused")).toBeTruthy()
    expect(within(dialog).getByRole("button", { name: "Use" })).toBeTruthy()
  })

  it("offers another address for Muse, and a key for OpenAI, Gemini and Grok", async () => {
    await friday.c("settings_set", { key: "llm", value: { base_url: null } })
    const { user, dialog, client } = await openBox("AI, Ready")
    const which = within(dialog).getByRole("radiogroup", { name: "Which AI" })
    await user.click(within(which).getByRole("radio", { name: /^Muse/ }))
    await answered(client)
    expect(await within(dialog).findByText(/^Muse API key/)).toBeTruthy()
    await user.click(within(dialog).getByRole("button", { name: "Use another address" }))
    expect(within(dialog).getByRole("textbox", { name: "Meta's API address, if it moved" })).toBeTruthy()
    await user.click(within(which).getByRole("radio", { name: /^Grok/ }))
    await answered(client)
    expect(await within(dialog).findByText("Grok API key · from console.x.ai")).toBeTruthy()
    await user.click(within(which).getByRole("radio", { name: /^OpenAI/ }))
    await answered(client)
    expect(await within(dialog).findByText(/OpenAI API key/)).toBeTruthy()
    expect((await llm()).provider).toBe("openai")
  })
})

describe("an open model on this Mac", () => {
  const catalog = [
    { name: "llama3.2:3b", label: "Llama 3.2 3B (Meta)", size_gb: 2.0, note: "Small and quickest", here: true, friday: true },
    { name: "gemma3:4b", label: "Gemma 3 4B (Google)", size_gb: 3.3, note: "Small, reads well for its size", here: false, friday: false },
  ]
  const running = { running: true, warning: "Runs on this Mac: the model is downloaded here.", catalog, others: [{ name: "mine:latest", label: "mine:latest", size_gb: null, note: "", here: true, friday: false }], download: null, active: "llama3.2:3b" }

  it("says what it costs, and that Ollama isn't running", async () => {
    undo.push(answer("local_models", () => ({ json: { ...running, running: false, catalog: [], others: [] } })))
    const { user, dialog, client } = await openBox("AI, Ready")
    await user.click(within(within(dialog).getByRole("radiogroup", { name: "Which AI" })).getByRole("radio", { name: /^On this Mac/ }))
    expect((await waitForSent("settings_set")).body).toEqual({ key: "llm", value: { provider: "local" } })
    await answered(client)
    expect(await within(dialog).findByText("Runs on this Mac: the model is downloaded here.")).toBeTruthy()
    expect(within(dialog).getByText(/Ollama runs the models. It isn't running here/)).toBeTruthy()
  })

  it("lists the models, which is in use, and downloads one", async () => {
    await friday.c("settings_set", { key: "llm", value: { provider: "local", model: "gemma3:4b" } })
    undo.push(answer("local_models", () => ({ json: { ...running, active: "gemma3:4b" } })))
    undo.push(answer("local_model_use", () => done({ message: "Downloading Gemma 3 4B" })))
    const { user, dialog } = await openBox("AI, Ready")
    const row = (await within(dialog).findByText("Llama 3.2 3B (Meta)")).closest(".fr-row") as HTMLElement
    expect(within(row).getByText("on this Mac, downloaded by Friday")).toBeTruthy()
    expect(within(row).getByText("2 GB")).toBeTruthy()
    const mine = within(dialog).getByText("mine:latest", { selector: ".mono" }).closest(".fr-row") as HTMLElement
    expect(within(mine).getByText("on this Mac, yours: never removed")).toBeTruthy()
    const gemma = within(dialog).getByText("Gemma 3 4B (Google)").closest(".fr-row") as HTMLElement
    expect(within(gemma).getByText("In use")).toBeTruthy()
    await user.click(within(row).getByRole("button", { name: "Use" }))
    expect((await waitForSent("local_model_use")).body).toEqual({ name: "llama3.2:3b" })
    await user.type(within(dialog).getByPlaceholderText("Another model Ollama has, e.g. llama3.1:8b"), "phi4-mini{Enter}")
    expect((await waitForSent("local_model_use")).body).toEqual({ name: "phi4-mini" })
  })

  it("asks before replacing a model Friday downloaded, which it then removes", async () => {
    await friday.c("settings_set", { key: "llm", value: { provider: "local", model: "llama3.2:3b" } })
    undo.push(answer("local_models", () => ({ json: running })))
    undo.push(answer("local_model_use", () => done({ message: "Downloading Gemma 3 4B" })))
    const { user, dialog } = await openBox("AI, Ready")
    const gemma = (await within(dialog).findByText("Gemma 3 4B (Google)")).closest(".fr-row") as HTMLElement
    await user.click(within(gemma).getByRole("button", { name: "Download · 3.3 GB" }))
    const asking = within(dialog).getByRole("alertdialog", { name: "Before you change" })
    expect(within(asking).getByText(/When gemma3:4b is ready, Friday will remove llama3.2:3b \(2 GB\), which it downloaded/)).toBeTruthy()
    await user.click(within(asking).getByRole("button", { name: "Cancel" }))
    expect(within(dialog).queryByRole("alertdialog")).toBeNull()
    await user.click(within(gemma).getByRole("button", { name: "Download · 3.3 GB" }))
    await user.click(within(dialog).getByRole("button", { name: "Change and remove it" }))
    expect((await waitForSent("local_model_use")).body).toEqual({ name: "gemma3:4b" })
  })

  it("asks before leaving for a service, since Friday's own download goes", async () => {
    undo.push(answer("local_models", () => ({ json: running })))
    const { user, dialog } = await openBox("AI, Ready")
    await within(dialog).findByText("Gemma 3 4B (Google)")
    await user.click(within(within(dialog).getByRole("radiogroup", { name: "Which AI" })).getByRole("radio", { name: /^Claude/ }))
    const asking = within(dialog).getByRole("alertdialog", { name: "Before you change" })
    expect(within(asking).getByText(/Friday will remove llama3.2:3b, which it downloaded to this Mac, and read with Claude/)).toBeTruthy()
    await user.click(within(asking).getByRole("button", { name: "Cancel" }))
    await user.click(within(within(dialog).getByRole("radiogroup", { name: "Which AI" })).getByRole("radio", { name: /^Claude/ }))
    await user.click(within(dialog).getByRole("button", { name: "Switch and remove it" }))
    expect((await waitForSent("settings_set")).body).toEqual({ key: "llm", value: { provider: "claude" } })
    await waitFor(async () => expect((await llm()).provider).toBe("claude"))
  })

  it("shows a download's progress with Stop, and what became of one that failed or stopped", async () => {
    await friday.c("settings_set", { key: "llm", value: { provider: "local", model: "llama3.2:3b" } })
    let download: Record<string, unknown> = { name: "gemma3:4b", status: "downloading", completed: 1.1e9, total: 3.3e9, error: null }
    undo.push(answer("local_models", () => ({ json: { ...running, download } })))
    undo.push(answer("local_model_cancel", () => ((download = { ...download, status: "cancelled" }), done({ message: "Stopped downloading gemma3:4b" }))))
    const { user, dialog, client } = await openBox("AI, Ready")
    expect(await within(dialog).findByText(/· 33% of 3.3 GB/)).toBeTruthy()
    // while it downloads, nothing else is chosen
    for (const use of within(dialog).getAllByRole("button", { name: /^(Use|Download)/ })) expect((use as HTMLButtonElement).disabled).toBe(true)
    await user.click(within(dialog).getByRole("button", { name: "Stop the download" }))
    await waitForSent("local_model_cancel")
    await answered(client)
    expect(await within(dialog).findByText("The download of gemma3:4b was stopped. The AI you had stays.")).toBeTruthy()
    download = { ...download, status: "failed", error: "no space left on device" }
    await client.invalidateQueries({ queryKey: ["local_models"] })
    expect(await within(dialog).findByText("Downloading gemma3:4b failed: no space left on device. The AI you had stays.")).toBeTruthy()
    await friday.c("settings_set", { key: "llm", value: { provider: "claude", model: "claude-sonnet-5-5" } })
  })
})

type Access = Record<string, unknown>
const ACCOUNT = { email: "aj452@cornell.edu", gmail: true, events: true, mail_error: null, tasks: false }
const connectedAccess: Access = { state: "idle", message: null, url: null, account: null, client_file: true, calendar: true, gmail: true, events: true, accounts: [ACCOUNT] }

/** Friday as your own, not the demo: Google's connection is offered. */
async function yourOwn() {
  const status = await friday.q<Record<string, unknown>>("status")
  undo.push(answer("status", () => ({ json: { ...status, demo: false } })))
}

describe("Google's own connection", () => {
  it("before a key file: what it is, the steps to get one, and the server's words for a wrong file", async () => {
    await yourOwn()
    let access: Access = { ...connectedAccess, client_file: false, calendar: false, gmail: false, accounts: [] }
    undo.push(answer("google_connect_status", () => ({ json: access })))
    undo.push(answer("google_client_save", (body) => ((body as { content: string }).content.includes("installed") ? ((access = { ...access, client_file: true }), done(access)) : refused("file", "file: file: that isn't Google's key file"))))
    const { user, dialog } = await openBox(/^Google Calendar/)
    const advanced = within(dialog).getByRole("button", { name: "Advanced: Google with a Google Cloud key of your own" })
    expect(advanced.getAttribute("aria-expanded")).toBe("false")
    await user.click(advanced)
    expect(await within(dialog).findByText(/Most people don't need this: add your Google account to this Mac/)).toBeTruthy()
    expect(await within(dialog).findByText("Make a project")).toBeTruthy()
    expect(within(dialog).getByRole("link", { name: /^Credentials/ }).getAttribute("href")).toBe("https://console.cloud.google.com/apis/credentials")
    const file = dialog.querySelector('input[type="file"][accept=".json,application/json"]') as HTMLInputElement
    await user.upload(file, new File(['{"web": {}}'], "notes.json", { type: "application/json" }))
    expect((await waitForSent("google_client_save")).body).toEqual({ content: '{"web": {}}' })
    expect(await within(dialog).findByText("That isn't Google's key file.")).toBeTruthy()
    await user.upload(file, new File(['{"installed": {"client_id": "x"}}'], "client.json", { type: "application/json" }))
    // taken: Connect, the first time, with the same sign-in from Terminal beside it
    expect(await within(dialog).findByRole("button", { name: "Connect Google" })).toBeTruthy()
    expect(within(dialog).getByText("Opens Google's page in your browser. Allow Friday there, then come back.")).toBeTruthy()
    expect(within(dialog).getByText("Connect Google Calendar first; Google asks about your mail at the same time.")).toBeTruthy()
  })

  it("copies the Terminal way to sign in", async () => {
    await yourOwn()
    undo.push(answer("google_connect_status", () => ({ json: { ...connectedAccess, client_file: false, calendar: false, accounts: [] } })))
    const { user, dialog } = await openBox(/^Google Calendar/)
    await user.click(within(dialog).getByRole("button", { name: /^Advanced:/ }))
    expect(await within(dialog).findByText("fridayd google-login --client-file ~/Downloads/client_secret.json")).toBeTruthy()
    await user.click(within(dialog).getByRole("button", { name: "Copy" }))
    expect(await within(dialog).findByRole("button", { name: "Copied" })).toBeTruthy()
    expect(await navigator.clipboard.readText()).toBe("fridayd google-login --client-file ~/Downloads/client_secret.json")
  })

  it("adds another account: waits for Google's page, can be cancelled, and says what to do when Google blocks it", async () => {
    await yourOwn()
    let access: Access = connectedAccess
    undo.push(answer("google_connect_status", () => ({ json: access })))
    undo.push(answer("google_connect", () => ((access = { ...connectedAccess, state: "waiting", url: "https://accounts.google.com/o/oauth2/auth?client_id=x" }), done(access))))
    undo.push(answer("google_connect_cancel", () => ((access = { ...connectedAccess, state: "idle", message: "Sign-in stopped: nothing was connected" }), done(access))))
    const { user, dialog } = await openBox("Google Calendar, 7 connected")
    const add = await within(dialog).findByRole("button", { name: "Add another Google account" })
    expect(within(dialog).getByText(/For your school's or work's calendar too/)).toBeTruthy()
    const blocked = within(dialog).getByText(/Google says “Access blocked/).closest("details")!
    expect(blocked.open).toBe(false)
    await user.click(add)
    expect((await waitForSent("google_connect")).body).toEqual({})
    expect(await within(dialog).findByText(/^Google's page is open in your browser: choose the account and click Allow/)).toBeTruthy()
    expect(within(dialog).getByRole("button", { name: "Waiting for Google…" }).getAttribute("aria-busy")).toBe("true")
    expect(within(dialog).getByRole("link", { name: "Didn't see it? Open Google's page" }).getAttribute("href")).toBe("https://accounts.google.com/o/oauth2/auth?client_id=x")
    expect(within(dialog).getByText(/Google says “Access blocked/).closest("details")!.open).toBe(true)
    await user.click(within(dialog).getByRole("button", { name: "Cancel sign-in" }))
    await waitForSent("google_connect_cancel")
    expect(await within(dialog).findByText("Sign-in stopped: nothing was connected")).toBeTruthy()
  })

  it("says it's connected once Google's page is done, and a sign-in that failed", async () => {
    await yourOwn()
    let access: Access = connectedAccess
    undo.push(answer("google_connect_status", () => ({ json: access })))
    undo.push(answer("google_connect", () => ((access = { ...connectedAccess, state: "waiting", url: "https://accounts.google.com/x" }), done(access))))
    const { user, dialog } = await openBox("Google Calendar, 7 connected")
    await user.click(await within(dialog).findByRole("button", { name: "Add another Google account" }))
    await within(dialog).findByRole("button", { name: "Waiting for Google…" })
    access = { ...connectedAccess, state: "connected", account: "alex@gmail.com", accounts: [ACCOUNT, { ...ACCOUNT, email: "alex@gmail.com" }] }
    expect(await within(dialog).findByText("Connected alex@gmail.com. Switch on the calendars Friday should read below.", {}, { timeout: 8000 })).toBeTruthy()
    access = { ...connectedAccess, state: "failed", message: "Google said: access_denied" }
    await waitFor(() => expect(within(dialog).queryByText("Google said: access_denied")).toBeNull())
  })

  it("says the server's words when Google's page can't be opened", async () => {
    await yourOwn()
    undo.push(answer("google_connect_status", () => ({ json: connectedAccess })))
    undo.push(answer("google_connect", () => refused("google", "google: Google's key file is missing its client id")))
    const { user, dialog } = await openBox("Google Calendar, 7 connected")
    await user.click(await within(dialog).findByRole("button", { name: "Add another Google account" }))
    expect(await within(dialog).findByText("Google's key file is missing its client id.")).toBeTruthy()
  })

  it("asks before removing an account, and keeps it on Keep", async () => {
    await yourOwn()
    undo.push(answer("google_connect_status", () => ({ json: connectedAccess })))
    undo.push(answer("google_remove", () => done({ ...connectedAccess, calendar: false, accounts: [] })))
    const { user, dialog } = await openBox("Google Calendar, 7 connected")
    await user.click(await within(dialog).findByRole("button", { name: "Remove aj452@cornell.edu" }))
    expect(within(dialog).getByText(/^Remove aj452@cornell.edu\? Friday stops reading its calendars and mail/)).toBeTruthy()
    await user.click(within(dialog).getByRole("button", { name: "Keep" }))
    expect(within(dialog).queryByText(/^Remove aj452@cornell.edu\?/)).toBeNull()
    await user.click(within(dialog).getByRole("button", { name: "Remove aj452@cornell.edu" }))
    await user.click(within(dialog).getByRole("button", { name: "Remove" }))
    expect((await waitForSent("google_remove")).body).toEqual({ account: "aj452@cornell.edu" })
  })

  it("says the server's words when an account can't be removed", async () => {
    await yourOwn()
    undo.push(answer("google_connect_status", () => ({ json: connectedAccess })))
    undo.push(answer("google_remove", () => refused("account", "account: Friday doesn't read that account")))
    const { user, dialog } = await openBox("Google Calendar, 7 connected")
    await user.click(await within(dialog).findByRole("button", { name: "Remove aj452@cornell.edu" }))
    await user.click(within(dialog).getByRole("button", { name: "Remove" }))
    expect(await within(dialog).findByText("Friday doesn't read that account.")).toBeTruthy()
  })

  it("asks to connect an account again when Google stopped letting Friday in, and to allow its mail", async () => {
    await yourOwn()
    const calendars = await friday.q<Record<string, unknown>[]>("google_calendars")
    undo.push(answer("google_calendars", () => ({ json: calendars.map((c) => (c.name === "Canvas" ? { ...c, error: "RefreshError: invalid_grant" } : c)) })))
    const accounts = [ACCOUNT, { ...ACCOUNT, email: "alex@gmail.com", gmail: false }, { ...ACCOUNT, email: "alex@school.edu", mail_error: "RefreshError: invalid_grant" }]
    undo.push(answer("google_connect_status", () => ({ json: { ...connectedAccess, accounts } })))
    const { dialog } = await openBox("Google Calendar, 7 connected")
    expect((await within(dialog).findAllByText("Connect again")).length).toBeGreaterThan(1)
    expect(within(dialog).getAllByText(/^Google stopped letting Friday into this account/).length).toBeGreaterThan(0)
    expect(within(dialog).getAllByRole("button", { name: "Connect again" }).length).toBeGreaterThan(0)
    // the second account's mail waits for Google's OK
    expect(within(dialog).getByText("Its mail isn't allowed yet")).toBeTruthy()
    expect(within(dialog).getByRole("button", { name: "Allow Gmail" })).toBeTruthy()
    expect(within(dialog).getByText(/Its mail isn't allowed yet \(Allow Gmail, under Gmail\)/)).toBeTruthy()
    expect(within(dialog).getByText("Google stopped letting Friday read its mail")).toBeTruthy()
  })

  it("says a calendar that can't be read, and mail Google stopped or the internet can't reach", async () => {
    const calendars = await friday.q<Record<string, unknown>[]>("google_calendars")
    undo.push(answer("google_calendars", () => ({ json: calendars.map((c) => (c.name === "Work" ? { ...c, error: "HttpError 404: Not Found" } : c)) })))
    undo.push(answer("google_connect_status", () => ({ json: { ...connectedAccess, accounts: [{ ...ACCOUNT, mail_error: "ConnectionError: NameResolutionError" }, { ...ACCOUNT, email: "alex@gmail.com", mail_error: "IMAP said: too many connections" }] } })))
    const { user, dialog } = await openBox("Google Calendar, 7 connected")
    expect((await within(dialog).findAllByText("Trouble reading")).length).toBeGreaterThan(0)
    expect(within(dialog).getByText("Couldn't reach the internet; reads again once you're online")).toBeTruthy()
    expect(within(dialog).getByText("IMAP said: too many connections")).toBeTruthy()
    await user.click(await within(dialog).findByRole("button", { name: /^Calendars \d+ of \d+ read/ }))
    expect(within(dialog).getByText("HttpError 404: Not Found")).toBeTruthy()
  })

  it("says Gmail is offline, and when Google hasn't allowed it", async () => {
    undo.push(answer("google_connect_status", () => ({ json: { ...connectedAccess, accounts: [{ ...ACCOUNT, mail_error: "OSError: [Errno 51] Network is unreachable" }] } })))
    const { dialog, unmount } = await openBox("Google Calendar, 7 connected")
    const gmail = (await within(dialog).findByText("Gmail through Google's connection")).parentElement as HTMLElement
    expect(within(gmail).getByText("Offline")).toBeTruthy()
    unmount()
    undo.pop()!()
    undo.push(answer("google_connect_status", () => ({ json: { ...connectedAccess, gmail: false } })))
    const again = await openBox("Google Calendar, 7 connected")
    const card = (await within(again.dialog).findByText("Gmail through Google's connection")).parentElement as HTMLElement
    expect(within(card).getByText("Needs Google's OK")).toBeTruthy()
  })
})

describe("the AI's limit, set in friday.toml", () => {
  it("says to change it there", async () => {
    const status = await friday.q<Record<string, unknown>>("status")
    undo.push(answer("status", () => ({ json: { ...status, config_keys: ["llm", "claude"] } })))
    const { dialog, unmount } = await openBox("AI, Ready")
    expect(within(dialog).getByText("Set in friday.toml: change it there.")).toBeTruthy()
    expect((within(dialog).getByRole("slider", { name: "Daily reads" }) as HTMLInputElement).disabled).toBe(true)
    fireEvent.change(within(dialog).getByRole("slider", { name: "Daily reads" }), { target: { value: "100" } })
    unmount()
    const ask = await openBox("Ask the AI")
    expect(within(ask.dialog).getByText(/Set in friday.toml\.$/)).toBeTruthy()
  })
})
