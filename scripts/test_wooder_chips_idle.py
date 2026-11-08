#!/usr/bin/env python3
"""Real-browser regression test: the Wooder filter-chips MutationObserver must
settle (page reaches DOM idle) and stay settled after chip interactions.

Why this exists: the chips script's observer watches st-wooder with
attributeFilter ["style","hidden"]; an earlier version rewrote `hidden` on
already-hidden sections from inside its own observer callback. Chrome queues an
attribute mutation record even for same-value writes, so each observer run
enqueued new mutations - an infinite microtask loop that starved the renderer
(real Chrome hung indefinitely; DOM harnesses without real observer timing
never saw it). The fix makes hidden writes idempotent and disconnects the
observer while refreshing. This test loads the REAL index.html in headless
Chrome, clicks every wooder chip (interaction), and fails if mutation traffic
does not stop growing or the page never reaches idle.

Runs anywhere a Chrome/Chromium binary exists (GitHub ubuntu-latest ships
google-chrome). With no browser binary it prints SKIP and exits 0 - it is a
browser test, not a static check, and a vacuous pass beats a false failure.
Network is not required: the harness asserts settling, not data hydration, so
the dead-proxy fixture environment is fine (fetches fail fast, the page must
still go idle).
"""
import http.server
import json
import os
import shutil
import socket
import socketserver
import subprocess
import sys
import tempfile
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

HARNESS = """<!DOCTYPE html><html><body><script>
var RESULT = "";
function finish(s) {
  RESULT = s;
  document.title = s;
  var p = document.createElement("pre");
  p.id = "RESULT";
  p.textContent = s;
  document.body.appendChild(p);
}
var fr = document.createElement("iframe");
fr.src = "/index.html";
document.body.appendChild(fr);
fr.onload = function () {
  var d = fr.contentDocument;
  var root = d.getElementById("st-wooder");
  if (!root) { finish("FAIL no st-wooder in built page"); return; }
  var n = 0;
  new MutationObserver(function (rs) { n += rs.length; })
    .observe(root, { childList: true, subtree: true, attributes: true });
  function waitIdle(cb) {
    var last = -1, stable = 0;
    var iv = setInterval(function () {
      if (n === last) { stable++; } else { stable = 0; last = n; }
      if (n > 500000) { clearInterval(iv); finish("FAIL runaway mutations n=" + n); }
      else if (stable >= 4) { clearInterval(iv); cb(); }
    }, 250);
    return iv;
  }
  var iv0 = waitIdle(function () {
    var idleCount = n;
    var chips = Array.prototype.slice.call(root.querySelectorAll(".wi-chips .chip"));
    if (!chips.length) { finish("FAIL no wooder chips found"); return; }
    // interaction pass 1: click every chip in turn
    chips.forEach(function (c) { c.click(); });
    waitIdle(function () {
      // interaction pass 2: click a specific filter and check it applied
      var live = root.querySelector('.wi-chips .chip[data-chip="live"]') || chips[0];
      live.click();
      waitIdle(function () {
        var liveSec = root.querySelector('[data-filter="live"]');
        var others = Array.prototype.slice.call(root.querySelectorAll("[data-filter]"))
          .filter(function (s) { return s.getAttribute("data-filter") !== "live"; });
        var applied = liveSec && liveSec.hidden === false && others.some(function (s) { return s.hidden; });
        var all = root.querySelector('.wi-chips .chip[data-chip="all"]');
        if (all) all.click();
        waitIdle(function () {
          if (!applied) { finish("FAIL live filter did not apply (live section hidden or nothing else hidden)"); return; }
          finish("PASS idle-at=" + idleCount + " total=" + n + " chips=" + chips.length);
        });
      });
    });
  });
  // hard watchdog: with the starvation bug, timers never fire, so this only
  // runs on a healthy page that somehow never settles
  setTimeout(function () {
    if (!RESULT) { clearInterval(iv0); finish("FAIL never reached DOM idle, n=" + n); }
  }, 60000);
};
</script></body></html>"""


def find_chrome():
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome"):
        p = shutil.which(name)
        if p:
            return p
    return None


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/__chips_test"):
            body = HARNESS.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        return super().do_GET()

    def log_message(self, *a):
        pass


def main():
    chrome = find_chrome()
    if not chrome:
        print("SKIP: no chrome/chromium binary on this host (browser test needs one; CI has google-chrome)")
        return 0
    os.chdir(ROOT)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    srv = socketserver.ThreadingTCPServer(("127.0.0.1", port), Handler)
    srv.daemon_threads = True
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    profile = tempfile.mkdtemp(prefix="chips-idle-")
    cmd = [
        chrome, "--headless=new", "--no-sandbox", "--disable-gpu",
        "--disable-dev-shm-usage", "--user-data-dir=" + profile,
        "--virtual-time-budget=90000", "--timeout=90000",
        "--dump-dom", "http://127.0.0.1:%d/__chips_test" % port,
    ]
    try:
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=150)
            dom = out.stdout or ""
        except subprocess.TimeoutExpired:
            print("FAIL: chrome did not finish within 150s (renderer starved - mutation loop regression?)")
            return 1
    finally:
        srv.shutdown()
    import re
    hits = re.findall(r'id="RESULT">((?:PASS|FAIL)[^<]*)', dom)
    marker = hits[-1] if hits else ""
    if not marker:
        print("FAIL: harness produced no RESULT (page never reached idle; dump tail: %r)" % dom[-200:])
        return 1
    print(marker)
    if marker.startswith("PASS"):
        print("OK   wooder chips: page reaches DOM idle and stays settled after chip interactions (real Chrome)")
        return 0
    print("FAIL: %s" % marker)
    return 1


if __name__ == "__main__":
    sys.exit(main())
