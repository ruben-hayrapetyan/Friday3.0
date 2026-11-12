// Google Tasks through a script in your own Google account (C130): what the Google Tasks box gives you to paste into
// script.google.com, with a key made for this Friday. Deployed as a Web app, it answers Friday's requests
// (src/friday/integrations/google_tasks.py, Script): check, read, done, reopen. Plain Apps Script (V8), using the
// Google Tasks API service you add in the editor. Kept short and readable: people paste it into their own account.

const STORE = "friday.googleTasksKey"

/** This Friday's key for the script: made once and kept, so the box opened again gives the same script. */
export function scriptKey(storage: Pick<Storage, "getItem" | "setItem"> = localStorage): string {
  const kept = storage.getItem(STORE)
  if (kept && /^[\w-]{20,}$/.test(kept)) return kept
  const bytes = crypto.getRandomValues(new Uint8Array(24))
  const made = btoa(String.fromCharCode(...bytes)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "")
  storage.setItem(STORE, made)
  return made
}

/** What Friday keeps as the token: the Web app link and the key ("<link>#<key>"). */
export function scriptToken(link: string, key: string): string {
  return `${link.trim()}#${key}`
}

export const SCRIPT_LINK = /^https:\/\/script\.google\.com\/(?:a\/macros\/[\w.-]+|macros)\/s\/[\w-]{20,}\/exec(?:\?.*)?$/

export function tasksScript(key: string): string {
  return `// Friday ↔ Google Tasks. This runs in your own Google account, only for you. Friday sends the key below with
// each request; without it the script does nothing. It reads your open tasks, and ticks (or unticks) one you finish
// (or reopen) in Friday. Nothing else is read or changed, and nothing is sent anywhere but back to Friday.
const KEY = "${key}";

function doPost(e) {
  var ask;
  try {
    ask = JSON.parse(e.postData.contents);
  } catch (error) {
    return answer({ error: "unreadable" });
  }
  if (!ask || ask.key !== KEY) return answer({ error: "key" });
  // the Google Tasks API service, added in the editor (Services +)
  if (typeof Tasks === "undefined") return answer({ error: "Tasks is not defined" });
  try {
    if (ask.op === "check") return answer({ ok: true, v: 1, account: Session.getEffectiveUser().getEmail(), lists: lists().length });
    if (ask.op === "read") return answer({ ok: true, v: 1, lists: lists().map(function (l) { return { id: l.id, title: l.title, tasks: open(l.id) }; }) });
    if (ask.op === "done") return change(ask, { status: "completed" });
    if (ask.op === "reopen") return change(ask, { status: "needsAction", completed: null });
    return answer({ error: "op" });
  } catch (error) {
    return answer({ error: String((error && error.message) || error) });
  }
}

// Opening the link in a browser shows that it's there, and nothing else.
function doGet() {
  return answer({ ok: true, v: 1, friday: "Google Tasks script" });
}

function lists() {
  return every(function (options) { return Tasks.Tasklists.list(options); }, {});
}

function open(list) {
  return every(function (options) { return Tasks.Tasks.list(list, options); }, { showCompleted: false, showHidden: false })
    .filter(function (t) { return t.status !== "completed" && !t.deleted; })
    .map(function (t) { return { id: t.id, title: t.title, notes: t.notes, due: t.due, status: t.status, webViewLink: t.webViewLink }; });
}

function change(ask, body) {
  Tasks.Tasks.patch(body, ask.list, ask.task);
  return answer({ ok: true });
}

function every(fetch, options) {
  var found = [];
  var page = null;
  for (var n = 0; n < 100; n++) {
    var asked = { maxResults: 100 };
    for (var k in options) asked[k] = options[k];
    if (page) asked.pageToken = page;
    var got = fetch(asked);
    found = found.concat(got.items || []);
    page = got.nextPageToken;
    if (!page) break;
  }
  return found;
}

function answer(body) {
  return ContentService.createTextOutput(JSON.stringify(body)).setMimeType(ContentService.MimeType.JSON);
}
`
}
