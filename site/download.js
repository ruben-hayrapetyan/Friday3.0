// The download button names the visitor's computer (HOSTED.md H54): Friday is a Mac app for now (H110), so on Windows,
// Linux or a phone the button says so instead of downloading something that won't open there.
(function () {
  var button = document.getElementById("download-button");
  var other = document.getElementById("download-other");
  if (!button || !other) return;
  var platform = ((navigator.userAgentData && navigator.userAgentData.platform) || navigator.platform || "").toLowerCase();
  var agent = navigator.userAgent.toLowerCase();
  var phone = /iphone|ipad|android/.test(agent) || (platform === "macintel" && navigator.maxTouchPoints > 1);
  var mac = !phone && platform.indexOf("mac") === 0;
  if (mac) return;
  button.textContent = phone ? "Friday is a Mac app" : "Friday is for Mac for now";
  button.setAttribute("aria-disabled", "true");
  button.removeAttribute("download");
  button.removeAttribute("href");
  other.hidden = false;
  other.innerHTML = (phone ? "Open this page on your Mac to download it. " : "Windows and Linux versions are coming. ") +
    '<a href="/downloads/Friday-0.1.0.dmg" download>Download for Mac anyway</a>';
})();
