// The download buttons name the visitor's computer (HOSTED.md H54): Friday is a Mac app for now (H110), so on
// Windows, Linux or a phone they say so instead of downloading something that won't open there. Friday runs on
// Apple silicon only: Chrome and Edge can tell an Intel Mac, which is told so (H188); Safari and Firefox can't, and
// there the specs line under each button ("Apple silicon, macOS 14 or later") is the only warning.
(function () {
  var platform = ((navigator.userAgentData && navigator.userAgentData.platform) || navigator.platform || "").toLowerCase();
  var agent = navigator.userAgent.toLowerCase();
  var phone = /iphone|ipad|android/.test(agent) || (platform === "macintel" && navigator.maxTouchPoints > 1);
  var mac = !phone && platform.indexOf("mac") === 0;
  var first = document.querySelector("[data-download]");
  var file = first ? first.getAttribute("href") : "/#get";  // the current disk image, as the page names it

  function cannot(label, note, anyway, hideMacOnly) {
    document.querySelectorAll("[data-download]").forEach(function (button) {
      button.textContent = label;
      button.setAttribute("aria-disabled", "true");
      button.removeAttribute("download");
      button.removeAttribute("href");
    });
    if (hideMacOnly) document.querySelectorAll("[data-mac-only]").forEach(function (part) { part.hidden = true; });
    document.querySelectorAll("[data-download-other]").forEach(function (other) {
      other.hidden = false;
      other.innerHTML = note + '<a href="' + file + '" download>' + anyway + "</a>";
    });
  }

  if (!mac) {
    cannot(phone ? "Friday is a Mac app" : "Friday is for Mac for now",
      phone ? "Open this page on your Mac to download it. " : "Windows and Linux versions are coming. ",
      "Download for Mac anyway", true);
    return;
  }
  // Only Chromium browsers tell the chip; "x86" is an Intel Mac. Any other answer, or none, keeps the download.
  var data = navigator.userAgentData;
  if (!data || typeof data.getHighEntropyValues !== "function") return;
  data.getHighEntropyValues(["architecture"]).then(function (values) {
    if (values && values.architecture === "x86") {
      cannot("Friday needs an Apple silicon Mac",
        "This Mac has an Intel chip, and Friday runs on Macs with Apple silicon (M1 or later). ", "Download anyway", false);
    }
  }, function () {});
})();
