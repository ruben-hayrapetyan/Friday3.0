import { describe, expect, it } from "vitest"
import { shouldOffer } from "./PasskeyOffer"

describe("the bar offering a passkey inside Friday (H94)", () => {
  it("shows when a hosted Friday offers and this window can make passkeys", () => {
    expect(shouldOffer({ offer_passkey: true }, true)).toBe(true)
  })
  it("doesn't show once this browser has one or said Not now", () => {
    expect(shouldOffer({ offer_passkey: false }, true)).toBe(false)
  })
  it("doesn't show in the Mac app's window, which can't make passkeys", () => {
    expect(shouldOffer({ offer_passkey: true }, false)).toBe(false)
  })
  it("doesn't show on your own Friday, where nobody is signed in", () => {
    expect(shouldOffer(null, true)).toBe(false)
    expect(shouldOffer({}, true)).toBe(false)
  })
})
