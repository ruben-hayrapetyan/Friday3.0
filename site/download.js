// The download buttons name the visitor's computer (HOSTED.md H54): Friday is a Mac app for now (H110), so on
// Windows, Linux or a phone they say so instead of downloading something that won't open there.
(function () {
  var platform = ((navigator.userAgentData && navigator.userAgentData.platform) || navigator.platform || "").toLowerCase();
  var agent = navigator.userAgent.toLowerCase();
  var phone = /iphone|ipad|android/.test(agent) || (platform === "macintel" && navigator.maxTouchPoints > 1);
  var mac = !phone && platform.indexOf("mac") === 0;
  if (mac) return;
  var button = document.querySelector("[data-download]");
  var file = button ? button.getAttribute("href") : "/#get";  // the current disk image, as the page names it
  document.querySelectorAll("[data-download]").forEach(function (button) {
    button.textContent = phone ? "Friday is a Mac app" : "Friday is for Mac for now";
    button.setAttribute("aria-disabled", "true");
    button.removeAttribute("download");
    button.removeAttribute("href");
  });
  document.querySelectorAll("[data-mac-only]").forEach(function (part) { part.hidden = true; });
  document.querySelectorAll("[data-download-other]").forEach(function (note) {
    note.hidden = false;
    note.innerHTML = (phone ? "Open this page on your Mac to download it. " : "Windows and Linux versions are coming. ") +
      '<a href="' + file + '" download>Download for Mac anyway</a>';
  });
})();
