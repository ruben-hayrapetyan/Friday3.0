// The integrations gallery (PROGRESS.md C96, 10 Nov: "each integration is a box in which you can click into it and
// then you can search the boxes by name (similar to the way that anthropic does plugins for claude)"). Your layout:
// what you've connected on top, then each category; search across all; a box opens a panel over the gallery. This
// file is the catalog and its search, kept plain so it's tested on its own (gallery.test.ts).

export type Category = "Calendars" | "Mail" | "Messages" | "To-do apps" | "School" | "Work schedules" | "AI" | "Files"

export const CATEGORIES: Category[] = ["Calendars", "To-do apps", "School", "Work schedules", "Mail", "Messages", "AI", "Files"]

/** Something else connecting asks for beside the token (Jira: your site, your email). */
export interface TokenField {
  key: string
  label: string
  placeholder: string
  type?: "email" | "text"
}

export interface Entry {
  id: string
  name: string
  category: Category
  line: string // what it brings, in one line
  aliases: string[] // other names people search for it by
  icon: string // a Phosphor icon; services' own logos aren't ours to use
  hue: string // its tile's colour
  // connected by pasting a token (integrations/*); `page` "" when the server knows it (Trello's carries Friday's key)
  // `pageText`: the link's words when the page is help rather than the token page itself (Canvas's is your school's)
  token?: { page: string; label: string; steps: string[]; note?: string; fields?: TokenField[]; pageText?: string }
  link?: { help: string; steps: string[]; reads: string } // connected by the calendar link it publishes (C96)
  viaMac?: { help: string; steps: string[] } // reaches Friday through the Mac's calendars (no link of its own)
  mail?: { provider: "icloud" | "yahoo" | "fastmail" | "other"; help?: string; steps: string[] } // by app password (C99)
  onMac?: { steps: string[] } // read by Friday's Mac app itself, no account or token: macOS asks (C100)
  signIn?: { steps: string[]; note?: string } // connected by signing in on the service's own page (C109)
}

// Mail beyond Gmail by app password (C99; servers and steps from each provider's help, 10 Nov). Outlook.com isn't
// here: Microsoft no longer lets an app password read its mail, so it comes with Microsoft's own sign-in.
const MAIL: Entry[] = [
  {
    id: "icloud-mail", name: "iCloud Mail", category: "Mail", icon: "cloud", hue: "#3a8ee6",
    line: "New mail read for deadlines and events, into your Inbox", aliases: ["apple", "me.com", "mac.com", "email"],
    mail: { provider: "icloud", help: "https://support.apple.com/en-us/102525", steps: [
      "Sign in at account.apple.com → Sign-In and Security → App-Specific Passwords (two-factor authentication must be on).",
      "Make one called Friday and copy it.",
      "Type your full iCloud address and paste the password here.",
    ] },
  },
  {
    id: "yahoo-mail", name: "Yahoo Mail", category: "Mail", icon: "envelope-open", hue: "#6b2fd0",
    line: "New mail read for deadlines and events, into your Inbox", aliases: ["yahoo", "aol", "email"],
    mail: { provider: "yahoo", help: "https://help.yahoo.com/kb/SLN15241.html", steps: [
      "Open Yahoo's Account Security page and choose Generate app password.",
      "Name it Friday and copy the password Yahoo shows (it's shown once).",
      "Type your full Yahoo address and paste the password here.",
    ] },
  },
  {
    id: "fastmail", name: "Fastmail", category: "Mail", icon: "envelope-simple-open", hue: "#2b5d9e",
    line: "New mail read for deadlines and events, into your Inbox", aliases: ["email"],
    mail: { provider: "fastmail", help: "https://www.fastmail.help/hc/en-us/articles/1500000279961-Setting-up-K-9-Mail", steps: [
      "In Fastmail, open Settings → Privacy & Security → App passwords and make a new one for mail (not on the Basic plan).",
      "Copy it.",
      "Type your full address and paste the password here.",
    ] },
  },
  {
    id: "other-mail", name: "Other mail (IMAP)", category: "Mail", icon: "at", hue: "#6e7a8c",
    line: "Any mail server that speaks IMAP: your school's, your own domain's", aliases: ["imap", "email", "school mail", "work mail"],
    mail: { provider: "other", steps: [
      "Find your provider's IMAP server name in its help (like imap.example.com; it must use SSL, port 993).",
      "Make an app password there if it has them; otherwise your password.",
      "Type the server, your address and the password here.",
    ] },
  },
]

// The steps are each service's own, from its help pages (10 Nov); menu names vary a little between schools.
const SCHOOL_READS = "Its due dates come to your Inbox, as a Canvas feed's do: assignments and exams by their words."
const SHIFT_READS = "Your shifts go straight in as fixed work time, and move when your manager changes the schedule."
const LINKS: Entry[] = [
  {
    id: "blackboard", name: "Blackboard", category: "School", icon: "chalkboard-teacher", hue: "#3c5a99",
    line: "Due dates from Blackboard's calendar", aliases: ["learn", "ultra", "bb", "lms"],
    link: { help: "https://help.blackboard.com/Learn/Student/Ultra/Tools/Calendar", reads: SCHOOL_READS, steps: [
      "In Blackboard, open Calendar from the menu on the left.",
      "Open the calendar's settings and choose Share Calendar (or “Get External Calendar Link”).",
      "Copy the link (it ends in .ics) and paste it here.",
    ] },
  },
  {
    id: "moodle", name: "Moodle", category: "School", icon: "graduation-cap", hue: "#e07b20",
    line: "Due dates from Moodle's calendar", aliases: ["lms", "course"],
    link: { help: "https://docs.moodle.org/en/Calendar_export", reads: SCHOOL_READS, steps: [
      "In Moodle, open the Calendar and click Export calendar (or Import or export calendars) at the bottom.",
      "Choose All events and “Recent and next 60 days”.",
      "Click Get calendar URL, copy the link and paste it here (not Export, which is a one-time file).",
    ] },
  },
  {
    id: "brightspace", name: "Brightspace", category: "School", icon: "student", hue: "#2d8c7e",
    line: "Due dates from Brightspace (D2L)'s calendar", aliases: ["d2l", "desire2learn", "lms"],
    link: { help: "https://community.d2l.com/brightspace/kb/articles/18115-calendar", reads: SCHOOL_READS, steps: [
      "In Brightspace, open the Calendar tool (from your homepage or a course).",
      "Click Subscribe (some schools first ask you to turn on calendar feeds in its Settings).",
      "Copy the link shown (not the feed.ics download, which never updates) and paste it here.",
    ] },
  },
  {
    id: "schoology", name: "Schoology", category: "School", icon: "backpack", hue: "#0b75b5",
    line: "Due dates from Schoology's calendar", aliases: ["powerschool", "lms", "high school"],
    link: { help: "https://docs.powerschool.com/SGYH/instructors/personal-account/calendar", reads: SCHOOL_READS, steps: [
      "In Schoology, click the arrow by your name at the top right and choose Account Settings.",
      "Under sharing your Schoology calendar, click Enable.",
      "Copy the link under “Use this iCal link” and paste it here.",
    ] },
  },
  {
    id: "wheniwork", name: "When I Work", category: "Work schedules", icon: "clock-user", hue: "#51a33d",
    line: "Your shifts from When I Work, kept up to date", aliases: ["shifts", "schedule", "wiw"],
    link: { help: "https://help.wheniwork.com/articles/syncing-your-schedule-to-a-calendar-app-computer", reads: SHIFT_READS, steps: [
      "Log in to When I Work on the web (the phone app's sync adds shifts to the phone only).",
      "Open Calendar Sync and copy the My Schedule link.",
      "Paste it here.",
    ] },
  },
  {
    id: "deputy", name: "Deputy", category: "Work schedules", icon: "identification-badge", hue: "#2f6fd1",
    line: "Your rostered shifts from Deputy", aliases: ["roster", "shifts", "schedule"],
    link: { help: "https://help.deputy.com/hc/en-au/articles/4688796818703", reads: SHIFT_READS, steps: [
      "Open Deputy on the web and go to your profile.",
      "Copy the calendar sync link (your employer has to have calendar sync turned on).",
      "Paste it here.",
    ] },
  },
  {
    id: "7shifts", name: "7shifts", category: "Work schedules", icon: "fork-knife", hue: "#f0663a",
    line: "Your restaurant shifts from 7shifts", aliases: ["seven shifts", "restaurant", "schedule"],
    link: { help: "https://kb.7shifts.com/hc/en-us/articles/4861793532691", reads: SHIFT_READS, steps: [
      "Log in to 7shifts on the web, open Schedules and click Tools.",
      "Choose calendar sync and copy your personal link (it's yours alone: don't share it).",
      "Paste it here.",
    ] },
  },
  {
    id: "sling", name: "Sling", category: "Work schedules", icon: "calendar-check", hue: "#6b4fd6",
    line: "Your shifts from Sling", aliases: ["toast", "schedule", "shifts"],
    link: { help: "https://support.getsling.com/en/articles/6062972-calendar-sync", reads: SHIFT_READS, steps: [
      "Open Sling on the web (the phone app can't make the link), go to Schedule.",
      "Click the calendar sync icon at the top right and copy the link (Premium and Business plans).",
      "Paste it here.",
    ] },
  },
  {
    id: "homebase", name: "Homebase", category: "Work schedules", icon: "house-line", hue: "#e5484d",
    line: "Your Homebase shifts, through your phone's calendar", aliases: ["schedule", "shifts"],
    viaMac: { help: "https://support.joinhomebase.com/hc/en-us/articles/360022479511-Calendar-Sync", steps: [
      "Homebase puts shifts in your phone's calendar rather than giving a link.",
      "In the Homebase app: More → Settings → Calendar Sync → Enable, and pick a calendar that syncs to this Mac (iCloud or Google).",
      "Friday then reads your shifts through Calendars on this Mac, with nothing else to connect.",
    ] },
  },
]

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
    id: "notion",
    name: "Notion",
    category: "To-do apps",
    line: "Your Notion to-do databases planned into your week; done goes both ways",
    aliases: ["database", "databases", "todo", "to-do", "tasks", "notes", "wiki"],
    icon: "notebook",
    hue: "#8c7b6b",
    token: {
      page: "https://www.notion.so/developers/tokens",
      label: "Notion personal access token",
      steps: [
        "Open Notion's Personal access tokens page (the link below) and press New token.",
        "Name it Friday, tick Notion API, and choose 1 year (the longest it lasts).",
        "Press Create token, copy it (Notion shows it only once), paste it here and press Connect.",
        "Then choose which of your to-do lists Friday reads, right here.",
      ],
      note: "On Free and Business plans only workspace owners can make one unless an admin allows it. An integration's secret works too: Friday then reads only the databases you add it to (••• → Connections).",
    },
  },
  {
    id: "trello",
    name: "Trello",
    category: "To-do apps",
    line: "The Trello cards you're on planned into your week; done goes both ways",
    aliases: ["cards", "boards", "kanban", "atlassian", "todo", "to-do", "tasks"],
    icon: "kanban",
    hue: "#3f7fc4",
    token: {
      page: "",
      label: "Trello token",
      steps: [
        "Open Trello's Allow page (the link below), signing in to Trello if it asks.",
        "Press Allow: Trello shows a long token.",
        "Copy it, paste it here and press Connect.",
      ],
      note: "Friday reads the open cards you're on, on every board. To bring one in, join it in Trello (open the card and press Join, or hover it and press space). Finishing it in Friday ticks its due date complete.",
    },
  },
  {
    id: "asana",
    name: "Asana",
    category: "To-do apps",
    line: "Your Asana My tasks planned into your week; done goes both ways",
    aliases: ["my tasks", "projects", "work", "todo", "to-do", "tasks"],
    icon: "circles-three",
    hue: "#e8736b",
    token: {
      page: "https://app.asana.com/0/my-apps",
      label: "Asana personal access token",
      steps: [
        "Open Asana's developer console (the link below) and press Create new token.",
        "Name it Friday, agree to Asana's API terms, and press Create token.",
        "Copy the token (Asana shows it only once), paste it here and press Connect.",
      ],
      note: "Friday reads the open tasks assigned to you, in every workspace you're in: your My tasks. They come in as Work tasks.",
    },
  },
  {
    id: "linear",
    name: "Linear",
    category: "To-do apps",
    line: "The Linear issues assigned to you planned into your week; done goes both ways",
    aliases: ["issues", "tickets", "engineering", "sprint", "cycle", "work", "tasks"],
    icon: "line-segments",
    hue: "#7b7fd8",
    token: {
      page: "https://linear.app/settings/account/security",
      label: "Linear personal API key",
      steps: [
        "Open Linear's Security & access settings (the link below).",
        "Under Personal API keys press New API key, name it Friday, and give it read and write access if Linear asks.",
        "Copy the key, paste it here and press Connect.",
      ],
      note: "Friday reads the open issues assigned to you, as Work tasks. Finishing one in Friday moves it to your team's Done state.",
    },
  },
  {
    id: "jira",
    name: "Jira",
    category: "To-do apps",
    line: "The Jira issues assigned to you planned into your week; done goes both ways",
    aliases: ["atlassian", "issues", "tickets", "sprint", "scrum", "work", "tasks", "jira cloud"],
    icon: "kanban",
    hue: "#3d7be0",
    token: {
      page: "https://id.atlassian.com/manage-profile/security/api-tokens",
      label: "Atlassian API token",
      steps: [
        "Open Atlassian's API tokens page (the link below) and press Create API token.",
        "Name it Friday, choose how long it lasts (a year is the longest), and press Create.",
        "Copy the token, paste it here with your Jira site and email, and press Connect.",
      ],
      fields: [
        { key: "site", label: "Your Jira site", placeholder: "yourteam.atlassian.net" },
        { key: "email", label: "The email you sign in to Jira with", placeholder: "you@company.com", type: "email" },
      ],
      note: "Jira Cloud only. Friday reads the open issues assigned to you, as Work tasks; finishing one in Friday moves it to Done through your project's own workflow.",
    },
  },
  {
    id: "github",
    name: "GitHub",
    category: "To-do apps",
    line: "Issues assigned to you and reviews asked of you, planned into your week",
    aliases: ["issues", "pull requests", "prs", "reviews", "code", "repos", "developer", "git"],
    icon: "github-logo",
    hue: "#6e7681",
    token: {
      page: "https://github.com/settings/personal-access-tokens/new",
      label: "GitHub fine-grained token",
      steps: [
        "Open GitHub's new fine-grained token page (the link below).",
        "Name it Friday, choose when it expires (up to a year), and under Repository access choose All repositories.",
        "Under Permissions add Issues and Pull requests, both Read-only.",
        "Press Generate token, copy it, paste it here and press Connect.",
      ],
      note: "Friday only reads GitHub: close an issue there (or merge the pull request that closes it) and it's done here. Reviews asked of you come in as “Review: …”. An organization may need to approve the token before its repositories show.",
    },
  },
  {
    id: "microsoft_todo",
    name: "Microsoft To Do",
    category: "To-do apps",
    line: "Your To Do lists planned into your week; done goes both ways",
    aliases: ["microsoft", "to do", "todo", "outlook tasks", "wunderlist", "office 365", "tasks"],
    icon: "microsoft-outlook-logo",
    hue: "#2f7ed8",
    signIn: {
      steps: [
        "Press Sign in with Microsoft: Microsoft's page opens in your browser.",
        "Choose your account (Outlook.com, Hotmail, or your school's or work's) and press Accept.",
        "Come back to Friday: the open tasks of every To Do list come to your Inbox to review together.",
      ],
      note: "Some schools and workplaces let only an administrator approve new apps; Microsoft's page says so if yours does.",
    },
  },
  {
    id: "google_tasks",
    name: "Google Tasks",
    category: "To-do apps",
    line: "Your Google Tasks planned into your week; done goes both ways",
    aliases: ["google", "todo", "to-do", "tasks"],
    icon: "check-square-offset",
    hue: "#4285f4",
    signIn: {
      steps: [
        "Press Sign in with Google: Google's page opens and asks to let Friday see and change your tasks.",
        "Back in Friday, choose the account to read Google Tasks from.",
        "The open tasks of every list come to your Inbox to review together.",
      ],
      note: "It uses the same Google sign-in as your calendars and Gmail; signing in again keeps Tasks allowed.",
    },
  },
  {
    id: "ticktick",
    name: "TickTick",
    category: "To-do apps",
    line: "Your TickTick lists planned into your week; done goes both ways",
    aliases: ["tick tick", "dida", "todo", "to-do", "tasks"],
    icon: "check-fat",
    hue: "#4772fa",
    signIn: {
      steps: [
        "Press Sign in with TickTick: TickTick's page opens in your browser.",
        "Sign in if it asks, then press Authorize.",
        "Come back to Friday: the open tasks of your Inbox and every list come to your Inbox to review together.",
      ],
      note: "TickTick's sign-in lasts about six months; when it runs out, this box asks you to sign in again.",
    },
  },
  {
    id: "reminders",
    name: "Apple Reminders",
    category: "To-do apps",
    line: "Your reminders planned into your week; done goes both ways",
    aliases: ["reminders", "apple", "icloud", "todo", "to-do", "tasks", "siri"],
    icon: "list-checks",
    hue: "#e8913a",
    onMac: {
      steps: [
        "Press Connect: nothing to copy, no account to sign in to.",
        "macOS asks once whether Friday may see your reminders. Press Allow.",
        "Your open reminders, from every list, come to your Inbox to review together.",
      ],
    },
  },
  {
    id: "canvas",
    name: "Canvas",
    category: "School",
    line: "Assignments and quizzes with exact times; done ticks Canvas's To Do",
    aliases: ["canvas api", "instructure", "lms", "assignments", "homework", "quizzes", "school"],
    icon: "student",
    hue: "#d9534f",
    token: {
      page: "https://community.canvaslms.com/t5/Student-Guide/How-do-I-manage-API-access-tokens-as-a-student/ta-p/273",
      pageText: "Canvas's own help on this",
      label: "Canvas access token",
      steps: [
        "In Canvas, open Account → Settings.",
        "Under Approved Integrations press New Access Token, write Friday as its purpose, and press Generate Token.",
        "Copy the token (Canvas shows it only once), paste it here with your school's Canvas address, and press Connect.",
      ],
      fields: [{ key: "site", label: "Your school's Canvas address", placeholder: "canvas.yourschool.edu" }],
      note: "If there's no New Access Token button, your school has turned tokens off: use your Canvas calendar feed under Calendar links instead. Once connected, Canvas's assignments come from here, and your Canvas calendar feed keeps bringing only its events. Finishing one in Friday ticks it in Canvas's To Do, which only you see; nothing is submitted.",
    },
  },
  {
    id: "things",
    name: "Things",
    category: "To-do apps",
    line: "Your Things to-dos planned into your week; done goes both ways",
    aliases: ["things 3", "cultured code", "todo", "to-do", "tasks", "gtd"],
    icon: "check-circle",
    hue: "#4a90d9",
    onMac: {
      steps: [
        "Have Things 3 on this Mac, then press Connect: nothing to copy, no account.",
        "macOS asks once whether Friday may control Things. Press OK.",
        "Your to-dos in Inbox, Today, Upcoming and Anytime come to your Inbox to review together; Someday stays out.",
        "A Things deadline is the deadline; a When date alone is the day you meant to do it, which Friday can move.",
      ],
    },
  },
  ...LINKS,
  ...MAIL,
  {
    id: "outlook_mail",
    name: "Outlook",
    category: "Mail",
    line: "New mail read for deadlines and events, into your Inbox",
    aliases: ["outlook.com", "hotmail", "live.com", "office 365", "microsoft 365", "exchange", "email", "microsoft"],
    icon: "envelope-open",
    hue: "#2f7ed8",
    signIn: {
      steps: [
        "Press Sign in with Microsoft: Microsoft's page opens in your browser.",
        "Choose your Outlook.com, Hotmail, school or work account and press Accept: Friday asks only to read mail.",
        "Come back to Friday: new mail is read as Gmail's is, its deadlines and events waiting in your Inbox.",
      ],
      note: "Nothing is sent, moved, deleted or marked read. Some schools and workplaces let only an administrator approve new apps.",
    },
  },
  {
    id: "slack",
    name: "Slack",
    category: "Messages",
    line: "Messages that mention you, waiting in your Inbox to decide on",
    aliases: ["mentions", "chat", "messages", "workspace", "dm"],
    icon: "slack-logo",
    hue: "#7d4a8f",
    signIn: {
      steps: [
        "Press Sign in with Slack: Slack's page opens in your browser.",
        "Choose your workspace and press Allow: Friday asks only to search for what mentions you.",
        "Come back to Friday: messages from the last two weeks that mention you wait in your Inbox, each one yours to keep as a to-do or not.",
      ],
      note: "Friday can't post, react or read anything else. Slack has retired reminders for apps, so your /remind reminders can't come in.",
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
