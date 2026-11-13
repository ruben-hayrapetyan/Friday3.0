// Keeping Tab inside an open dialog (the audit, 12 Nov: the integration panel had no focus trap, so Tab walked out of
// it into the page behind). Dialogs.tsx's useDialogKeys uses it, so every dialog built on that keeps the keys alike.

const FOCUSABLE = [
  "a[href]",
  "area[href]",
  "button",
  "input:not([type=hidden])",
  "select",
  "textarea",
  "summary",
  "iframe",
  "[tabindex]",
  "[contenteditable='']",
  "[contenteditable='true']",
].join(", ")

/** What Tab can reach inside `box`, in the page's order: not disabled, not hidden, inert or folded away in a closed
 * <details>, not taken out of the order with tabindex -1. A step the browser would skip, left in, would let Tab out. */
export function tabbable(box: HTMLElement): HTMLElement[] {
  return [...box.querySelectorAll<HTMLElement>(FOCUSABLE)].filter(
    (el) =>
      (el.tabIndex >= 0 || opensDetails(el)) &&
      !el.matches(":disabled") &&
      !el.closest("[hidden], [inert], fieldset:disabled") &&
      !foldedAway(el) &&
      (el.checkVisibility?.() ?? true),
  )
}

function foldedAway(el: HTMLElement): boolean {
  const closed = el.closest("details:not([open])")
  return !!closed && !(opensDetails(el) && el.parentElement === closed)
}

/** A <details>' own summary is a tab stop, whatever tabIndex a page without layout says (happy-dom says -1). */
function opensDetails(el: HTMLElement): boolean {
  return el.tagName === "SUMMARY" && el.parentElement?.tagName === "DETAILS" && !el.hasAttribute("tabindex")
}

/** Where Tab (Shift-Tab when `back`) takes the focus from `at`, one of `items` or null when the focus isn't on any of
 * them (outside the dialog, or on the dialog itself): round from the last to the first and the first to the last, in
 * from outside, "box" to stay on a dialog with nothing to reach, or null where the browser's own step stays inside. */
export function tabTarget<T>(items: readonly T[], at: T | null, back: boolean): T | "box" | null {
  if (!items.length) return "box"
  const first = items[0]
  const last = items[items.length - 1]
  if (at === null) return back ? last : first
  if (back && at === first) return last
  if (!back && at === last) return first
  return null
}

/** A Tab pressed while `box` is open keeps the focus inside it. */
export function keepTabInside(e: KeyboardEvent, box: HTMLElement): void {
  if (e.key !== "Tab" || e.defaultPrevented) return
  const items = tabbable(box)
  const active = document.activeElement as HTMLElement | null
  const to = tabTarget(items, active && items.includes(active) ? active : null, e.shiftKey)
  if (to === null) return
  e.preventDefault()
  ;(to === "box" ? box : to).focus({ preventScroll: to === "box" })
}

/** Whether the focus is in another dialog, opened over `box` (search over a panel, say): that one has the keys. */
export function inAnotherDialog(box: HTMLElement): boolean {
  const other = (document.activeElement as HTMLElement | null)?.closest?.("[aria-modal='true']")
  return !!other && other !== box
}
