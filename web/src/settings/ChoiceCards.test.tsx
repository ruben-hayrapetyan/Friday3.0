import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it } from "vitest"
import { HoursArt } from "./appearanceArt"
import { ChoiceCards } from "./ChoiceCards"

describe("choice cards", () => {
  const html = renderToStaticMarkup(
    <ChoiceCards
      label="Hours shown"
      value="All day"
      onPick={() => {}}
      choices={[
        { value: "Waking", label: "Waking hours", art: <HoursArt hours="Waking" /> },
        { value: "All day", label: "All 24 hours", art: <HoursArt hours="All day" /> },
      ]}
    />,
  )
  it("is a labelled group of buttons, one per choice, with its short name", () => {
    expect(html).toMatch(/role="group" aria-label="Hours shown"/)
    expect(html.match(/<button/g)).toHaveLength(2)
    expect(html).toContain("Waking hours")
    expect(html).toContain("All 24 hours")
  })
  it("presses only the chosen card, and hides its picture from screen readers", () => {
    expect(html.match(/aria-pressed="true"/g)).toHaveLength(1)
    expect(html.match(/aria-pressed="false"/g)).toHaveLength(1)
    expect(html.indexOf('aria-pressed="true"')).toBeGreaterThan(html.indexOf("Waking hours"))
    expect(html).toMatch(/aria-hidden="true"/)
  })
})
