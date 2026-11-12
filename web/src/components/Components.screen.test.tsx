// The shared pieces on their own: what shows when a page breaks (and that Friday is told), the toasts, a time typed
// the way you'd say it, a due date counting down, an estimate nudged while you work, and the small controls.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { type ReactNode, useState } from "react"
import { describe, expect, it } from "vitest"
import { ShellProvider } from "@/shell/ShellContext"
import { friday, waitForSent } from "@/test/friday"
import { DueLabel } from "./DueLabel"
import { EstimateNudge } from "./EstimateNudge"
import { ErrorBoundary } from "./ErrorBoundary"
import { Check, Chip, Menu, Seg, Switch } from "./fr/controls"
import { Dropdown, MenuRow } from "./fr/Dropdown"
import { DateTimeInput, TimeInput } from "./fr/TimeInput"
import { Toasts, useToast } from "./Toasts"

function today(): string {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
}

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return (
    <QueryClientProvider client={client}>
      <Toasts>
        <ShellProvider today={today()}>{children}</ShellProvider>
      </Toasts>
    </QueryClientProvider>
  )
}

function Bomb({ armed }: { armed: boolean }): ReactNode {
  if (armed) throw new Error("The calendar fell over")
  return <span>All is well</span>
}

describe("a page that breaks", () => {
  it("says so, tells Friday, and tries again on asking", async () => {
    const user = userEvent.setup()
    const quiet = console.error
    console.error = () => {}
    try {
      function Page() {
        const [armed, setArmed] = useState(true)
        return (
          <>
            <button onClick={() => setArmed(false)}>Mend it</button>
            <ErrorBoundary>
              <Bomb armed={armed} />
            </ErrorBoundary>
          </>
        )
      }
      render(<Page />)
      expect(screen.getByRole("alert")).toBeTruthy()
      expect(screen.getByText("Something on this page broke")).toBeTruthy()
      expect(screen.getByText("Nothing you saved is lost. Friday noted what happened so it can be fixed.")).toBeTruthy()
      expect(screen.getByText("The calendar fell over")).toBeTruthy()
      expect(screen.getByRole("button", { name: "Back to the plan" })).toBeTruthy()
      const report = await waitForSent("report")
      expect(report.body).toMatchObject({ message: "The calendar fell over" })
      await user.click(screen.getByRole("button", { name: "Mend it" }))
      await user.click(screen.getByRole("button", { name: "Try again" }))
      expect(screen.getByText("All is well")).toBeTruthy()
    } finally {
      console.error = quiet
    }
  })

  it("tries again by itself on another page, and the whole window offers no way back to the plan", async () => {
    const quiet = console.error
    console.error = () => {}
    try {
      const { rerender } = render(
        <ErrorBoundary resetKey="/todo">
          <Bomb armed />
        </ErrorBoundary>,
      )
      expect(screen.getByText("Something on this page broke")).toBeTruthy()
      rerender(
        <ErrorBoundary resetKey="/inbox">
          <Bomb armed={false} />
        </ErrorBoundary>,
      )
      expect(screen.getByText("All is well")).toBeTruthy()
      rerender(
        <ErrorBoundary resetKey="/inbox" whole>
          <Bomb armed />
        </ErrorBoundary>,
      )
      expect(screen.queryByRole("button", { name: "Back to the plan" })).toBeNull()
      expect(screen.getByRole("button", { name: "Reload" })).toBeTruthy()
    } finally {
      console.error = quiet
    }
  })

  it("Back to the plan goes to the plan", async () => {
    const user = userEvent.setup()
    const quiet = console.error
    console.error = () => {}
    window.location.hash = "#/inbox"
    try {
      render(
        <ErrorBoundary>
          <Bomb armed={window.location.hash === "#/inbox"} />
        </ErrorBoundary>,
      )
      await user.click(screen.getByRole("button", { name: "Back to the plan" }))
      expect(window.location.hash).toBe("#/")
    } finally {
      console.error = quiet
    }
  })
})

describe("the toasts", () => {
  function Say({ toast }: { toast: Parameters<ReturnType<typeof useToast>>[0] }) {
    const show = useToast()
    return <button onClick={() => show(toast)}>Say it</button>
  }

  it("show what happened with its Undo, which runs once and goes", async () => {
    const user = userEvent.setup()
    const ran: number[] = []
    render(<Say toast={{ message: "Moved essay", action: { label: "Undo", run: () => ran.push(1) } }} />, { wrapper })
    await user.click(screen.getByRole("button", { name: "Say it" }))
    expect(screen.getByText("Moved essay")).toBeTruthy()
    await user.click(screen.getByRole("button", { name: "Undo" }))
    expect(ran).toEqual([1])
    expect(screen.queryByText("Moved essay")).toBeNull()
  })

  it("an error stays until dismissed or a while has passed", async () => {
    const user = userEvent.setup()
    render(<Say toast={{ message: "Friday said no", tone: "error" }} />, { wrapper })
    await user.click(screen.getByRole("button", { name: "Say it" }))
    expect(screen.getByText("Friday said no")).toBeTruthy()
    await user.click(screen.getByRole("button", { name: "Dismiss" }))
    expect(screen.queryByText("Friday said no")).toBeNull()
  })

  it("keep the newest three, and go by themselves", async () => {
    const user = userEvent.setup()
    function Many() {
      const show = useToast()
      const [n, setN] = useState(0)
      return <button onClick={() => (show({ message: `Toast ${n + 1}` }), setN(n + 1))}>Another</button>
    }
    render(<Many />, { wrapper })
    for (let i = 0; i < 4; i++) await user.click(screen.getByRole("button", { name: "Another" }))
    expect(screen.queryByText("Toast 1")).toBeNull()
    for (const n of [2, 3, 4]) expect(screen.getByText(`Toast ${n}`)).toBeTruthy()
    await waitFor(() => expect(screen.queryByText("Toast 4")).toBeNull(), { timeout: 7000 })
  }, 15_000)
})

describe("a time box", () => {
  function Timed({ start = "", expect: hint }: { start?: string; expect?: Parameters<typeof TimeInput>[0]["expect"] }) {
    const [value, setValue] = useState(start)
    return (
      <>
        <TimeInput value={value} onChange={setValue} label="Starts" step={900} expect={hint} />
        <span>Set to “{value}”</span>
      </>
    )
  }

  it("reads a time typed the way you'd say it, when you leave the box", async () => {
    const user = userEvent.setup()
    render(<Timed start="09:00" />)
    const box = screen.getByRole("textbox", { name: "Starts" }) as HTMLInputElement
    expect(box.value).toBe("9am")
    await user.clear(box)
    await user.type(box, "1130")
    await user.tab()
    expect(screen.getByText("Set to “11:30”")).toBeTruthy()
    await user.clear(box)
    await user.type(box, "noon")
    await user.tab()
    expect(screen.getByText("Set to “12:00”")).toBeTruthy()
    await user.clear(box)
    await user.type(box, "7:45p")
    await user.tab()
    expect(screen.getByText("Set to “19:45”")).toBeTruthy()
  })

  it("marks what it can't read, puts the time back on Escape, and clears when emptied", async () => {
    const user = userEvent.setup()
    render(<Timed start="09:00" />)
    const box = screen.getByRole("textbox", { name: "Starts" }) as HTMLInputElement
    await user.clear(box)
    await user.type(box, "banana")
    expect(box.getAttribute("aria-invalid")).toBe("true")
    expect(box.title).toBe("Type a time, like 9:30, 11pm or noon")
    await user.keyboard("{Escape}")
    expect(box.value).toBe("9am")
    await user.clear(box)
    await user.tab()
    expect(screen.getByText("Set to “”")).toBeTruthy()
  })

  it("steps by its step with the arrow keys, and Enter sets what's typed", async () => {
    const user = userEvent.setup()
    render(<Timed start="10:10" />)
    const box = screen.getByRole("textbox", { name: "Starts" }) as HTMLInputElement
    await user.click(box)
    await user.keyboard("{ArrowUp}")
    expect(box.value).toBe("10:15am")
    await user.keyboard("{ArrowUp}{ArrowDown}{ArrowDown}")
    expect(box.value).toBe("10am")
    await user.keyboard("{Enter}")
    expect(screen.getByText("Set to “10:00”")).toBeTruthy()
  })

  it("an empty box starts its arrows near what it expects", async () => {
    const user = userEvent.setup()
    render(<Timed expect={{ near: "18:00" }} />)
    const box = screen.getByRole("textbox", { name: "Starts" }) as HTMLInputElement
    await user.click(box)
    await user.keyboard("{ArrowUp}")
    expect(box.value).toBe("6:15pm")
  })

  it("beside a date, makes a day and a time; a day with no time is at the end of it", async () => {
    function Due() {
      const [value, setValue] = useState<string | null>(null)
      return (
        <>
          <DateTimeInput value={value} onChange={setValue} label="Due" />
          <span>Due “{value ?? "none"}”</span>
        </>
      )
    }
    const user = userEvent.setup()
    render(<Due />)
    fireEvent.change(screen.getByLabelText("Due day"), { target: { value: "2026-12-01" } })
    expect(screen.getByText("Due “2026-12-01T23:59”")).toBeTruthy()
    const time = screen.getByRole("textbox", { name: "Due time" })
    await user.clear(time)
    await user.type(time, "5pm")
    await user.tab()
    expect(screen.getByText("Due “2026-12-01T17:00”")).toBeTruthy()
    await user.clear(time)
    await user.tab()
    expect(screen.getByText("Due “2026-12-01T23:59”")).toBeTruthy()
    fireEvent.change(screen.getByLabelText("Due day"), { target: { value: "" } })
    expect(screen.getByText("Due “none”")).toBeTruthy()
  })
})

describe("a due date", () => {
  it("says when it's due, counts down today, and turns to over once past", () => {
    const d = today()
    render(
      <>
        <DueLabel due="2099-01-01T12:00" />
        <DueLabel due={`${d}T00:01`} prefix="By " />
        <DueLabel due={`${d}T00:01`} routine />
      </>,
      { wrapper },
    )
    expect(screen.getByText(/^Due /)).toBeTruthy()
    expect(screen.getAllByText(/over|ago|late/).length + screen.getAllByText("not recorded").length).toBeGreaterThan(0)
    expect(screen.getByText("not recorded")).toBeTruthy()
  })
})

describe("an estimate, nudged", () => {
  it("adds and takes quarter hours on the spot, and saves them together", async () => {
    const made = await friday.c<{ result: { item: { id: number } } }>("add", { title: "Nudge practice", duration_min: 60, due: "2099-01-01T23:59" })
    const id = made.result.item.id
    const user = userEvent.setup()
    render(<EstimateNudge itemId={id} runningMin={10} />, { wrapper })
    const text = await screen.findByTestId("estimate-text")
    expect(text.textContent).toMatch(/1h expected · 50m left/)
    await user.click(screen.getByRole("button", { name: "30 minutes more" }))
    await user.click(screen.getByRole("button", { name: "60 minutes more" }))
    await user.click(screen.getByRole("button", { name: "15 minutes less" }))
    expect(screen.getByTestId("estimate-text").textContent).toMatch(/2h 15m expected|2h15m expected|2¼/)
    expect((await waitForSent("edit", 4000)).body).toEqual({ id, duration_min: 135 })
  })
})

describe("the small controls", () => {
  it("a segmented control presses the one picked", async () => {
    const user = userEvent.setup()
    function Picker() {
      const [v, setV] = useState<string>("Steady")
      return <Seg options={["Easy", "Steady", { value: "Push", label: "Push hard" }]} value={v} onPick={setV} label="Pace" />
    }
    render(<Picker />)
    expect(screen.getByRole("button", { name: "Steady" }).getAttribute("aria-pressed")).toBe("true")
    await user.click(screen.getByRole("button", { name: "Push hard" }))
    expect(screen.getByRole("button", { name: "Push hard" }).getAttribute("aria-pressed")).toBe("true")
  })

  it("a dropdown menu lists its options, picks one, and closes on Escape or a click away", async () => {
    const user = userEvent.setup()
    function Pick() {
      const [v, setV] = useState("a")
      return (
        <>
          <Menu options={[{ value: "a", label: "Apples" }, { value: "b", label: "Bananas" }]} value={v} onPick={setV} label="Fruit" />
          <span>Outside</span>
        </>
      )
    }
    render(<Pick />)
    const button = screen.getByRole("button", { name: "Fruit" })
    await user.click(button)
    expect(button.getAttribute("aria-expanded")).toBe("true")
    expect(screen.getByRole("option", { name: "Apples" }).getAttribute("aria-selected")).toBe("true")
    await user.click(screen.getByRole("option", { name: "Bananas" }))
    expect(screen.queryByRole("listbox")).toBeNull()
    expect(button.textContent).toContain("Bananas")
    await user.click(button)
    await user.keyboard("{Escape}")
    expect(screen.queryByRole("listbox")).toBeNull()
    await user.click(button)
    await user.click(screen.getByText("Outside"))
    expect(screen.queryByRole("listbox")).toBeNull()
  })

  it("a switch, a check and a chip each say whether they're on", async () => {
    const user = userEvent.setup()
    function All() {
      const [on, setOn] = useState(false)
      return (
        <>
          <Switch on={on} onToggle={() => setOn(!on)} label="Dark" />
          <Check done={on} onToggle={() => setOn(!on)} />
          <Chip on={on} onClick={() => setOn(!on)} swatch="red">
            Red
          </Chip>
        </>
      )
    }
    render(<All />)
    await user.click(screen.getByRole("switch", { name: "Dark" }))
    expect(screen.getByRole("switch", { name: "Dark" }).getAttribute("aria-checked")).toBe("true")
    expect(screen.getByRole("checkbox", { name: "Mark not done" }).getAttribute("aria-checked")).toBe("true")
    expect(screen.getByRole("button", { name: "Red" }).getAttribute("aria-pressed")).toBe("true")
    await user.click(screen.getByRole("checkbox", { name: "Mark not done" }))
    await user.click(screen.getByRole("button", { name: "Red" }))
    expect(screen.getByRole("switch", { name: "Dark" }).getAttribute("aria-checked")).toBe("true")
  })

  it("a button's panel opens below it and closes on a row, Escape or a click away", async () => {
    const user = userEvent.setup()
    const picked: string[] = []
    render(
      <>
        <Dropdown icon="sparkle" label="Plan" wide>
          {(close) => <MenuRow icon="gauge" label="Pace" note="Push harder or ease off" onClick={() => (picked.push("pace"), close())} />}
        </Dropdown>
        <span>Elsewhere</span>
      </>,
      { wrapper },
    )
    const button = screen.getByRole("button", { name: "Plan" })
    await user.click(button)
    expect(screen.getByText("Push harder or ease off")).toBeTruthy()
    await user.click(screen.getByRole("button", { name: /^Pace/ }))
    expect(picked).toEqual(["pace"])
    expect(screen.queryByText("Push harder or ease off")).toBeNull()
    await user.click(button)
    await user.keyboard("{Escape}")
    expect(screen.queryByText("Push harder or ease off")).toBeNull()
    await user.click(button)
    fireEvent.pointerDown(screen.getByText("Elsewhere"))
    await waitFor(() => expect(screen.queryByText("Push harder or ease off")).toBeNull())
  })
})
