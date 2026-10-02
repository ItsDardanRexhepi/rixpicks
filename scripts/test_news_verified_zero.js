#!/usr/bin/env node
/* Fixture for the news verified-zero bucket rule (v17, prospective). Run: node scripts/test_news_verified_zero.js
   Loads workers/rixpicks-feeds/src/lib/parity.js unmodified (a temp .mjs copy with newsGate exported). Judges only checks.buckets. */
'use strict';
const fs = require('fs'), os = require('os'), path = require('path');
(async () => {
  const src = fs.readFileSync(path.join(__dirname, '../workers/rixpicks-feeds/src/lib/parity.js'), 'utf8');
  const tmp = path.join(os.tmpdir(), 'parity_vz_' + process.pid + '.mjs');
  fs.writeFileSync(tmp, src + '\nexport { newsGate };\n');
  const { newsGate } = await import('file://' + tmp);
  fs.unlinkSync(tmp);
  let f = 0;
  const t = (label, got, want) => { const ok = JSON.stringify(got) === JSON.stringify(want); if (!ok) f++; console.log((ok ? 'OK   ' : 'FAIL ') + label + (ok ? '' : ' got=' + JSON.stringify(got))); };
  const G = '2026-10-02T00:00:00.000Z', now = Date.parse(G);
  const art = (h, s) => ({ headline: h, link: 'https://x/' + h, source: s || 'ESPN', published: G });
  const prod = { generated_at: G, latest: [art('p1')], leagues: { 'hockey/nhl': [art('nhl story')] } };
  const mineWith = (leagues, gen) => ({ generated_at: gen || G, latest: [art('p1')], leagues });
  const bk = (mine, reads) => newsGate(mine, prod, { reads }, now).checks.buckets;
  const rd = (o, gen) => ({ generated_at: gen || G, reads: { 'hockey/nhl': o } });
  const empty = mineWith({ 'hockey/nhl': [] });
  let b = bk(empty, rd({ ok: 3, fail: 0, n_raw: 40, n_relevant: 0 }));
  t('relevant-zero, all reads ok: SKIPPED, buckets ok', [b.ok, b.gaps, b.skipped_verified_zero.length, b.reads_stamp_match], [true, [], 1, true]);
  t('relevant-zero skip keeps old rule beside it (ok_v9 false, gaps_v9 lists bucket)', [b.ok_v9, b.gaps_v9], [false, ['hockey/nhl']]);
  b = bk(empty, rd({ ok: 3, fail: 0, n_raw: 40, n_relevant: 0 }, '2026-10-01T23:59:00.000Z'));
  t('stamp mismatch: REJECTED (closed)', [b.ok, b.gaps, b.reads_stamp_match], [false, ['hockey/nhl'], false]);
  b = bk(empty, rd({ ok: 2, fail: 1, n_raw: 40, n_relevant: 0 }));
  t('fail>0: REJECTED (closed)', [b.ok, b.gaps], [false, ['hockey/nhl']]);
  b = bk(empty, rd({ ok: 0, fail: 0, n_raw: 0, n_relevant: 0 }));
  t('ok=0 (no read succeeded): REJECTED (closed)', [b.ok, b.gaps], [false, ['hockey/nhl']]);
  b = bk(empty, undefined);
  t('reads missing entirely: REJECTED (closed)', [b.ok, b.gaps, b.reads_stamp_match], [false, ['hockey/nhl'], false]);
  b = bk(empty, { generated_at: G, reads: {} });
  t('reads present but no record for the bucket: REJECTED (closed)', [b.ok, b.gaps], [false, ['hockey/nhl']]);
  b = bk(empty, rd({ ok: 3, fail: 0, n_raw: 40, n_relevant: 2 }));
  t('source items relevant (n_relevant>0) with empty worker bucket: still REJECTED', [b.ok, b.gaps, b.skipped_verified_zero.length], [false, ['hockey/nhl'], 0]);
  b = bk(mineWith({ 'hockey/nhl': [art('nhl story')] }), rd({ ok: 3, fail: 0, n_raw: 40, n_relevant: 1 }));
  t('worker bucket populated: no gap, nothing skipped', [b.ok, b.gaps, b.skipped_verified_zero.length], [true, [], 0]);
  console.log(f ? f + ' FAIL' : 'ALL OK');
  process.exit(f ? 1 : 0);
})();
