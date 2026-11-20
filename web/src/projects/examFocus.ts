// Exam focus in words, shared by an exam's popup and New exam: how many days before an exam only its class's work is
// planned (0: its own day, until it starts).

export const FOCUS = [0, 1, 2, 3, 5, 7]
const daysWord = (d: number) => (d === 1 ? "the day" : `${d} days`)
/** "on its day, until it starts", "the day before", "3 days before" (19 Nov: an exam's own day). */
export const focusWords = (d: number) => (d === 0 ? "on its day, until it starts" : `${daysWord(d)} before`)
export const capital = (s: string) => s.replace(/^./, (c) => c.toUpperCase())

export type FocusPick = number | "none" | "rule"

/** The choices for an exam's focus: as your rule gives it (`ruleDays`, None when the rule isn't for it), off, or its
 * own days. `ruleOn`: whether you have a rule at all, to say why "As your other exams" is none. */
export function focusChoices(ruleDays: number | null | undefined, ruleOn: boolean) {
  const rule = ruleDays != null
    ? `${capital(focusWords(ruleDays))}, from your rule in Rules`
    : ruleOn
      ? "Other classes go on as usual: your rule in Rules isn't for exams named so"
      : "Other classes go on as usual (no rule in Rules)"
  return [
    { value: "rule" as FocusPick, label: "As your other exams", desc: rule },
    { value: "none" as FocusPick, label: "Off", desc: "Other classes go on as usual" },
    ...FOCUS.map((d) => ({ value: d as FocusPick, label: capital(focusWords(d)), desc: "Only the exam's class is planned then" })),
  ]
}

/** What a pick comes to: its days, or none. */
export const focusOf = (pick: FocusPick, ruleDays: number | null | undefined): number | null =>
  pick === "rule" ? (ruleDays ?? null) : pick === "none" ? null : pick
