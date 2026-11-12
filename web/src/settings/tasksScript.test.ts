// The Google Tasks script (C130), run against stand-ins for Apps Script's services: it answers Friday's protocol
// (src/friday/integrations/google_tasks.py and its stand-in tests/integrations/fake_tasks_script.py) and does
// nothing without its key.
import { describe, expect, it } from "vitest"
import { SCRIPT_LINK, scriptKey, scriptToken, tasksScript } from "./tasksScript"

type Task = { id: string; title: string; status: string; due?: string; notes?: string; webViewLink?: string; deleted?: boolean }

function appsScript(key: string, opts: { lists?: { id: string; title: string }[]; tasks?: Record<string, Task[]>; noService?: boolean; page?: number } = {}) {
  const lists = opts.lists ?? [{ id: "L1", title: "My Tasks" }]
  const tasks = opts.tasks ?? { L1: [{ id: "T1", title: "Buy milk", status: "needsAction", due: "2026-10-22T00:00:00.000Z" }] }
  const patched: unknown[] = []
  const size = opts.page ?? 100
  const paged = <T,>(all: T[], o: { pageToken?: string; maxResults: number }) => {
    const start = Number(o.pageToken ?? 0)
    const end = start + Math.min(size, o.maxResults)
    return { items: all.slice(start, end), ...(end < all.length ? { nextPageToken: String(end) } : {}) }
  }
  const Tasks = {
    Tasklists: { list: (o: { pageToken?: string; maxResults: number }) => paged(lists, o) },
    Tasks: {
      list: (list: string, o: { pageToken?: string; maxResults: number; showCompleted: boolean }) => {
        expect(o.showCompleted).toBe(false)
        return paged(tasks[list] ?? [], o)
      },
      patch: (body: unknown, list: string, task: string) => patched.push([body, list, task]),
    },
  }
  const ContentService = { MimeType: { JSON: "json" }, createTextOutput: (text: string) => ({ setMimeType: () => text }) }
  const Session = { getEffectiveUser: () => ({ getEmail: () => "maria@gmail.com" }) }
  const run = new Function("Tasks", "ContentService", "Session", `${tasksScript(key)}\nreturn { doPost, doGet };`)
  const { doPost, doGet } = opts.noService
    ? run(undefined, ContentService, Session)
    : run(Tasks, ContentService, Session)
  const post = (body: unknown) => JSON.parse(doPost({ postData: { contents: JSON.stringify(body) } }))
  return { post, doGet: () => JSON.parse(doGet()), patched }
}

describe("the Google Tasks script", () => {
  it("does nothing without its key", () => {
    const s = appsScript("good-key-0123456789abcdef")
    expect(s.post({ key: "other", op: "read" })).toEqual({ error: "key" })
    expect(s.post({ op: "done", list: "L1", task: "T1" })).toEqual({ error: "key" })
    expect(s.patched).toEqual([])
  })

  it("checks, reads every list's open tasks over pages, and ticks and unticks", () => {
    const key = "good-key-0123456789abcdef"
    const many = Array.from({ length: 7 }, (_, i) => ({ id: `T${i}`, title: `Task ${i}`, status: "needsAction" }))
    const s = appsScript(key, {
      lists: [{ id: "L1", title: "My Tasks" }, { id: "L2", title: "Groceries" }],
      tasks: { L1: many, L2: [{ id: "G1", title: "Eggs", status: "completed" }, { id: "G2", title: "Bread", status: "needsAction", deleted: true }] },
      page: 3,
    })
    expect(s.post({ key, op: "check" })).toEqual({ ok: true, v: 1, account: "maria@gmail.com", lists: 2 })
    const read = s.post({ key, op: "read" })
    expect(read.lists.map((l: { id: string; tasks: Task[] }) => [l.id, l.tasks.length])).toEqual([["L1", 7], ["L2", 0]])
    expect(s.post({ key, op: "done", list: "L1", task: "T3" })).toEqual({ ok: true })
    expect(s.post({ key, op: "reopen", list: "L1", task: "T3" })).toEqual({ ok: true })
    expect(s.patched).toEqual([[{ status: "completed" }, "L1", "T3"], [{ status: "needsAction", completed: null }, "L1", "T3"]])
    expect(s.post({ key, op: "delete" })).toEqual({ error: "op" })
  })

  it("says when the Tasks service wasn't added, as Friday reads it", () => {
    const key = "good-key-0123456789abcdef"
    expect(appsScript(key, { noService: true }).post({ key, op: "check" })).toEqual({ error: "Tasks is not defined" })
  })

  it("shows only that it's there when opened in a browser", () => {
    expect(appsScript("good-key-0123456789abcdef").doGet()).toEqual({ ok: true, v: 1, friday: "Google Tasks script" })
  })
})

describe("the script's key and link", () => {
  it("is made once and kept", () => {
    const kept = new Map<string, string>()
    const storage = { getItem: (k: string) => kept.get(k) ?? null, setItem: (k: string, v: string) => void kept.set(k, v) }
    const key = scriptKey(storage)
    expect(key).toMatch(/^[\w-]{32}$/)
    expect(scriptKey(storage)).toBe(key)
  })

  it("knows a Web app link, and keeps it with the key", () => {
    expect(SCRIPT_LINK.test("https://script.google.com/macros/s/AKfycbz-stand-in-deployment-id_0123456789/exec")).toBe(true)
    expect(SCRIPT_LINK.test("https://script.google.com/a/macros/cornell.edu/s/AKfycbz-stand-in-deployment-id_0123456789/exec")).toBe(true)
    expect(SCRIPT_LINK.test("https://script.google.com/macros/s/AKfycbz-stand-in-deployment-id_0123456789/dev")).toBe(false)
    expect(scriptToken(" https://script.google.com/macros/s/x/exec \n", "k")).toBe("https://script.google.com/macros/s/x/exec#k")
  })
})
