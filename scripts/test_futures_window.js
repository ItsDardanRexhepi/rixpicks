#!/usr/bin/env node
/* Fixture for futures_window.js. Run: node scripts/test_futures_window.js */
'use strict';
const { futuresFresh } = require('./futures_window.js');
let f = 0;
function t(label, got, want) { if (got !== want) f++; console.log((got === want ? 'OK   ' : 'FAIL ') + label); }
const Z = s => Date.parse(s);
t('in window, 5 min old: fresh', futuresFresh(Z('2026-10-01T03:00:00Z'), Z('2026-10-01T02:55:00Z')), true);
t('in window, 30 min old: STALE', futuresFresh(Z('2026-10-01T03:00:00Z'), Z('2026-10-01T02:30:00Z')), false);
t('window edge 06:59, 10 min old: fresh', futuresFresh(Z('2026-10-01T06:59:00Z'), Z('2026-10-01T06:49:00Z')), true);
t('after close 07:18, last quote 06:50 (the 12:18 AM PT case): fresh', futuresFresh(Z('2026-10-01T07:18:00Z'), Z('2026-10-01T06:50:00Z')), true);
t('overnight 12:00Z, last quote 06:50: fresh', futuresFresh(Z('2026-10-01T12:00:00Z'), Z('2026-10-01T06:50:00Z')), true);
t('overnight 12:00Z, quoter died at 03:00: STALE', futuresFresh(Z('2026-10-01T12:00:00Z'), Z('2026-10-01T03:00:00Z')), false);
t('16:30Z in window, last quote from yesterday: STALE', futuresFresh(Z('2026-10-01T16:30:00Z'), Z('2026-10-01T06:50:00Z')), false);
t('no quote: STALE', futuresFresh(Z('2026-10-01T03:00:00Z'), NaN), false);
console.log(f ? 'FAILURES: ' + f : 'ALL CHECKS PASS'); process.exit(f ? 1 : 0);
