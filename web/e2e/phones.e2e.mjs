// Phone pairing (tests/features.toml: phones), in Settings → Phone: the switch makes Friday answer on this Mac's
// Tailscale address and says where; Pair a phone shows a one-time QR code; a phone paired with it is listed, and
// Remove forgets it; off again, Friday answers on this Mac alone. Needs this Mac on Tailscale for the pairing; without
// it the page's own words for that are checked instead.

const phone = async (q) => await q("phone_status")
const waitFor = async (check, ms = 10_000) => {
  for (const end = Date.now() + ms; Date.now() < end; await new Promise((r) => setTimeout(r, 250))) {
    const found = await check()
    if (found) return found
  }
  return null
}

export default [
  {
    name: "off, the page says Friday answers on this Mac alone and lists no phone",
    async run({ open, has, q, expect }) {
      expect((await phone(q)).on === false, "the sample starts with the phone on")
      await open("/settings/phone")
      await has("Off: Friday answers on this Mac alone.")
      await has("No phone yet.")
    },
  },
  {
    name: "on, it says where; Pair a phone shows a code a phone pairs with, listed until Remove",
    async run({ open, has, gone, click, q, c, expect, until }) {
      await open("/settings/phone")
      await click("Use Friday on my phone")
      expect(await waitFor(async () => (await phone(q)).on), "the switch didn't turn the phone on on the server")
      expect((await q("settings")).phone.on === true, "the setting isn't on")
      const status = await phone(q)
      const where = status.name ?? status.address
      if (!where) {
        await has("This Mac isn't on Tailscale.")
        console.log("      (this Mac isn't on Tailscale: pairing not tried)")
        return
      }
      await has(`On at ${where}. Your Mac must be awake for your phone to reach it.`)
      await click("Pair a phone")
      await until(`!!document.querySelector("[aria-label='Pairing code to scan'] svg")`, 10_000, "the QR code")
      await has("Works once, for 10 minutes.")
      await click("Hide the code")
      await has("Pair a phone")
      // a phone scanning the code: its camera opens the link with the code after the #, on the tailnet address
      const { url } = (await c("phone_pair")).result
      expect(url.startsWith(`http://${where}:`) && url.includes("/pair#"), `the code's link is ${url}`)
      // the port Friday serves on here, not the link's (see the BUG test below): never another Friday on this Mac
      const there = `http://${where}:${await until("location.port")}`
      const code = url.split("/pair#")[1]
      let paired
      for (let i = 0; i < 40 && !paired; i++) {
        paired = await fetch(`${there}/api/pair`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ code, device: "E2E iPhone" }) }).then((r) => r.ok, () => false)
        if (!paired) await new Promise((r) => setTimeout(r, 500))
      }
      expect(paired, "a phone couldn't pair with the code")
      const again = await fetch(`${there}/api/pair`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ code, device: "E2E iPad" }) })
      expect(!again.ok, "the code worked twice")
      await has("E2E iPhone", "main", 15_000)
      await has("not opened yet")
      expect((await phone(q)).phones.map((p) => p.name).join() === "E2E iPhone", "the server lists other phones")
      await click("Remove")
      await has("No phone yet.")
      await gone("E2E iPhone", "main")
      expect((await phone(q)).phones.length === 0, "Remove didn't forget the phone on the server")
    },
  },
  {
    name: "off again, Friday answers on this Mac alone; a phone removed twice is refused",
    async run({ open, has, click, q, request, expect }) {
      await open("/settings/phone")
      if ((await phone(q)).on) await click("Use Friday on my phone")
      await has("Off: Friday answers on this Mac alone.")
      expect(await waitFor(async () => !(await phone(q)).on), "the phone is still on on the server")
      const refused = await request("POST", "/api/c/phone_pair", {})
      expect(refused.status === 422 && refused.body.message.includes("Switch on Use Friday on my phone first"), `pairing while off: ${JSON.stringify(refused)}`)
      const gone = await request("POST", "/api/c/phone_forget", { id: "nope" })
      expect(gone.status === 422, `forgetting no phone: ${JSON.stringify(gone)}`)
    },
  },
  {
    name: "the pairing link names the port Friday was started on, not the one in Settings (fixed 24 Nov)",
    async run({ c, q, until, expect }) {
      // 24 Nov: `fridayd serve --port N` (or `demo --port N`) answers on the tailnet on port N
      // (server/main.py's TailnetListener), but phone_pair's link is built from settings' server.port (8765), so a
      // phone scanning it opens whatever answers on 8765, not this Friday. Expected: the link's port is N.
      await c("phone_set", { on: true })
      const status = await q("phone_status")
      if (!(status.name ?? status.address)) return await c("phone_set", { on: false })
      const { url } = (await c("phone_pair")).result
      await c("phone_set", { on: false })
      expect(new URL(url.replace("/pair#", "/pair?")).port === (await until("location.port")), `the link is ${url}`)
    },
  },
]
