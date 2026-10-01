/* Futures quote freshness, window-aware. The quoter (futures_quotes.py via wooder_td.yml) runs
   every-5-min cron on UTC hours 16-23 and 0-6 (9 AM - 11:59 PM PT). Outside that window nothing is
   scheduled to refresh quotes, so a plain age check false-alarms every night from ~07:20 UTC.
   Inside the window: newest quote must be under 20 min old. Outside: newest quote must be from
   the last window (no older than window close minus 20 min), so a quoter that died in-window
   still fails the next morning. */
'use strict';
const LIM = 20 * 60000;
function inWindow(ms) { const h = new Date(ms).getUTCHours(); return h >= 16 || h <= 6; }
function lastWindowClose(ms) { const d = new Date(ms); d.setUTCHours(7, 0, 0, 0); if (d.getTime() > ms) d.setUTCDate(d.getUTCDate() - 1); return d.getTime(); }
function futuresFresh(nowMs, newestQuoteMs) {
  if (!isFinite(newestQuoteMs)) return false;
  if (inWindow(nowMs)) return (nowMs - newestQuoteMs) < LIM;
  return newestQuoteMs >= lastWindowClose(nowMs) - LIM;
}
module.exports = { futuresFresh, inWindow, lastWindowClose };
