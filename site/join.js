// The invite page (H233, H234). The invite is the part of the link after "#": never sent to the site with the page.
// The page asks the hub what it is (whose, used, run out) without using it; meanwhile it reveals itself like a landing
// page: a counter, Friday's blocks flying in and stacking, the words rising from behind masks, the cover parting like
// curtains onto the ticket. Accept tears the ticket's stub off along its perforation and hands the invite to Friday
// (friday://join?invite=…), which swaps it for this device's key. On this computer only (a local preview), ?state=
// ok|used|gone|none|limited|offline shows a state without asking, and ?noopen tears the stub without opening Friday.
(function () {
  var main = document.querySelector("main.invite");
  var cover = document.getElementById("cover");
  var ticket = document.getElementById("ticket");
  var stub = document.getElementById("stub");
  var invite = location.hash.slice(1);
  var reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var local = /^(localhost|127\.0\.0\.1|\[::1\])$/.test(location.hostname);
  var noopen = local && new URLSearchParams(location.search).has("noopen");
  var launch = function (link) { if (!noopen) location.href = link; };
  var at = function (ms, fn) { setTimeout(fn, ms); };

  // Friday's blocks: what a week holds, in its paints
  var CARDS = [
    ["Lecture", "10:10am", "--payne"], ["Problem set 7", "2h", "--verdigris"], ["Lunch", "12:30pm", "--ochre"],
    ["Essay draft", "1h 30m", "--cerulean"], ["Run", "5:30pm", "--sienna"], ["Reading", "45m", "--magenta"],
    ["Your week", "planned", "--ultramarine"],
  ];
  function deal() {
    var deck = document.getElementById("deck");
    var wide = Math.min(window.innerWidth, 1200);
    var step = Math.min(176, (wide - 80) / CARDS.length);
    CARDS.forEach(function (c, i) {
      var card = document.createElement("div");
      var mid = i - (CARDS.length - 1) / 2;
      var side = mid < 0 ? -1 : 1;
      card.className = "card";
      card.innerHTML = "<b></b><small></small>";
      card.firstChild.textContent = c[0];
      card.lastChild.textContent = c[1];
      var set = function (k, v) { card.style.setProperty(k, v); };
      set("--paint", "var(" + c[2] + ")");
      set("--w", "180px");
      set("--h", "112px");
      set("--d", i * 0.07 + "s");
      // from off the screen, below and to a side
      set("--fx", side * (40 + Math.random() * 40) + "vw");
      set("--fy", 60 + Math.random() * 30 + "vh");
      set("--fr", side * (30 + Math.random() * 40) + "deg");
      // the stack: a little askew
      set("--sx", (Math.random() - 0.5) * 18 + "px");
      set("--sy", (Math.random() - 0.5) * 14 - i * 2 + "px");
      set("--sr", (Math.random() - 0.5) * 12 + "deg");
      // fanned across, on a gentle arc
      set("--px", mid * step + "px");
      set("--py", Math.abs(mid) * Math.abs(mid) * 6 + "px");
      set("--pr", mid * 4 + "deg");
      // away with the curtain on its side
      set("--ox", side * (55 + Math.random() * 20) + "vw");
      set("--oy", (Math.random() - 0.5) * 40 + "vh");
      set("--or", side * (20 + Math.random() * 30) + "deg");
      deck.appendChild(card);
    });
  }

  // the counter: up to 90 on its own, the rest once the hub has answered
  function count(answered, done) {
    var digits = document.getElementById("count");
    var bar = document.getElementById("bar");
    var shown = 0;
    var began = performance.now();
    function tick(now) {
      var k = Math.min(1, (now - began) / 1300);
      var goal = answered() ? 100 : 90;
      var eased = 1 - Math.pow(1 - k, 3);
      shown = Math.max(shown, Math.min(goal, Math.round(eased * 100)));
      if (answered() && k >= 1) shown = Math.min(100, shown + 4);
      digits.textContent = String(shown).padStart(3, "0");
      bar.style.width = shown + "%";
      if (shown < 100) requestAnimationFrame(tick);
      else done();
    }
    requestAnimationFrame(tick);
  }

  function show(got) {
    main.setAttribute("data-state", got.state);
    document.getElementById("serial").textContent = "No. " + (got.serial || "----");
    if (got.state === "ok") {
      var who = got.name ? ", " + got.name : "";
      document.getElementById("who").textContent = who;
      document.getElementById("lines-who").textContent = who;
      document.getElementById("left").textContent = got.hours > 1 ? "Works once · " + got.hours + " hours left" : "Works once · under an hour left";
    }
  }

  function play(got) {
    show(got);
    if (reduced) return ticket.classList.add("shown");
    var party = got.state === "ok";
    cover.classList.add("counted");
    var t = 450;
    if (party) {
      at(t, function () { cover.classList.add("stacked"); });
      at((t += 1000), function () { cover.classList.add("fanned"); });
      at((t += 650), function () { cover.classList.add("said"); });
      t += 1200;
    }
    at(t, function () {
      cover.classList.add("open");
      ticket.classList.add("shown");
    });
    at(t + 1300, function () { cover.classList.add("gone"); });
  }

  // what the invite is, without using it (the hub, friday_hub/site.py: POST /test/invite): whose and how long it has,
  // or used, run out (gone), none, or this address past its wrong tries (limited); offline when the site can't be asked
  function look(done) {
    var asked = local ? new URLSearchParams(location.search).get("state") : null;
    if (asked) return setTimeout(function () { done({ state: asked, name: "Alex", hours: 23, serial: "7F3A" }); }, 600);
    if (!invite) return done({ state: "none" });
    fetch("/test/invite", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ invite: invite }) })
      .then(function (r) { return r.json(); })
      .then(function (got) { done(got && typeof got.state === "string" ? got : { state: "none" }); })
      .catch(function () { done({ state: "offline" }); });
  }

  var got = null;
  if (!reduced) deal();
  look(function (answer) { got = answer; if (reduced) play(got); });
  if (!reduced) count(function () { return got !== null; }, function () { play(got); });

  // Accept: the stub tears off along its perforation (jagged), swings and falls; the ticket closes over the gap
  function jagged(box, across) {
    var w = box.width, h = box.height, points = [];
    var tooth = 9, deep = 5;
    if (!across) { // the stub on the left: its right edge torn, top to bottom
      points.push("0 0", w + "px 0");
      for (var y = 0, n = 0; y <= h; y += tooth, n++) points.push((n % 2 ? w - deep : w) + "px " + Math.min(y, h) + "px");
      points.push(w + "px " + h + "px", "0 " + h + "px");
    } else { // a phone: the stub on top, its bottom edge torn, right to left
      points.push("0 0", w + "px 0", w + "px " + h + "px");
      for (var x = w, m = 0; x >= 0; x -= tooth, m++) points.push(Math.max(x, 0) + "px " + (m % 2 ? h - deep : h) + "px");
      points.push("0 " + h + "px");
    }
    return "polygon(" + points.join(", ") + ")";
  }
  function bits(across, edge) {
    var box = document.createElement("div");
    box.className = "bits";
    if (across) box.style.top = edge.height + "px"; else box.style.left = edge.width + "px"; // where it tore
    for (var i = 0; i < 16; i++) {
      var b = document.createElement("i");
      var along = Math.random() * 100 + "%";
      if (across) b.style.left = along; else b.style.top = along;
      b.style.setProperty("--x", (Math.random() - 0.3) * 60 + "px");
      b.style.setProperty("--y", 40 + Math.random() * 90 + "px");
      b.style.setProperty("--r", (Math.random() - 0.5) * 540 + "deg");
      b.style.setProperty("--d", Math.random() * 0.15 + "s");
      box.appendChild(b);
    }
    ticket.appendChild(box);
    at(1400, function () { box.remove(); });
  }
  function accept() {
    var link = "friday://join?invite=" + encodeURIComponent(invite || "prototype");
    var go = function () {
      main.setAttribute("data-state", "in");
      launch(link);
    };
    if (reduced) {
      stub.classList.add("falling");
      return go();
    }
    var box = stub.getBoundingClientRect();
    var across = window.matchMedia("(max-width: 620px)").matches;
    // lifted out of the ticket where it is, so the ticket can close over it while it falls
    stub.style.clipPath = jagged(box, across);
    stub.style.position = "absolute";
    stub.style.left = "0px";
    stub.style.top = "0px";
    stub.style.width = box.width + "px";
    stub.style.height = box.height + "px";
    stub.style.zIndex = "2";
    stub.classList.add("torn");
    bits(across, box);
    requestAnimationFrame(function () {
      stub.classList.add("falling");
      ticket.classList.add("torn");
    });
    at(700, function () { main.setAttribute("data-state", "in"); });
    at(1300, function () { launch(link); });
  }
  document.getElementById("accept").addEventListener("click", accept);

  document.getElementById("copy").addEventListener("click", function (e) {
    navigator.clipboard.writeText(location.href).then(function () { e.target.textContent = "Copied"; });
  });
})();
