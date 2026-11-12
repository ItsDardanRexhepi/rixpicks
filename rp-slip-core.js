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

  function pmCell(leg) {
    if (leg.status === "open" || (leg.status === "live" && !has(leg.final))) {
      return '<td class="rp-pm when">' + esc(leg.when || "—") + "</td>";
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
    var gameRight = has(t.final) ? (status === "live" ? "Score " : "Final ") + "<strong>" + esc(t.final) + "</strong>" : "";

    var rows = legs.map(function (leg) {
      var st = leg.status || "open";
      var lineTxt = has(leg.lineText) ? leg.lineText : (has(leg.line) ? (leg.dir === "under" ? "U " + leg.line : leg.line + "+") : "—");
      var finTxt = has(leg.finalText) ? leg.finalText : (has(leg.final) ? leg.final : "—");
      return '<tr class="rp-' + st + '">' +
        '<td class="rp-leg"><span class="rp-leg-name">' + esc(leg.player) + '</span>' +
          (has(leg.market) ? '<span class="rp-leg-mkt">' + esc(leg.market) + "</span>" : "") + "</td>" +
        '<td class="rp-line">' + esc(lineTxt) + "</td>" +
        '<td class="rp-final">' + esc(finTxt) + "</td>" +
        '<td class="rp-col-meter">' + meter(leg) + "</td>" +
        pmCell(leg) +
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
