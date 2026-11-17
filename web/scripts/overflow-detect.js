// Finds text or boxes painting outside the box they sit in: run in the page (overflow-check.mjs sends it). Returns a
// list of findings, each { kind, where, text, by }.
(() => {
  const SLACK = 1.5 // px: subpixel rounding
  const findings = []
  const seen = new Set()
  const css = (el) => getComputedStyle(el)
  const transparent = (c) => !c || c === "transparent" || /rgba\([^)]*,\s*0\)$/.test(c) || /\/\s*0\)$/.test(c)
  const hasBox = (s) => !transparent(s.backgroundColor) || (s.boxShadow && s.boxShadow !== "none") || ["Top", "Right", "Bottom", "Left"].some((e) => parseFloat(s[`border${e}Width`]) > 0 && s[`border${e}Style`] !== "none" && !transparent(s[`border${e}Color`]))
  const clips = (s) => s.overflowX !== "visible" || s.overflowY !== "visible"
  const scrolls = (s) => /auto|scroll/.test(s.overflowX + s.overflowY)
  // drawn at all: not hidden, not see-through, and not in a closed <details> (its content keeps a layout box)
  const shown = (el) => {
    const r = el.getBoundingClientRect()
    if (r.width < 1 || r.height < 1) return false
    if (el.checkVisibility) return el.checkVisibility({ contentVisibilityAuto: true, opacityProperty: true, visibilityProperty: true })
    const s = css(el)
    return s.visibility !== "hidden" && parseFloat(s.opacity) > 0.01 && !el.closest("details:not([open]) > :not(summary)")
  }
  const name = (el) => {
    const parts = []
    for (let e = el; e && e !== document.body && parts.length < 4; e = e.parentElement) {
      const label = e.getAttribute("aria-label") || e.getAttribute("data-integration") || e.getAttribute("role")
      parts.unshift(e.tagName.toLowerCase() + (e.className && typeof e.className === "string" ? "." + e.className.trim().split(/\s+/).slice(0, 2).join(".") : "") + (label ? `[${label}]` : ""))
    }
    return parts.join(" > ")
  }
  const words = (el) => (el.innerText || el.textContent || "").replace(/\s+/g, " ").trim().slice(0, 90)
  const report = (kind, el, by, extra = "") => {
    const key = kind + "|" + name(el) + "|" + words(el)
    if (seen.has(key)) return
    seen.add(key)
    findings.push({ kind, where: name(el), text: words(el), by: by + extra })
  }
  // An element's own decoration that's meant to sit outside (a badge, a focus ring) is absolutely placed: only flowed
  // content is held to its box.
  const placed = (s) => s.position === "absolute" || s.position === "fixed"
  // The box an element is drawn in: its nearest ancestor with a background, border or shadow; and whether something
  // between scrolls (then the scroll area is its box) or the element is placed.
  function container(el) {
    for (let e = el.parentElement; e && e !== document.documentElement; e = e.parentElement) {
      const s = css(e)
      if (scrolls(s)) return { box: e, scroll: true }
      if (hasBox(s) || clips(s)) return { box: e, scroll: false, clip: clips(s) }
      if (placed(s)) return null // a popover's own content: checked against the popover's box, if it has one, above
    }
    return null
  }
  // whether a line crosses the box's edge, rather than lying wholly inside or out
  const straddles = (r, box) => (r.left < box.left - SLACK && r.right > box.left + SLACK) || (r.right > box.right + SLACK && r.left < box.right - SLACK) || (r.top < box.top - SLACK && r.bottom > box.top + SLACK) || (r.bottom > box.bottom + SLACK && r.top < box.bottom - SLACK)
  const ellipsized = (el, box) => {
    for (let e = el; e; e = e.parentElement) {
      if (css(e).textOverflow === "ellipsis" || (css(e).webkitLineClamp && css(e).webkitLineClamp !== "none")) return true
      if (e === box) return false
    }
    return false
  }
  const outside = (inner, outer) => Math.max(outer.top - inner.top, inner.bottom - outer.bottom, outer.left - inner.left, inner.right - outer.right)
  // 1. text and boxes past the edge of their box
  const all = document.body.querySelectorAll("*")
  for (const el of all) {
    if (!shown(el)) continue
    const s = css(el)
    if (placed(s) || s.display === "contents") continue
    if (el.closest("[data-overflow-ok], svg, canvas")) continue
    const holder = container(el)
    if (!holder) continue
    const outer = holder.box.getBoundingClientRect()
    let edge = outer
    if (holder.scroll) {
      // inside a scroll area only sideways spill is wrong (a row wider than its list); down is what scrolling is for
      const r = el.getBoundingClientRect()
      const past = r.right - (outer.left + holder.box.clientWidth + (holder.box.clientLeft || 0))
      const before = outer.left - r.left
      if (css(holder.box).overflowX !== "visible" && /auto|scroll/.test(css(holder.box).overflowX)) continue // sideways scrolling on purpose
      if (Math.max(past, before) > SLACK && holder.box.scrollWidth > holder.box.clientWidth + 1) report("past the side of its scroll area", el, `${Math.round(Math.max(past, before))}px`)
      continue
    }
    // text: each run of words, not the element (a fixed-height box's text paints past it while the element doesn't).
    // A line cut part way is wrong; a line wholly out of a box that cuts (a short block's second line) is that box
    // showing what fits, as calendars do; text that ends in an ellipsis says it goes on. An element that cuts its own
    // words (overflow: hidden) is their first box, and the box it sits in, if that cuts too, the second (a title
    // ending in "…" in a chip squeezed to a sliver is still cut).
    const own = clips(s) ? { box: el, clip: true } : holder
    const ownEdge = own.box.getBoundingClientRect()
    const boxes = [[own, ownEdge], ...(own !== holder && holder.clip ? [[holder, edge]] : [])]
    for (const node of el.childNodes) {
      if (node.nodeType !== 3 || !node.textContent.trim()) continue
      const dots = own.clip && ellipsized(el, own.box) // ends in "…" sideways; cut top or bottom is still cut
      const range = document.createRange()
      range.selectNodeContents(node)
      const size = parseFloat(css(el).fontSize)
      for (const line of range.getClientRects()) {
        if (line.width < 1) continue
        // the letters themselves, not the line box round them: a one-line block 10px tall shows 11px text whole
        const ink = Math.min(line.height, size * 0.8)
        const across = dots ? { left: Math.max(line.left, ownEdge.left), right: Math.min(line.right, ownEdge.right) } : line
        const r = { left: across.left, right: across.right, top: line.top + (line.height - ink) / 2, bottom: line.bottom - (line.height - ink) / 2 }
        const cut = boxes.find(([b, e]) => outside(r, e) > SLACK && (!b.clip || straddles(r, e)))
        if (!cut) continue
        report(cut[0].clip ? "text cut by its box" : "text past its box", el, `${Math.round(outside(r, cut[1]))}px`, ` (box: ${name(cut[0].box)})`)
        break
      }
    }
    if (el.children.length === 0 && el.childNodes.length === 0) continue
    const by = outside(el.getBoundingClientRect(), edge)
    if (by > SLACK && hasBox(s) && (!holder.clip || straddles(el.getBoundingClientRect(), edge))) report(holder.clip ? "box cut by its container" : "box past its container", el, `${Math.round(by)}px`, ` (container: ${name(holder.box)})`)
  }
  // 2. a scrolling column that would squeeze its rows (WebKit shrinks flex items to a miscounted height, 14 Nov: the
  // Google card's last lines under the next card): a flex column that scrolls, overflowing, with rows free to shrink
  for (const el of all) {
    if (!shown(el)) continue
    const s = css(el)
    if (!/flex/.test(s.display) || !s.flexDirection.startsWith("column") || !/auto|scroll/.test(s.overflowY)) continue
    if (el.scrollHeight <= el.clientHeight + 1) continue
    for (const child of el.children) {
      const c = css(child)
      if (!shown(child) || placed(c) || clips(c) || parseFloat(c.flexShrink) === 0) continue // a scroll area of its own is meant to give
      if ((child.innerText || "").trim()) {
        report("a scrolling column whose rows can shrink (give them flex-shrink: 0)", el, "", ` (first: ${name(child)})`)
        break
      }
    }
  }
  // 3. one control drawn over another (14 Nov: a calendar's kind menu, too wide for its column, covered its Skip Inbox
  // switch): buttons, switches, links and fields in the same layer (not one in a popover over the other) whose boxes
  // cross by more than a sliver both ways
  const layer = (el) => el.closest("[role=dialog], [role=menu], [role=listbox], .fr-float") ?? document
  // the part of a control that shows: what scrolled out of its list is under nothing
  const showing = (el) => {
    const r = el.getBoundingClientRect()
    let box = { left: r.left, right: r.right, top: r.top, bottom: r.bottom }
    for (let e = el.parentElement; e && e !== document.body; e = e.parentElement) {
      if (!clips(css(e))) continue
      const c = e.getBoundingClientRect()
      box = { left: Math.max(box.left, c.left), right: Math.min(box.right, c.right), top: Math.max(box.top, c.top), bottom: Math.min(box.bottom, c.bottom) }
    }
    return box
  }
  const controls = [...document.querySelectorAll("button, a[href], input, select, textarea, [role=switch], [role=button]")].filter((el) => shown(el) && !placed(css(el)) && !el.closest("[data-overflow-ok]"))
  const boxes = controls.map((el) => [el, showing(el), layer(el)])
  for (let i = 0; i < boxes.length; i++) {
    for (let j = i + 1; j < boxes.length; j++) {
      const [a, ra, la] = boxes[i]
      const [b, rb, lb] = boxes[j]
      if (la !== lb || a.contains(b) || b.contains(a)) continue
      const wide = Math.min(ra.right, rb.right) - Math.max(ra.left, rb.left)
      const tall = Math.min(ra.bottom, rb.bottom) - Math.max(ra.top, rb.top)
      if (wide > 3 && tall > 3) report("controls on top of each other", a, `${Math.round(wide)}×${Math.round(tall)}px`, ` (and ${name(b)})`)
    }
  }
  // 5. an open dropdown cut off by what it sits in (15 Nov: the Projects page's tag menus, cut by an exam card's
  // rounded corners and a project's column). Only what really clips it counts: for a list placed absolutely, its
  // containing block and what clips that; for one fixed over the page, only a transformed parent (the Now bar)
  const contains = (s) => s.transform !== "none" || s.filter !== "none" || s.perspective !== "none" || /paint|layout|strict|content/.test(s.contain)
  for (const list of document.querySelectorAll("[role=listbox], [role=menu]")) {
    if (!shown(list)) continue
    const s = css(list)
    let from = null
    if (s.position === "fixed") {
      for (let e = list.parentElement; e && e !== document.body; e = e.parentElement) if (contains(css(e))) { from = e; break }
    } else if (s.position === "absolute") {
      from = list.offsetParent
    } else from = list.parentElement
    const r = list.getBoundingClientRect()
    let box = { left: r.left, right: r.right, top: r.top, bottom: r.bottom }
    for (let e = from; e && e !== document.body && e !== document.documentElement; e = e.parentElement) {
      if (!clips(css(e))) continue
      const c = e.getBoundingClientRect()
      box = { left: Math.max(box.left, c.left), right: Math.min(box.right, c.right), top: Math.max(box.top, c.top), bottom: Math.min(box.bottom, c.bottom) }
    }
    // and the window itself (16 Nov, IMG 4240: a fixed list as wide as the window, its left edge off the screen)
    box = { left: Math.max(box.left, 0), right: Math.min(box.right, innerWidth), top: Math.max(box.top, 0), bottom: Math.min(box.bottom, innerHeight) }
    const lost = Math.max(r.right - box.right, box.left - r.left, r.bottom - box.bottom, box.top - r.top, 0)
    if (lost > SLACK) report("a dropdown cut off by what it sits in", list, `${Math.round(lost)}px`)
  }
  // 4. a control the Now dock covers even with its column scrolled to the end (15 Nov: with the sleep and meal rows
  // up, the dock covered the Inbox's Accept and Decline, and no scroll brought them out). Every scrolling column is
  // taken to its end, where whatever is still under the dock can't be uncovered, then put back.
  const dock = document.querySelector("[data-tour=now]")
  if (dock && shown(dock)) {
    const d = dock.getBoundingClientRect()
    const scrollers = [...all].filter((el) => scrolls(css(el)) && el.scrollHeight > el.clientHeight + 1 && !el.closest("[data-tour=now]"))
    const were = scrollers.map((el) => el.scrollTop)
    for (const el of scrollers) el.scrollTop = el.scrollHeight
    for (const el of controls) {
      if (layer(el) !== document || el.closest("[data-tour=now]") || !shown(el)) continue
      const r = showing(el)
      const wide = Math.min(r.right, d.right) - Math.max(r.left, d.left)
      const tall = Math.min(r.bottom, d.bottom) - Math.max(r.top, d.top)
      if (wide > 3 && tall > 3) report("a control under the Now dock, even scrolled to the end", el, `${Math.round(tall)}px`)
    }
    scrollers.forEach((el, i) => (el.scrollTop = were[i]))
  }
  // 6. an empty box's hint cut off by the box (17 Nov: an ongoing project's hours box showed "e.g. 12h, 2.5 ho"): the
  // hint's width in the box's own font, against the room inside its padding
  // (measured in a span set in the box's font, not a canvas: a canvas reads no "ui-monospace" and measured another font)
  const ruler = document.createElement("span")
  ruler.style.cssText = "position:absolute;visibility:hidden;white-space:pre;left:-9999px;top:0"
  document.body.append(ruler)
  for (const el of document.querySelectorAll("input[placeholder]")) {
    if (el.value || !el.placeholder || el.getClientRects().length === 0 || el.type === "hidden") continue
    const s = getComputedStyle(el)
    if (s.visibility === "hidden" || s.display === "none") continue
    Object.assign(ruler.style, { fontFamily: s.fontFamily, fontSize: s.fontSize, fontWeight: s.fontWeight, fontStyle: s.fontStyle, letterSpacing: s.letterSpacing })
    ruler.textContent = el.placeholder
    const room = el.clientWidth - parseFloat(s.paddingLeft) - parseFloat(s.paddingRight)
    const hint = ruler.getBoundingClientRect().width
    if (hint - room > SLACK) report("a box's hint cut off", el, `${Math.round(hint - room)}px`, ` ("${el.placeholder}")`)
  }
  ruler.remove()
  return findings
})()
