// The integrations gallery (PROGRESS.md C96, 10 Nov: "each integration is a box in which you can click into it and
// then you can search the boxes by name (similar to the way that anthropic does plugins for claude)"). Your layout:
// what you've connected on top, then each category; search across all; a box opens a panel over the gallery. This
// file is the catalog and its search, kept plain so it's tested on its own (gallery.test.ts).

export type Category = "Calendars" | "Mail" | "To-do apps" | "School" | "AI" | "Files"

export const CATEGORIES: Category[] = ["Calendars", "To-do apps", "School", "Mail", "AI", "Files"]

export interface Entry {
  id: string
  name: string
  category: Category
  line: string // what it brings, in one line
  aliases: string[] // other names people search for it by
  icon: string // a Phosphor icon; services' own logos aren't ours to use
  hue: string // its tile's colour
  token?: { page: string; label: string; steps: string[] } // connected by pasting a token (integrations/*)
}

export const CATALOG: Entry[] = [
  {
    id: "mac-calendars",
    name: "Calendars on this Mac",
    category: "Calendars",
    line: "Every calendar your Mac has: iCloud, Google, Outlook, your school's",
    aliases: ["apple calendar", "icloud", "google calendar", "outlook", "exchange", "ical"],
    icon: "calendar-dots",
    hue: "#5b8def",
  },
  {
    id: "calendar-links",
    name: "Calendar links",
    category: "Calendars",
    line: "Any calendar's private link: Canvas, your school, a team",
    aliases: ["ics", "ical", "webcal", "feed", "canvas feed", "subscribe", "course feeds"],
    icon: "rss",
    hue: "#e0884f",
  },
  {
    id: "google",
    name: "Google Calendar",
    category: "Calendars",
    line: "Google's own connection, for a Google Cloud key of your own",
    aliases: ["gcal", "google"],
    icon: "google-logo",
    hue: "#4285f4",
  },
  {
    id: "gmail",
    name: "Gmail",
    category: "Mail",
    line: "New mail read for deadlines and events, into your Inbox",
    aliases: ["google mail", "email", "app password"],
    icon: "envelope-simple",
    hue: "#d9534f",
  },
  {
    id: "todoist",
    name: "Todoist",
    category: "To-do apps",
    line: "Your Todoist to-dos planned into your week; done goes both ways",
    aliases: ["todo", "to-do", "tasks", "doist"],
    icon: "check-square",
    hue: "#e44332",
    token: {
      page: "https://app.todoist.com/app/settings/integrations/developer",
      label: "Todoist API token",
      steps: [
        "Open Todoist's Settings → Integrations → Developer (the link below).",
        "Copy the API token shown there.",
        "Paste it here and press Connect.",
      ],
    },
  },
  {
    id: "syllabus",
    name: "Syllabus upload",
    category: "School",
    line: "A syllabus becomes classes, readings, assignments and exam prep",
    aliases: ["pdf", "course", "canvas page", "upload", "document"],
    icon: "file-pdf",
    hue: "#8a6fd1",
  },
  {
    id: "ai",
    name: "AI",
    category: "AI",
    line: "Reads syllabi and mail, and rules Friday can't read itself",
    aliases: ["claude", "openai", "gpt", "chatgpt", "gemini", "grok", "muse", "ollama", "api key", "llm"],
    icon: "sparkle",
    hue: "#c98a2b",
  },
  {
    id: "ask-ai",
    name: "Ask the AI",
    category: "AI",
    line: "Say what you want in your own words; changes proposed to keep or not",
    aliases: ["ask claude", "chat", "assistant", "command"],
    icon: "chat-circle-text",
    hue: "#3f9e8f",
  },
]

/** Lower case, accents gone: "Calendrier" finds "calendrier". */
export function folded(text: string): string {
  return text.normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase()
}

/** The entries every word of `text` begins a word of (in its name, other names, category or line), best first:
 * a name that starts with what you typed, then one containing it, then the rest. */
export function search(entries: Entry[], text: string): Entry[] {
  const words = folded(text).split(/[^a-z0-9-]+/).filter(Boolean)
  if (!words.length) return entries
  const scored = entries
    .map((e) => {
      const name = folded(e.name)
      const haystack = folded([e.name, ...e.aliases, e.category, e.line].join(" "))
      const starts = (w: string) => new RegExp(`(^|[^a-z0-9])${w.replace(/[-]/g, "\\-")}`).test(haystack)
      if (!words.every(starts)) return null
      const joined = words.join(" ")
      const rank = name.startsWith(joined) ? 0 : name.includes(joined) ? 1 : 2
      return { e, rank }
    })
    .filter((x): x is { e: Entry; rank: number } => x !== null)
  return scored.sort((a, b) => a.rank - b.rank).map((x) => x.e)
}

/** Your layout: what you've connected first, then each category's (in CATEGORIES' order), empty ones left out. */
export function grouped(entries: Entry[], connected: Set<string>): { connected: Entry[]; sections: [Category, Entry[]][] } {
  const mine = entries.filter((e) => connected.has(e.id))
  const rest = entries.filter((e) => !connected.has(e.id))
  const sections = CATEGORIES.map((c) => [c, rest.filter((e) => e.category === c)] as [Category, Entry[]]).filter(([, list]) => list.length)
  return { connected: mine, sections }
}
