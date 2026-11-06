// The home page's week, which plans and replans while you watch (HOSTED.md H129): drawn as Friday draws a week
// (hour lines, blocks in Chroma's pigments with their times on a 12-hour clock, a red now line), and played as four
// steps on a loop: an essay typed in, planned into three gaps before Friday; a shift moved onto one of them; the two
// blocks it hit moved, and nothing else. Reduced motion shows the finished plan, still. Pause stops it anywhere.
(function () {
  var board = document.getElementById("board");
  if (!board) return;
  var FIRST = 8, LAST = 22; // 8am to 10pm
  var DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  var TODAY = 1; // Tuesday, in this example week

  // The week before the essay: classes and the shift (events, Payne's grey), meals (ochre), work already planned.
  var BASE = [
    { id: "econ-m", d: 0, s: 10, h: 1.25, t: "ECON Lecture", p: "payne", ev: 1 },
    { id: "econ-w", d: 2, s: 10, h: 1.25, t: "ECON Lecture", p: "payne", ev: 1 },
    { id: "econ-f", d: 4, s: 10, h: 1.25, t: "ECON Lecture", p: "payne", ev: 1 },
    { id: "cs-t", d: 1, s: 11.25, h: 0.8333, t: "CS Lecture", p: "payne", ev: 1 },
    { id: "cs-r", d: 3, s: 11.25, h: 0.8333, t: "CS Lecture", p: "payne", ev: 1 },
    { id: "span-m", d: 0, s: 14.75, h: 1.25, t: "SPAN 2090", p: "payne", ev: 1 },
    { id: "span-w", d: 2, s: 14.75, h: 1.25, t: "SPAN 2090", p: "payne", ev: 1 },
    { id: "shift", d: 1, s: 16, h: 4, t: "Shift", p: "payne", ev: 1 },
    { id: "lunch0", d: 0, s: 12.5, h: 0.75, t: "Lunch", p: "ochre" },
    { id: "lunch1", d: 1, s: 12.5, h: 0.75, t: "Lunch", p: "ochre" },
    { id: "lunch2", d: 2, s: 12.5, h: 0.75, t: "Lunch", p: "ochre" },
    { id: "lunch3", d: 3, s: 12.5, h: 0.75, t: "Lunch", p: "ochre" },
    { id: "lunch4", d: 4, s: 12.5, h: 0.75, t: "Lunch", p: "ochre" },
    { id: "lunch5", d: 5, s: 13, h: 0.75, t: "Lunch", p: "ochre" },
    { id: "lunch6", d: 6, s: 13, h: 0.75, t: "Lunch", p: "ochre" },
    { id: "dinner0", d: 0, s: 18.5, h: 0.75, t: "Dinner", p: "ochre" },
    { id: "dinner1", d: 1, s: 20.25, h: 0.75, t: "Dinner", p: "ochre" },
    { id: "dinner2", d: 2, s: 18.5, h: 0.75, t: "Dinner", p: "ochre" },
    { id: "dinner3", d: 3, s: 18.5, h: 0.75, t: "Dinner", p: "ochre" },
    { id: "dinner4", d: 4, s: 19, h: 0.75, t: "Dinner", p: "ochre" },
    { id: "dinner5", d: 5, s: 19, h: 0.75, t: "Dinner", p: "ochre" },
    { id: "dinner6", d: 6, s: 18.5, h: 0.75, t: "Dinner", p: "ochre" },
    { id: "read7", d: 0, s: 16.25, h: 1.5, t: "Reading 7", p: "verdigris" },
    { id: "ps4a", d: 0, s: 20, h: 1.5, t: "Problem Set 4", p: "cerulean" },
    { id: "lab", d: 2, s: 8.5, h: 1.5, t: "Lab Report", p: "ultramarine" },
    { id: "ps4b", d: 3, s: 14, h: 1.5, t: "Problem Set 4", p: "cerulean" },
    { id: "read8", d: 3, s: 20, h: 1.5, t: "Reading 8", p: "verdigris" },
    { id: "laundry", d: 5, s: 10.5, h: 1, t: "Laundry", p: "sienna" },
    { id: "prep", d: 6, s: 15, h: 2, t: "Prelim prep", p: "cerulean" },
  ];
  // The essay's three pieces, where Friday first puts them, and where the replan moves what the shift hit.
  var ESSAY = [
    { id: "essay1", d: 1, s: 14, h: 1, t: "Essay 1/3", p: "magenta" },
    { id: "essay2", d: 2, s: 16.5, h: 1, t: "Essay 2/3", p: "magenta" },
    { id: "essay3", d: 3, s: 9, h: 1, t: "Essay 3/3", p: "magenta" },
  ];
  var SHIFT_MOVED = { d: 2, s: 16, h: 4 };
  var REPLAN = { essay2: { d: 1, s: 17, h: 1 }, dinner2: { d: 2, s: 20.25, h: 0.75 } };
  var HIT = ["essay2", "dinner2"];

  var typed = board.querySelector(".typed"), quick = board.querySelector(".quickadd");
  var status = board.querySelector(".status"), steps = document.querySelectorAll(".chapters li");
  var head = board.querySelector(".days-head"), hours = board.querySelector(".hours"), grid = board.querySelector(".grid");
  var pause = document.querySelector(".pause");
  var still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var paused = false, blocks = {}, now = document.createElement("div"), dueTag;
  now.className = "now";

  function clock(x) {
    var h = Math.floor(x), m = Math.round((x - h) * 60), ap = h >= 12 ? "pm" : "am", h12 = ((h + 11) % 12) + 1;
    return h12 + (m ? ":" + String(m).padStart(2, "0") : "") + ap;
  }
  function span(b) {
    var a = clock(b.s), z = clock(b.s + b.h);
    return (a.slice(-2) === z.slice(-2) ? a.slice(0, -2) : a) + "–" + z;
  }
  function visible() {
    var w = board.clientWidth;
    return w < 560 ? [1, 2, 3] : w < 860 ? [1, 2, 3, 4] : [0, 1, 2, 3, 4, 5, 6];
  }

  function drawFrame() {
    var days = visible();
    board.style.setProperty("--days", days.length);
    head.innerHTML = "";
    days.forEach(function (d) {
      var cell = document.createElement("div");
      if (d === TODAY) cell.className = "today";
      cell.innerHTML = "<b>" + (10 + d) + "</b>" + DAYS[d] + (d === 4 ? '<span class="due">1 due</span>' : "");
      head.appendChild(cell);
    });
    dueTag = head.querySelector(".due");
    hours.innerHTML = "";
    grid.querySelectorAll(".col, .line").forEach(function (n) { n.remove(); });
    for (var h = FIRST + 1; h < LAST; h++) {
      var label = document.createElement("span");
      label.textContent = clock(h);
      label.style.top = ((h - FIRST) / (LAST - FIRST)) * 100 + "%";
      hours.appendChild(label);
      var line = document.createElement("div");
      line.className = "line";
      line.style.top = ((h - FIRST) / (LAST - FIRST)) * 100 + "%";
      grid.appendChild(line);
    }
    days.forEach(function () { var c = document.createElement("div"); c.className = "col"; grid.appendChild(c); });
    if (!now.parentNode) grid.appendChild(now);
    Object.keys(blocks).forEach(function (id) { place(blocks[id]); });
    placeNow(now.dataset.at ? +now.dataset.at : 9.67);
  }

  function place(el) {
    var b = el.b, days = visible(), i = days.indexOf(b.d), n = days.length;
    el.style.display = i < 0 ? "none" : "";
    el.style.left = "calc(" + (i / n) * 100 + "% + 3px)";
    el.style.width = "calc(" + 100 / n + "% - 6px)";
    el.style.top = ((b.s - FIRST) / (LAST - FIRST)) * 100 + "%";
    el.style.height = "calc(" + (b.h / (LAST - FIRST)) * 100 + "% - 2px)";
    el.innerHTML = b.t + (b.h >= 1.25 ? "<small>" + span(b) + "</small>" : "");
  }
  function placeNow(at) {
    var days = visible(), i = days.indexOf(TODAY), n = days.length;
    now.dataset.at = at;
    now.style.display = i < 0 ? "none" : "";
    now.style.left = (i / n) * 100 + "%";
    now.style.width = 100 / n + "%";
    now.style.top = ((at - FIRST) / (LAST - FIRST)) * 100 + "%";
  }
  function add(b, fresh) {
    var el = document.createElement("div");
    el.className = "block" + (b.ev ? " event" : "") + (fresh ? " fresh" : "");
    el.style.setProperty("--p", "var(--" + b.p + ")");
    el.b = Object.assign({}, b);
    blocks[b.id] = el;
    grid.appendChild(el);
    place(el);
    return el;
  }
  function move(id, to) {
    var el = blocks[id];
    Object.assign(el.b, to);
    place(el);
  }

  function wait(ms) {
    return new Promise(function (done) {
      var left = ms, last = performance.now();
      (function tick() {
        var t = performance.now();
        if (!paused) left -= t - last;
        last = t;
        if (left <= 0) done(); else requestAnimationFrame(tick);
      })();
    });
  }
  function say(text, on) { status.textContent = text; status.classList.toggle("on", !!on); }
  // Each step's bar fills over the time it plays (ms), on the story's own clock: paused, it stops too.
  var LENGTHS = [2600, 4300, 2200, 6400], current = -1, played = 0, last = performance.now();
  function step(n) {
    current = n;
    played = 0;
    steps.forEach(function (li, i) { li.style.setProperty("--fill", i < n ? "100%" : "0%"); });
  }
  (function fill() {
    var t = performance.now();
    if (!paused && current >= 0) played += t - last;
    last = t;
    if (current >= 0 && steps[current]) {
      steps[current].style.setProperty("--fill", Math.min(100, (played / LENGTHS[current]) * 100) + "%");
    }
    requestAnimationFrame(fill);
  })();

  function reset() {
    Object.keys(blocks).forEach(function (id) { blocks[id].remove(); });
    blocks = {};
    BASE.forEach(function (b) { add(b, false); });
    typed.textContent = "";
    quick.classList.remove("sent");
    if (dueTag) dueTag.classList.remove("on");
    say("Your week, planned", false);
    step(-1);
    placeNow(9.67);
  }

  async function play() {
    for (;;) {
      reset();
      await wait(1800);
      step(0);
      var words = "Essay 3h due Fri";
      for (var i = 1; i <= words.length; i++) { typed.textContent = words.slice(0, i); await wait(70); }
      await wait(500);
      quick.classList.add("sent");
      say("Planning the essay…", true);
      step(1);
      await wait(500);
      for (var k = 0; k < ESSAY.length; k++) {
        var el = add(Object.assign({}, ESSAY[k], { d: TODAY, s: FIRST, h: 1 }), true);
        void el.offsetWidth; // start where it was typed, then glide to its gap
        el.classList.remove("fresh");
        move(ESSAY[k].id, ESSAY[k]);
        await wait(380);
      }
      if (dueTag) dueTag.classList.add("on");
      typed.textContent = "";
      quick.classList.remove("sent");
      say("Planned 3 hours before Friday", true);
      placeNow(11.5);
      await wait(2600);
      step(2);
      say("Your shift moved to Wednesday", true);
      move("shift", SHIFT_MOVED);
      await wait(900);
      HIT.forEach(function (id) { blocks[id].classList.add("hit"); });
      await wait(1300);
      step(3);
      say("Replanning…", true);
      await wait(600);
      HIT.forEach(function (id) {
        blocks[id].classList.remove("hit");
        blocks[id].classList.add("moved");
        move(id, REPLAN[id]);
      });
      await wait(1000);
      say("Replanned: 2 moved, nothing else", true);
      placeNow(13.25);
      await wait(3200);
      HIT.forEach(function (id) { blocks[id].classList.remove("moved"); });
      await wait(1600);
    }
  }

  function finished() {
    reset();
    ESSAY.forEach(function (b) { add(b, false); });
    move("shift", SHIFT_MOVED);
    Object.keys(REPLAN).forEach(function (id) { move(id, REPLAN[id]); });
    if (dueTag) dueTag.classList.add("on");
    say("Replanned: 2 moved, nothing else", true);
    current = -1;
    steps.forEach(function (li) { li.style.setProperty("--fill", "100%"); });
    pause.hidden = true;
  }

  pause.addEventListener("click", function () {
    paused = !paused;
    pause.textContent = paused ? "Play" : "Pause";
    pause.setAttribute("aria-pressed", String(paused));
  });
  var lastDays = 0;
  window.addEventListener("resize", function () {
    var n = visible().length;
    if (n !== lastDays) { lastDays = n; drawFrame(); }
  });
  lastDays = visible().length;
  drawFrame();
  if (still) finished(); else play();

})();
