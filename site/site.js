// Sections arrive as you reach them (HOSTED.md H129): a short rise and fade, once. Nothing moves with reduced motion,
// and without scripts everything simply shows (only a page that runs scripts hides them first: `.js`).
(function () {
  var parts = document.querySelectorAll(".reveal");
  if (!("IntersectionObserver" in window) || window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    parts.forEach(function (el) { el.classList.add("in"); });
    return;
  }
  var seen = new IntersectionObserver(function (entries) {
    entries.forEach(function (entry) {
      if (entry.isIntersecting) { entry.target.classList.add("in"); seen.unobserve(entry.target); }
    });
  }, { rootMargin: "0px 0px -10% 0px" });
  parts.forEach(function (el) { seen.observe(el); });
})();

// Copy puts the Terminal line on the clipboard (HOSTED.md H131) and says so for a moment.
(function () {
  document.querySelectorAll("[data-copy]").forEach(function (button) {
    button.addEventListener("click", function () {
      var line = button.parentNode.querySelector("code").textContent;
      var done = function () {
        button.textContent = "Copied";
        setTimeout(function () { button.textContent = "Copy"; }, 1600);
      };
      if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(line).then(done);
      else {
        var range = document.createRange();
        range.selectNodeContents(button.parentNode.querySelector("code"));
        getSelection().removeAllRanges();
        getSelection().addRange(range);
      }
    });
  });
})();
