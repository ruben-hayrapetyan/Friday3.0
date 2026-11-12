// Slack's sign-in comes back here (https); this sends the browser on to Friday on this Mac with the same answer
// (H182). The port Friday listens on is at the front of `state` ("8765-…"); only this Mac's own address is ever used.
(function () {
  var asked = new URLSearchParams(location.search)
  var state = asked.get("state") || ""
  var port = state.split("-")[0]
  var said = document.getElementById("said")
  if (!/^\d{4,5}$/.test(port) || Number(port) < 1024 || Number(port) > 65535) {
    said.textContent = "This page only finishes a Slack sign-in started in Friday. Start again from Friday's Slack box."
    return
  }
  location.replace("http://127.0.0.1:" + port + "/oauth/callback" + location.search)
})()
