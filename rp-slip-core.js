(function () {
  var STAMP = { open: "Open", live: "Live", won: "Won", lost: "Lost", void: "Void" };

  function esc(v) {
    return String(v == null ? "" : v).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function has(v) { return v !== undefined && v !== null && v !== ""; }

  function legMargin(leg) {
    if (has(leg.margin)) return Number(leg.margin);
    if (!has(leg.line) || !has(leg.final)) return null;
    var m = Number(leg.final) - Number(leg.line);
    return leg.dir === "under" ? -m : m;
  }

  function meter(leg) {
    if (!has(leg.line) || isNaN(Number(leg.line))) {
      return ""; // moneyline / non-numeric lines: no meter
    }
    var line = Number(leg.line), fin = has(leg.final) ? Number(leg.final) : 0;
    var scale = Math.max(line, fin) * 1.25 || 1;
    var l = Math.round(line / scale * 100), a = Math.round(fin / scale * 100);
    return '<span class="rp-meter" style="--line:' + l + '%;--act:' + a + '%"></span>';
  }

  // Countdown wording per sport. Edit this map to change the wording site-wide.
  var VERB = {
    NBA: "Tip off in", WNBA: "Tip off in", NCAAB: "Tip off in", CBB: "Tip off in",
    NFL: "Kickoff in", NCAAF: "Kickoff in", CFB: "Kickoff in",
    SOCCER: "Kickoff in", MLS: "Kickoff in", EPL: "Kickoff in", UCL: "Kickoff in",
    MLB: "First pitch in", NHL: "Puck drop in", UFC: "Fight starts in", BOXING: "Fight starts in",
    PGA: "Tee off in", GOLF: "Tee off in", TENNIS: "First serve in", F1: "Lights out in", NASCAR: "Green flag in"
  };
  function verbFor(sport) { return VERB[String(sport || "").toUpperCase()] || "Starts in"; }

  function fmtLeft(ms) {
    var s = Math.max(0, Math.floor(ms / 1000));
    var d = Math.floor(s / 86400), h = Math.floor(s % 86400 / 3600), m = Math.floor(s % 3600 / 60), sec = s % 60;
    function p(n) { return (n < 10 ? "0" : "") + n; }
    return (d ? d + "d " : "") + p(h) + ":" + p(m) + ":" + p(sec);
  }

  function countdown(startsAt, sport) {
    var ms = new Date(startsAt).getTime();
    if (isNaN(ms)) return "";
    return '<span class="rp-cd" data-starts="' + ms + '" data-verb="' + esc(verbFor(sport)) + '">' +
      esc(verbFor(sport)) + " <strong>" + fmtLeft(ms - Date.now()) + "</strong></span>";
  }

  // One shared 1-second ticker updates every countdown on the page.
  function tick() {
    var now = Date.now();
    var els = document.querySelectorAll(".rp-cd[data-starts]");
    for (var i = 0; i < els.length; i++) {
      var left = Number(els[i].getAttribute("data-starts")) - now;
      var strong = els[i].querySelector("strong");
      if (left <= 0) { els[i].classList.add("rp-cd-done"); els[i].innerHTML = "<strong>Starting</strong>"; els[i].removeAttribute("data-starts"); }
      else if (strong) strong.textContent = fmtLeft(left);
    }
  }
  if (typeof window !== "undefined" && !window.__rpCdTimer) window.__rpCdTimer = setInterval(tick, 1000);

  // ---- Live game clock, worded per sport ----
  // clock = { period: 3, time: "8:42", half: "top"|"bot" (MLB), outs: 2 (MLB),
  //           state: "live"|"break"|"delay"|"final", text: "override text" }
  function ord(n) { var s = ["th","st","nd","rd"], v = n % 100; return n + (s[(v - 20) % 10] || s[v] || s[0]); }
  function fmtClock(c, sport) {
    if (!c) return "";
    if (has(c.text)) return c.text;
    var S = String(sport || "").toUpperCase(), p = Number(c.period) || 0, tm = has(c.time) ? " " + c.time : "";
    if (c.state === "final") return "Final";
    if (c.state === "delay") return "Delayed";
    if (S === "MLB") {
      if (c.state === "break") return (c.half === "top" ? "Mid " : "End ") + ord(p);
      return (c.half === "bot" ? "Bot " : "Top ") + ord(p) + (has(c.outs) ? " · " + c.outs + " out" : "");
    }
    if (S === "NHL") {
      if (c.state === "break") return p >= 3 ? "End of reg" : "Int " + p;
      return (p === 4 ? "OT" : p >= 5 ? "SO" : "P" + p) + tm;
    }
    if (S === "NCAAB" || S === "CBB") {
      if (c.state === "break") return p === 1 ? "Halftime" : "End of reg";
      return (p <= 2 ? "H" + p : (p === 3 ? "OT" : (p - 2) + "OT")) + tm;
    }
    if (["SOCCER","MLS","EPL","UCL"].indexOf(S) > -1) {
      if (c.state === "break") return "HT";
      return has(c.time) ? c.time + "\u2032" : "Live";
    }
    if (["NBA","WNBA","NFL","NCAAF","CFB"].indexOf(S) > -1) {
      if (c.state === "break") return p === 2 ? "Halftime" : "End Q" + p;
      return (p <= 4 ? "Q" + p : (p === 5 ? "OT" : (p - 4) + "OT")) + tm;
    }
    return (p ? "P" + p : "Live") + tm;
  }
  function clockTag(c, sport) {
    var txt = fmtClock(c, sport);
    return txt ? '<span class="rp-clock' + (c.state === "break" || c.state === "delay" ? " rp-clock-break" : "") + '">' + esc(txt) + "</span>" : "";
  }

  function pmCell(leg, t) {
    if (leg.status === "live" && !has(leg.final) && leg.clock) {
      return '<td class="rp-pm when">' + clockTag(leg.clock, leg.sport || t.sport) + "</td>";
    }
    if (leg.status === "open" || (leg.status === "live" && !has(leg.final))) {
      if (has(leg.startsAt) && !(has(t.startsAt) && t.startsAt === leg.startsAt)) {
        return '<td class="rp-pm when">' + countdown(leg.startsAt, leg.sport || t.sport) + "</td>";
      }
      return '<td class="rp-pm when">' + esc(leg.when || (has(t.startsAt) ? "—" : "—")) + "</td>";
    }
    if (leg.status === "void") return '<td class="rp-pm">—</td>';
    var m = legMargin(leg);
    if (m === null) return '<td class="rp-pm">—</td>';
    if (m === 0) return '<td class="rp-pm exact">EXACT</td>';
    if (leg.status === "live") {
      // live: show how many still needed (or +x already over)
      return m > 0 ? '<td class="rp-pm up">+' + m + "</td>"
                   : '<td class="rp-pm when">' + Math.abs(m) + " to go</td>";
    }
    return '<td class="rp-pm ' + (m > 0 ? "up" : "down") + '">' + (m > 0 ? "+" : "−") + Math.abs(m) + "</td>";
  }

  function render(t) {
    var legs = t.legs || [];
    var hits = legs.filter(function (l) { return l.status === "hit"; }).length;
    var counted = legs.filter(function (l) { return l.status !== "void"; }).length;
    var togo = legs.filter(function (l) { return l.status === "live" || l.status === "open"; }).length;
    var status = t.status || "open";

    var count = status === "open"
      ? counted + " <span>legs</span>"
      : hits + "/" + counted + " <span>" + (togo ? "· " + togo + " to go" : "legs") + "</span>";

    var gameLeft = [t.date, t.game].filter(has).map(esc).join(" · ");
    var gameRight;
    if (status === "live" && t.clock) {
      gameRight = clockTag(t.clock, t.sport) + (has(t.final) ? " <strong>" + esc(t.final) + "</strong>" : "");
    } else if (has(t.final)) {
      gameRight = (status === "live" ? "Score " : "Final ") + "<strong>" + esc(t.final) + "</strong>";
    } else if ((status === "open" || status === "live") && has(t.startsAt)) {
      gameRight = countdown(t.startsAt, t.sport);
    } else gameRight = "";

    var rows = legs.map(function (leg) {
      var st = leg.status || "open";
      var lineTxt = has(leg.lineText) ? leg.lineText : (has(leg.line) ? (leg.dir === "under" ? "U " + leg.line : leg.line + "+") : "—");
      var finTxt = has(leg.finalText) ? leg.finalText : (has(leg.final) ? leg.final : "—");
      return '<tr class="rp-' + st + '">' +
        '<td class="rp-leg"><span class="rp-leg-name">' + esc(leg.player) + '</span>' +
          ((has(leg.market) || (leg.clock && has(leg.final))) ? '<span class="rp-leg-mkt">' + esc(leg.market || "") +
            (leg.clock && has(leg.final) && st === "live" ? " " + clockTag(leg.clock, leg.sport || t.sport) : "") + "</span>" : "") + "</td>" +
        '<td class="rp-line">' + esc(lineTxt) + "</td>" +
        '<td class="rp-final">' + esc(finTxt) + "</td>" +
        '<td class="rp-col-meter">' + meter(leg) + "</td>" +
        pmCell(leg, t) +
        '<td class="rp-odds rp-col-odds">' + esc(leg.odds || "—") + "</td>" +
      "</tr>";
    }).join("");

    var foot = '<span class="rp-src">' + esc(t.source || "RixPicks") + "</span>";
    if (t.books && t.books.length) {
      foot += '<span class="rp-books">' + t.books.map(function (b) {
        return '<a class="rp-book' + (b.best ? " best" : "") + '" href="' + esc(b.url || "#") + '" target="_blank" rel="noopener">' +
          esc(b.name) + " <b>" + esc(b.odds) + "</b></a>";
      }).join("") + "</span>";
    } else if (has(t.total)) {
      foot += '<span class="rp-total">Total <b>' + esc(t.total) + "</b></span>";
    }

    return '<article class="rp-slip" data-status="' + esc(status) + '">' +
      '<header class="rp-slip-head">' +
        '<p class="rp-slip-kicker"><b>' + esc(t.sport) + "</b>" + (has(t.type) ? " · " + esc(t.type) : "") + "</p>" +
        '<h3 class="rp-slip-title" title="' + esc(t.title) + '">' + esc(t.title) + "</h3>" +
        '<div class="rp-slip-result"><span class="rp-stamp">' + STAMP[status] + '</span><span class="rp-slip-count">' + count + "</span></div>" +
      "</header>" +
      ((gameLeft || gameRight) ? '<div class="rp-slip-game"><span>' + gameLeft + "</span><span>" + gameRight + "</span></div>" : "") +
      '<table class="rp-slip-table"><thead><tr>' +
        "<th>Leg</th><th>Line</th><th>" + (status === "live" ? "Now" : "Final") + '</th><th class="rp-col-meter">Margin</th><th>' +
        (status === "open" ? "Starts" : "+/-") + '</th><th class="rp-col-odds">' + esc(t.oddsLabel || "Odds") + "</th>" +
      "</tr></thead><tbody>" + rows + "</tbody></table>" +
      (has(t.note) ? '<p class="rp-slip-note">' + esc(t.note) + "</p>" : "") +
      '<footer class="rp-slip-foot">' + foot + "</footer>" +
      more(t) +
    "</article>";
  }

  function more(t) {
    var src = (t.sources || []).filter(function (s) { return s && has(s.url); });
    if (!src.length && !has(t.details)) return "";
    return '<details class="rp-slip-more"><summary>Sources &amp; details</summary><div class="rp-slip-more-body">' +
      (src.length ? '<ul class="rp-sources">' + src.map(function (s) {
        return '<li><a href="' + esc(s.url) + '" target="_blank" rel="noopener">' + esc(s.label || s.url) + " ↗</a></li>";
      }).join("") + "</ul>" : "") +
      (has(t.details) ? '<p class="rp-details">' + esc(t.details) + "</p>" : "") +
    "</div></details>";
  }

  function mount(el, tickets) {
    if (typeof el === "string") el = document.querySelector(el);
    if (!el) return;
    el.innerHTML = (tickets || []).map(render).join("");
  }

  window.RPSlip = { render: render, mount: mount };
})();
