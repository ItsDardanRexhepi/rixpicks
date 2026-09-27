"""Validate a delivered NFL anytime-TD slate (contract slates/schema_v1.json) and publish it.

Usage: python3 scripts/ingest_nfl_slate.py <slate.json>
Writes slates/nfl_latest.json and archives a copy under slates/archive/.
Fails loudly on any contract violation; never publishes a partial slate.
"""
import json, re, sys, datetime, os

WINDOWS = ('sun-early', 'sun-afternoon', 'sun-night', 'mon-night', 'thu-night')
URL_RE = re.compile(r'^https://([a-z0-9-]+\.)*(draftkings\.com|kalshi\.com)(/|$)', re.I)
ODDS_RE = re.compile(r'^[+-]\d{2,5}$')

def die(msg):
    print('SLATE REJECTED: ' + msg, file=sys.stderr)
    sys.exit(1)

def req_str(d, k, ctx):
    v = d.get(k)
    if not isinstance(v, str) or not v.strip():
        die('%s.%s must be a non-empty string' % (ctx, k))
    return v.strip()

def opt_url(d, k, ctx):
    v = d.get(k)
    if v is None:
        return None
    if not isinstance(v, str) or not URL_RE.match(v):
        die('%s.%s must be an https:// draftkings.com or kalshi.com URL' % (ctx, k))
    return v


def price_form(d, ctx, combined=False):
    """Fail-closed price rule, mirrors builder rpLegPx: exactly one price form.
    American string OR native contract cents (price_c int 1-99 + price_type contract_cents).
    Both or neither -> reject whole slate."""
    ok = d.get('odds') if not combined else d.get('combined_odds')
    pc_key = 'price_c' if not combined else 'combined_price_c'
    has_a = isinstance(ok, str) and ok.strip() != ''
    pc = d.get(pc_key)
    has_c = isinstance(pc, int) and not isinstance(pc, bool) and 1 <= pc <= 99 \
        and d.get('price_type') == 'contract_cents'
    if has_a == has_c:
        die('%s must carry exactly one price form (American odds OR contract_cents, never both/neither)' % ctx)
    if has_a and not ODDS_RE.match(ok.strip()):
        die('%s odds must be American odds like +115 or -140' % ctx)

def check_pick(p, ctx):
    req_str(p, 'player', ctx)
    req_str(p, 'team', ctx)
    req_str(p, 'matchup', ctx)

def main(path):
    try:
        j = json.load(open(path))
    except Exception as e:
        die('unreadable JSON: %s' % e)
    if j.get('version') != 1:
        die('version must be 1')
    if j.get('source') != 'wooder-ice':
        die('source must be "wooder-ice"')
    if j.get('kind') != 'nfl-anytime-td':
        die('kind must be "nfl-anytime-td"')
    gen = req_str(j, 'generated_at', 'root')
    try:
        datetime.datetime.fromisoformat(gen.replace('Z', '+00:00'))
    except Exception:
        die('generated_at must be ISO-8601')
    if j.get('window') not in WINDOWS:
        die('window must be one of %s' % ', '.join(WINDOWS))
    req_str(j, 'window_label', 'root')

    dk = j.get('dk')
    if not isinstance(dk, dict):
        die('dk object required')
    singles = dk.get('singles') or []
    parlays = dk.get('parlays') or []
    if not isinstance(singles, list) or not isinstance(parlays, list):
        die('dk.singles and dk.parlays must be arrays')
    for i, s in enumerate(singles):
        c = 'dk.singles[%d]' % i
        check_pick(s, c)
        price_form(s, c)
        opt_url(s, 'link', c)
    for i, p in enumerate(parlays):
        c = 'dk.parlays[%d]' % i
        legs = p.get('legs')
        if not isinstance(legs, list) or not (2 <= len(legs) <= 8):
            die('%s.legs must hold 2-8 legs' % c)
        for k, l in enumerate(legs):
            check_pick(l, '%s.legs[%d]' % (c, k))
            price_form(l, '%s.legs[%d]' % (c, k))
        price_form(p, c + '.combined', combined=True)
        if isinstance(p.get('combined_odds'), str) and p['combined_odds'].strip():
            req_str(p, 'est_payout', c)
        opt_url(p, 'link', c)
        opt_url(p, 'pm', c)

    kal = j.get('kalshi')
    if not isinstance(kal, dict):
        die('kalshi object required')
    top = kal.get('top10') or []
    if not isinstance(top, list) or len(top) > 10:
        die('kalshi.top10 must be an array of at most 10')
    for i, t in enumerate(top):
        c = 'kalshi.top10[%d]' % i
        check_pick(t, c)
        prob = t.get('prob')
        if not isinstance(prob, (int, float)) or isinstance(prob, bool) or not (0 <= prob <= 1):
            die('%s.prob must be 0-1' % c)
        pc = t.get('price_c')
        if not isinstance(pc, int) or isinstance(pc, bool) or not (0 <= pc <= 100):
            die('%s.price_c must be an int 0-100' % c)
        req_str(t, 'link', c)
        opt_url(t, 'link', c)
    bb = kal.get('bankroll_builder')
    if bb is not None:
        if not isinstance(bb, dict):
            die('kalshi.bankroll_builder must be an object')
        req_str(bb, 'matchup', 'kalshi.bankroll_builder')
        picks = bb.get('picks')
        if not isinstance(picks, list) or not (3 <= len(picks) <= 5):
            die('kalshi.bankroll_builder.picks must hold 3-5 picks')
        for i, b in enumerate(picks):
            c = 'kalshi.bankroll_builder.picks[%d]' % i
            check_pick(b, c)
            pc = b.get('price_c')
            if not isinstance(pc, int) or isinstance(pc, bool) or not (0 <= pc <= 100):
                die('%s.price_c must be an int 0-100' % c)
            req_str(b, 'link', c)
            opt_url(b, 'link', c)
        ec = bb.get('est_cost_c')
        if ec is not None and (not isinstance(ec, int) or isinstance(ec, bool) or ec < 0):
            die('kalshi.bankroll_builder.est_cost_c must be a non-negative int')

    if not singles and not parlays and not top and not bb:
        die('slate carries no content at all')

    out = {'version': 1, 'source': 'wooder-ice', 'kind': 'nfl-anytime-td',
           'generated_at': gen, 'window': j['window'], 'window_label': j['window_label'].strip(),
           'dk': {'singles': singles, 'parlays': parlays}, 'kalshi': {'top10': top, 'bankroll_builder': bb}}
    os.makedirs('slates/archive', exist_ok=True)
    day = gen[:10]
    arch = 'slates/archive/nfl_%s_%s.json' % (day, j['window'])
    json.dump(out, open('slates/nfl_latest.json', 'w'), indent=1)
    json.dump(out, open(arch, 'w'), indent=1)
    print('slate OK: %d singles, %d parlays, %d kalshi top, builder=%s -> slates/nfl_latest.json (+ %s)'
          % (len(singles), len(parlays), len(top), 'yes' if bb else 'no', arch))

if __name__ == '__main__':
    if len(sys.argv) != 2:
        die('usage: python3 scripts/ingest_nfl_slate.py <slate.json>')
    main(sys.argv[1])
