// The dialogs any page can open: the morning brief, what the last replan changed, what gives when it can't all fit,
// and Ask (the demo's AI is a stand-in that proposes nothing, so what it proposes is given here, in its answer's
// place; the changes it proposes then run on the real Friday).
import { screen, waitFor, within } from "@testing-library/react"
import { afterEach, describe, expect, it } from "vitest"
import { friday, openFriday, waitForSent } from "@/test/friday"

type User = Awaited<ReturnType<typeof openFriday>>["user"]

/** A row of the Plan page's Plan menu. */
async function fromPlanMenu(user: User, row: RegExp) {
  await user.click(await screen.findByRole("button", { name: "Plan", expanded: false }))
  await user.click(await screen.findByRole("button", { name: row }))
}

function dayOn(days: number): string {
  const d = new Date()
  d.setDate(d.getDate() + days)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
}

describe("the morning brief", () => {
  it("shows what matters today, what's fixed and what's pressing", async () => {
    const { user } = await openFriday("/")
    await fromPlanMenu(user, /^Morning brief/)
    expect(await screen.findByText("Good morning")).toBeTruthy()
    const brief = await friday.q<{ summary: string; rocks: { title: string }[]; fixed: unknown[]; alerts: unknown[] }>("brief")
    const dialog = screen.getByRole("dialog")
    expect(within(dialog).getByText("What matters today")).toBeTruthy()
    expect(within(dialog).getByText("Fixed today")).toBeTruthy()
    expect(within(dialog).getByText("Heads up")).toBeTruthy()
    if (brief.summary) await within(dialog).findByText(brief.summary)
    for (const r of brief.rocks) expect(within(dialog).getAllByText(r.title).length).toBeGreaterThan(0)
    if (!brief.rocks.length) expect(within(dialog).getByText("Nothing big today.")).toBeTruthy()
    if (!brief.alerts.length) expect(within(dialog).getByText("Nothing pressing.")).toBeTruthy()
  })

  it("sets today's pace, and remembers whether to show itself each morning", async () => {
    const { user } = await openFriday("/")
    await fromPlanMenu(user, /^Morning brief/)
    await screen.findByText("Good morning")
    const paces = await friday.q<{ paces: Record<string, unknown>; now_label: string }>("paces")
    const other = Object.keys(paces.paces).find((p) => p !== paces.now_label)!
    await user.click(await screen.findByRole("button", { name: other }))
    expect((await waitForSent("pace")).body).toEqual({ name: other, for_days: 1 })
    const box = screen.getByRole("checkbox", { name: "Show this when I open Friday each morning" }) as HTMLInputElement
    const was = box.checked
    await user.click(box)
    const sent = await waitForSent("settings_set")
    expect(sent.body).toMatchObject({ key: "notify", value: { morning_brief: !was } })
    try {
      await waitFor(async () => expect((await friday.q<{ notify: Record<string, unknown> }>("settings")).notify.morning_brief).toBe(!was))
    } finally {
      // back as it was: on, it would open by itself over the tests after, in a morning
      const { notify } = await friday.q<{ notify: Record<string, unknown> }>("settings")
      await friday.c("settings_set", { key: "notify", value: { ...notify, morning_brief: was } })
    }
    await user.click(screen.getByRole("button", { name: "See the plan" }))
    await waitFor(() => expect(screen.queryByText("Good morning")).toBeNull())
  })

  it("starts the first thing planned today, when there is one", async () => {
    const { user } = await openFriday("/")
    await fromPlanMenu(user, /^Morning brief/)
    await screen.findByText("Good morning")
    const start = await screen.findByRole("button", { name: /^Start / }, { timeout: 3000 }).catch(() => null)
    if (!start) return // nothing of today's left to start at this hour
    await user.click(start)
    expect((await waitForSent("start")).body).toHaveProperty("id")
    await waitFor(() => expect(screen.queryByText("Good morning")).toBeNull())
  })

  it("closes with its × and with Escape", async () => {
    const { user } = await openFriday("/")
    await fromPlanMenu(user, /^Morning brief/)
    await screen.findByText("Good morning")
    // named, as a dialog must be for a screen reader (the audit, 12 Nov: the brief, what changed and triage had none)
    await user.click(within(screen.getByRole("dialog", { name: "Morning brief" })).getByRole("button", { name: "Close" }))
    await waitFor(() => expect(screen.queryByText("Good morning")).toBeNull())
    await fromPlanMenu(user, /^Morning brief/)
    await screen.findByText("Good morning")
    await user.keyboard("{Escape}")
    await waitFor(() => expect(screen.queryByText("Good morning")).toBeNull())
  })
})

describe("what changed", () => {
  it("says what led to the last replan and what it moved, and closes", async () => {
    const { user } = await openFriday("/")
    await fromPlanMenu(user, /^What changed/)
    expect(await screen.findByText("What changed")).toBeTruthy()
    const dialog = screen.getByRole("dialog", { name: "What changed" })
    await waitFor(() => expect(within(dialog).queryByText("Working out what would move…")).toBeNull())
    await user.click(within(dialog).getByRole("button", { name: "Close" }))
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull())
  })
})

describe("what gives when it can't all fit", () => {
  it("says everything fits when nothing is late", async () => {
    const triage = await friday.q<{ late: Record<string, number> }>("triage")
    const { user } = await openFriday("/?triage")
    expect(await screen.findByRole("dialog", { name: "What gives when it can't all fit" })).toBeTruthy()
    if (Object.keys(triage.late).length) return
    expect(await screen.findByText("Everything fits", {}, { timeout: 15_000 })).toBeTruthy()
    expect(screen.getByText("Nothing is going late.")).toBeTruthy()
    expect(screen.getByRole("button", { name: /^Apply/ }).hasAttribute("disabled")).toBe(true)
    await user.click(screen.getByRole("button", { name: "Close" }))
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull())
  })

  it("with work going late, offers options best first, and applies the one you pick with an Undo", async () => {
    // a long piece of work, in as many sittings as it takes, due in two days: too much to fit, at any hour the test runs
    const due = `${dayOn(2)}T12:00`
    const made = await friday.c<{ result: { item: { id: number } } }>("add", { title: "Capstone report", duration_min: 1500, due, shape: "split" })
    const id = made.result.item.id
    let triage = await friday.q<{ late: Record<string, number>; options: { action: string; skip_title: string | null; late_hours_saved: number }[] }>("triage")
    for (const minutes of [2200, 3000, 4000, 5000]) {
      if (triage.options.some((o) => !o.skip_title && o.late_hours_saved > 0)) break
      await friday.c("edit", { id, duration_min: minutes })
      triage = await friday.q("triage")
    }
    const option = triage.options.find((o) => !o.skip_title && o.late_hours_saved > 0)
    expect(option, JSON.stringify(triage).slice(0, 400)).toBeTruthy()
    const { user } = await openFriday("/?triage")
    expect(await screen.findByText(/h of work won’t make it/, {}, { timeout: 20_000 })).toBeTruthy()
    expect(screen.getByText(/^Late now: .*Capstone report/)).toBeTruthy()
    expect(screen.getByText("Best options first. Pick one or combine them.")).toBeTruthy()
    expect(screen.getByText("Pick what gives")).toBeTruthy()
    expect(screen.getByText("Best fit")).toBeTruthy()
    const row = screen.getByRole("button", { name: new RegExp(option!.action.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")) })
    await user.click(row)
    expect(screen.getByText(/h late after these$/)).toBeTruthy()
    await user.click(row) // picked again: not picked
    expect(screen.getByText("Pick what gives")).toBeTruthy()
    await user.click(row)
    await user.click(screen.getByRole("button", { name: /^Apply/ }))
    await waitForSent("edit")
    await waitFor(() => expect(screen.queryByText(/h of work won’t make it/)).toBeNull())
    expect(await screen.findByText(option!.action)).toBeTruthy()
    await user.click(screen.getByRole("button", { name: "Undo" }))
    await waitForSent("undo")
    expect(await screen.findByText("Undone")).toBeTruthy()
    await waitFor(async () => expect((await friday.q<{ id: number; due: string }[]>("items")).find((i) => i.id === id)?.due).toBe(due), { timeout: 10_000 })
  }, 120_000)
})

// The AI's answer, given in the stand-in's place: the request still goes to Friday, and its answer is replaced.
type Action = { sentence: string; command: string; input: Record<string, unknown>; error?: string | null; event?: boolean }
let realFetch: typeof fetch | null = null // the page's own (setup.ts notes what it sends), taken when first replaced
function answerAs(answer: { reply: string; actions: Action[] } | { status: number; message: string }, delay = 0) {
  realFetch ??= window.fetch
  const real = realFetch
  const stand = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url
    if (!url.includes("/api/c/ask_claude")) return real(input, init)
    await real(input, { ...init, signal: undefined })
    if (delay)
      await new Promise<void>((done, fail) => {
        const timer = setTimeout(done, delay)
        init?.signal?.addEventListener("abort", () => (clearTimeout(timer), fail(new DOMException("Stopped", "AbortError"))))
      })
    if ("status" in answer) return new Response(JSON.stringify({ message: answer.message }), { status: answer.status, headers: { "content-type": "application/json" } })
    return new Response(JSON.stringify({ command_id: null, result: answer }), { headers: { "content-type": "application/json" } })
  }) as typeof fetch
  window.fetch = stand
  globalThis.fetch = stand
}
afterEach(() => {
  if (!realFetch) return
  window.fetch = realFetch
  globalThis.fetch = realFetch
})

/** What you want, typed in a box that may still hold a question stopped earlier (it comes back with the window). */
async function typeAsk(user: User, text: string) {
  const box = await screen.findByRole("textbox", { name: "What you want" })
  await user.clear(box)
  await user.type(box, text)
}

const movieNight = (): Action => {
  const day = dayOn(4)
  return { sentence: "Add Movie night on the calendar", command: "add", input: { title: "Movie night", when: "fixed", start: `${day}T20:00`, end: `${day}T22:00` }, event: true }
}

describe("Ask", () => {
  it("opens from the Plan menu with the box focused; Ask waits for words", async () => {
    const { user } = await openFriday("/")
    await fromPlanMenu(user, /^Ask /)
    const box = await screen.findByRole("textbox", { name: "What you want" })
    await waitFor(() => expect(document.activeElement).toBe(box))
    expect(screen.getByRole("button", { name: "Ask" }).hasAttribute("disabled")).toBe(true)
    expect(screen.getByText(/only proposes; nothing changes until you apply it/)).toBeTruthy()
    await user.keyboard("{Escape}")
    await waitFor(() => expect(screen.queryByRole("textbox", { name: "What you want" })).toBeNull())
  })

  it("sends what you typed, and says so when the AI has nothing to change", async () => {
    const { user } = await openFriday("/")
    await fromPlanMenu(user, /^Ask /)
    await typeAsk(user, "Move my gym to Thursday")
    await user.click(screen.getByRole("button", { name: "Ask" }))
    expect((await waitForSent("ask_claude")).body).toEqual({ text: "Move my gym to Thursday", purpose: "anything" })
    expect(await screen.findByText(/had no changes to suggest for this. Try saying it another way./, {}, { timeout: 10_000 })).toBeTruthy()
    await user.click(screen.getByRole("button", { name: "Ask again" }))
    expect(screen.getByRole("button", { name: "Ask" })).toBeTruthy()
  })

  it("lists what it would change, ticked, with what can't run unticked; Apply runs the ticked ones as one change", async () => {
    answerAs({
      reply: "Here's a movie night, and the moon stays where it is.",
      actions: [movieNight(), { sentence: "Move the moon", command: "edit", input: { id: 0 }, error: "Nothing is called the moon" }],
    })
    const { user } = await openFriday("/")
    await fromPlanMenu(user, /^Ask /)
    await typeAsk(user, "Plan a movie night")
    await user.keyboard("{Meta>}{Enter}{/Meta}")
    expect(await screen.findByText("Here's a movie night, and the moon stays where it is.", {}, { timeout: 10_000 })).toBeTruthy()
    expect(screen.getByText(/wants to$/)).toBeTruthy()
    const movie = screen.getByRole("button", { name: /Add Movie night on the calendar/ })
    const moon = screen.getByRole("button", { name: /Move the moon/ })
    expect(within(movie).getByRole("checkbox").getAttribute("aria-checked")).toBe("true")
    expect(moon.hasAttribute("disabled")).toBe(true)
    expect(screen.getByText("Nothing is called the moon")).toBeTruthy()
    expect((await screen.findAllByText(/Checking whether you have time…|you have time|late/)).length).toBeGreaterThan(0)
    await user.click(movie) // unticked: nothing to apply
    expect(screen.getByRole("button", { name: /^Apply/ }).hasAttribute("disabled")).toBe(true)
    await user.click(movie)
    await user.click(screen.getByRole("button", { name: /^Apply 1/ }))
    expect((await waitForSent("add")).body).toMatchObject({ title: "Movie night", when: "fixed" })
    expect(await screen.findByText("Applied 1 change")).toBeTruthy()
    await waitFor(() => expect(screen.queryByRole("textbox", { name: "What you want" })).toBeNull())
    await waitFor(async () => expect((await friday.q<{ title: string }[]>("events", { text: "Movie night" })).some((i) => i.title === "Movie night")).toBe(true))
    await user.click(screen.getByRole("button", { name: "Undo" }))
    await waitForSent("undo")
    await waitFor(async () => expect((await friday.q<{ title: string }[]>("events", { text: "Movie night" })).some((i) => i.title === "Movie night")).toBe(false))
  })

  it("with events changed without asking, applies an event at once, with its own Undo", async () => {
    answerAs({ reply: "", actions: [movieNight()] })
    const { user, client } = await openFriday("/")
    await fromPlanMenu(user, /^Ask /)
    const auto = await screen.findByRole("switch", { name: "Change calendar events without asking" })
    await user.click(auto)
    expect((await waitForSent("settings_set")).body).toMatchObject({ key: "claude", value: { events_without_asking: true } })
    await waitFor(async () => expect((await friday.q<{ claude: { events_without_asking: boolean } }>("settings")).claude.events_without_asking).toBe(true))
    await client.invalidateQueries({ queryKey: ["settings"] }) // what Friday's live updates do in a browser
    await waitFor(() => expect(screen.getByRole("switch", { name: "Change calendar events without asking" }).getAttribute("aria-checked")).toBe("true"))
    expect(screen.getByText(/Changes to calendar events apply at once; the rest wait for you./)).toBeTruthy()
    await typeAsk(user, "Movie night on Saturday")
    await user.click(screen.getByRole("button", { name: "Ask" }))
    expect(await screen.findByText("Done: a change to your calendar", {}, { timeout: 10_000 })).toBeTruthy()
    expect(await screen.findByText("Changed an event without asking")).toBeTruthy()
    await user.click(screen.getByRole("button", { name: "Undo the change made" }))
    await waitForSent("undo")
    await waitFor(() => expect(screen.queryByText("Done: a change to your calendar")).toBeNull())
    expect(screen.getByRole("button", { name: /^Apply 1/ })).toBeTruthy() // taken back: yours to apply again
    await user.click(screen.getByRole("switch", { name: "Change calendar events without asking" }))
    expect((await waitForSent("settings_set")).body).toMatchObject({ key: "claude", value: { events_without_asking: false } })
    await waitFor(async () => expect((await friday.q<{ claude: { events_without_asking: boolean } }>("settings")).claude.events_without_asking).toBe(false))
    await client.invalidateQueries({ queryKey: ["settings"] })
    await user.click(screen.getByRole("button", { name: "Discard" }))
    await waitFor(() => expect(screen.queryByRole("textbox", { name: "What you want" })).toBeNull())
  })

  it("counts the seconds while it thinks, and stops waiting when you say", async () => {
    answerAs({ reply: "Too late", actions: [] }, 10_000)
    const { user } = await openFriday("/")
    await fromPlanMenu(user, /^Ask /)
    await typeAsk(user, "Something slow")
    await user.click(screen.getByRole("button", { name: "Ask" }))
    expect(await screen.findByText(/^Asking .*… \d+s$/)).toBeTruthy()
    await user.click(screen.getByRole("button", { name: "Stop" }))
    expect(await screen.findByRole("button", { name: "Ask" })).toBeTruthy()
    expect(screen.queryByText("Too late")).toBeNull()
  })

  it("closed while it thinks, says when the answer comes and opens on it", async () => {
    answerAs({ reply: "A quiet week ahead.", actions: [] }, 800)
    const { user } = await openFriday("/")
    await fromPlanMenu(user, /^Ask /)
    await typeAsk(user, "How does my week look")
    await user.click(screen.getByRole("button", { name: "Ask" }))
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Close" }))
    expect(await screen.findByText(/answered “How does my week look”/, {}, { timeout: 15_000 })).toBeTruthy()
    await user.click(screen.getByRole("button", { name: "See it" }))
    expect(await screen.findByText("A quiet week ahead.", {}, { timeout: 5000 })).toBeTruthy()
  })

  it("says what went wrong when the AI couldn't answer", async () => {
    answerAs({ status: 400, message: "The AI isn't set up yet" })
    const { user } = await openFriday("/")
    await fromPlanMenu(user, /^Ask /)
    await typeAsk(user, "Anything")
    await user.click(screen.getByRole("button", { name: "Ask" }))
    expect(await screen.findByText("The AI isn't set up yet", {}, { timeout: 10_000 })).toBeTruthy()
  })

  it("asks from search, with what you typed there", async () => {
    const { user } = await openFriday("/")
    await user.keyboard("{Meta>}k{/Meta}")
    await user.type(await screen.findByRole("textbox", { name: "Search" }), "free up friday")
    await user.click(await screen.findByRole("button", { name: /^Ask .*: free up friday/ }))
    expect(((await screen.findByRole("textbox", { name: "What you want" })) as HTMLTextAreaElement).value).toBe("free up friday")
  })
})
