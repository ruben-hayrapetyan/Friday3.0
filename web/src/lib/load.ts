// Days that hold more than your usual, said plainly (15 Nov: a client's Load ahead said "The week of Mon 9 holds 1.0 h
// more than you can do" and its button said "Everything fits. Nothing is going late."): what's planned, how far past
// your usual it is, and whether anything will be late, which is a different question.

/** Hours as said: "16 h", "1.5 h", to the tenth and no ".0". */
export function hoursSaid(hours: number): string {
  return `${tenth(hours)} h`
}

const tenth = (hours: number) => Math.round(hours * 10) / 10

/** "Mon 9's week: 16 h planned, 1 h past your usual 15 h. Nothing will be late." `late`: how many things will be late,
 * anywhere in the plan. */
export function overSentence(label: string, planned: number, usual: number, late: number): string {
  const lateWords = late === 0 ? "Nothing will be late." : late === 1 ? "1 thing will be late." : `${late} things will be late.`
  // the gap from the numbers as said, so the three add up
  return `${label}: ${hoursSaid(planned)} planned, ${hoursSaid(tenth(planned) - tenth(usual))} past your usual ${hoursSaid(usual)}. ${lateWords}`
}

/** "Mon 9's week", for a week starting on `start` (YYYY-MM-DD). */
export function weekLabel(start: string, weekday: (date: string) => string): string {
  return `${weekday(start)} ${Number(start.slice(8, 10))}’s week`
}
