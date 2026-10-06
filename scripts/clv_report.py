#!/usr/bin/env python3
"""clv_report.py - internal closing-line-value (CLV) ledger. Read-only on the record.

For every graded pick - each history.json row, plus grades still queued in record_request.json
(marked queued; --no-queued leaves them out) - this finds the published card pick it was graded
under (the same card-date rule and grade key record_final.py uses), then the CLOSE:
  - the last book snapshot in this repo's git history taken before the game began:
    slates/odds_prefill.json for moneylines, slates/odds_prefill_st.json for spreads and totals.
    A snapshot's time is its commit's author date (the refresh fetched before it committed, and a
    rebase keeps the author date). It counts only when that time is before the card's commence
    AND before the commence the snapshot itself lists for the game (never a live line), and no more
    than MAX_AGE_MIN (180) minutes before the card's commence (an older line is no close);
  - each book (draftkings, fanduel, betmgm, espnbet, hardrockbet, betrivers; a book listed under
    state_templates counts too) is de-vigged multiplicatively on its own two-way market: the picked
    side's implied probability over the sum of both sides' implied probabilities;
  - spreads use the card's HOME-basis line: a book counts only when its spread_home_pts equals the
    pick's line exactly, and the picked side's price is used (home -> spread_home_price, away ->
    spread_away_price). Totals: total_pts equals the line, over_price / under_price;
  - close_novig = the median of those de-vigged probabilities across at least 3 books; fewer books
    at the pick's line means no close (the reason is listed, nothing is guessed).
LOCKED cents (locked_c) come from the card price: the accepted entry's cents when the card pick is
the accepted entry (core/accepted_entry.py); else the card's Kalshi cents when they ARE the card
price (cents_to_american(kalshi.cents) == the card's American price); else the whole cents behind
the card's American price when they convert back to it exactly (62c -> -163); else the price's
implied probability in cents. clv_c = close_novig * 100 - locked_c: positive means the pick was
locked at a better price than the close.

Writes ONLY the ledger (default slates/clv_ledger.json; --out for another path). It never writes
history.json, manifest.json, record_done.json or record_request.json and is not part of grading:
record_final.py does not call it and no workflow runs it. The ledger is internal - no
page renders it. Output is deterministic (no wall-clock stamp), so an unchanged input gives the
same file. Exit 0 on success, 2 when the repo or its history cannot be read.

  python3 scripts/clv_report.py [--root DIR] [--out PATH] [--date YYYY-MM-DD] [--no-queued] [--max-age-min N]
"""
import argparse, glob, json, os, statistics, subprocess, sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..'))
# the grading rules themselves (pure helpers only - nothing here calls main() or writes a record file)
from record_final import _market_class, _pt_date, american, card_date_of, card_key  # noqa: E402
from core.accepted_entry import accepted_entry  # noqa: E402
from core.units import cents_to_american  # noqa: E402

BOOKS = ('draftkings', 'fanduel', 'betmgm', 'espnbet', 'hardrockbet', 'betrivers')
MIN_BOOKS = 3
SNAP_FILE = {'ml': 'slates/odds_prefill.json', 'spread': 'slates/odds_prefill_st.json', 'total': 'slates/odds_prefill_st.json'}
GAME_WINDOW = timedelta(hours=12)  # a snapshot's listing of the game must be this close to the card's commence
# a 'close' older than this is no close (Oct 1: the refresh lane stopped at 08:50 PT and the newest snapshot
# listing that night's NHL games was 32 hours old); --max-age-min overrides
MAX_AGE_MIN = 180
METHOD = {
    'close': 'last snapshot (commit author time) before both the card commence and the snapshot\'s own commence for the game, '
             'at most {max_age_min} min before the card commence',
    'files': SNAP_FILE,
    'devig': 'multiplicative, per book, on its own two-way market',
    'consensus': f'median across >= {MIN_BOOKS} books',
    'books': list(BOOKS),
    'spread_line': 'HOME basis: book spread_home_pts == card line; picked side\'s price',
    'locked_c': 'accepted-entry cents, else Kalshi cents that are the card price, else whole cents behind the card American price, else its implied cents',
    'clv_c': 'close_novig * 100 - locked_c (positive = locked better than the close)',
}


def _git(root, *args):
    r = subprocess.run(['git', '-C', root, *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f'git {" ".join(args)}: {r.stderr.strip()}')
    return r.stdout


def _when(iso):
    try:
        t = datetime.fromisoformat(str(iso).replace('Z', '+00:00'))
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo else None


def implied(a):
    """Implied probability of an American price (with the vig in it)."""
    return Decimal(100) / (Decimal(a) + 100) if a > 0 else Decimal(-a) / (Decimal(-a) + 100)


def _price(v):
    # an American price as the snapshot stores it: an int (an integral float or int-like string too), never a bool
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return american(v)


def _same_line(a, b):
    try:
        return a is not None and b is not None and Decimal(str(a)) == Decimal(str(b))
    except (InvalidOperation, ValueError):
        return False


def _norm(s):
    return ''.join(ch for ch in str(s or '').lower() if ch.isalnum())


class Snapshots:
    """Every committed version of one snapshot file, by commit author time (cached reads)."""

    def __init__(self, root, path):
        self.root, self.path, self._blobs = root, path, {}
        self.commits = []  # (author time, sha), newest first
        for ln in _git(root, 'log', '--format=%H %aI', '--', path).splitlines():
            sha, _, iso = ln.strip().partition(' ')
            t = _when(iso)
            if sha and t:
                self.commits.append((t, sha))
        self.commits.sort(reverse=True)

    def load(self, sha):
        if sha not in self._blobs:
            try:
                self._blobs[sha] = json.loads(_git(self.root, 'show', f'{sha}:{self.path}'))
            except (RuntimeError, ValueError):
                self._blobs[sha] = None
        return self._blobs[sha]

    def before(self, cutoff):
        return [(t, h) for t, h in self.commits if t < cutoff]


def _find_game(snap, away, home, commence):
    """The snapshot's entry for this game (same teams, listed commence within GAME_WINDOW of the
    card's), nearest first; None when absent."""
    if not isinstance(snap, list):
        return None
    hits = []
    for g in snap:
        if not isinstance(g, dict) or not isinstance(g.get('books'), dict):
            continue
        if (g.get('away'), g.get('home')) != (away, home) and (_norm(g.get('away')), _norm(g.get('home'))) != (_norm(away), _norm(home)):
            continue
        gc = _when(g.get('commence'))
        if gc and abs(gc - commence) <= GAME_WINDOW:
            hits.append((abs(gc - commence), gc, g))
    return min(hits, key=lambda x: x[0])[1:] if hits else None


def _books(g):
    out = {}
    st = g['books'].get('state_templates')
    for name in BOOKS:
        b = g['books'].get(name)
        if not isinstance(b, dict) and isinstance(st, dict):
            b = st.get(name)
        if isinstance(b, dict):
            out[name] = b
    return out


def devig_side(book, mc, side, line):
    """Multiplicative no-vig probability of the picked side at one book, or None when the book has
    no two-way market at the pick's line."""
    if mc == 'ml':
        if side not in ('home', 'away'):
            return None
        mine, other = (book.get('home_ml'), book.get('away_ml')) if side == 'home' else (book.get('away_ml'), book.get('home_ml'))
    elif mc == 'spread':
        if side not in ('home', 'away') or not _same_line(book.get('spread_home_pts'), line):
            return None
        hp, ap = book.get('spread_home_price'), book.get('spread_away_price')
        mine, other = (hp, ap) if side == 'home' else (ap, hp)
    elif mc == 'total':
        if side not in ('over', 'under') or not _same_line(book.get('total_pts'), line):
            return None
        mine, other = (book.get('over_price'), book.get('under_price')) if side == 'over' else (book.get('under_price'), book.get('over_price'))
    else:
        return None
    mine, other = _price(mine), _price(other)
    if mine is None or other is None:
        return None
    a, b = implied(mine), implied(other)
    return a / (a + b)


def close_for(snaps, cp, max_age_min=MAX_AGE_MIN):
    """(close dict, None) or (None, reason)."""
    mc, side, line = _market_class(cp), cp.get('side'), cp.get('line')
    g = cp.get('game') or {}
    commence = _when(g.get('commence'))
    if commence is None:
        return None, 'card pick has no readable commence'
    cands = snaps.before(commence)
    if not cands:
        oldest = snaps.commits[-1][0].isoformat() if snaps.commits else 'none'
        return None, f'no {snaps.path} snapshot before {commence.isoformat()} in git history (oldest {oldest})'
    for t, sha in cands:
        hit = _find_game(snaps.load(sha), g.get('away'), g.get('home'), commence)
        if hit is None:
            continue
        listed, entry = hit
        if t >= listed:
            continue  # the snapshot itself says the game had begun: live lines, never a close
        per = {}
        for name, book in sorted(_books(entry).items()):
            p = devig_side(book, mc, side, line)
            if p is not None:
                per[name] = p
        base = {'close_ts': t.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z'), 'close_commit': sha[:12],
                'close_file': snaps.path, 'close_listed_commence': listed.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z'),
                'close_age_min': int((commence - t).total_seconds() // 60)}
        if base['close_age_min'] > max_age_min:
            return None, (f'the last pre-commence snapshot listing the game ({base["close_ts"]}, {sha[:12]}) is '
                          f'{base["close_age_min"]} min before the card commence, over the {max_age_min} min limit - no close')
        if len(per) < MIN_BOOKS:
            seen = sorted({str(b.get('spread_home_pts' if mc == 'spread' else 'total_pts')) for b in _books(entry).values()}) if mc != 'ml' else []
            return None, (f'{len(per)} book(s) priced the pick at its line in the last pre-commence snapshot ({base["close_ts"]}, '
                          f'{sha[:12]}), need {MIN_BOOKS}' + (f'; lines there: {", ".join(seen)}' if seen else ''))
        base['close_books'] = {k: float(round(v, 4)) for k, v in per.items()}
        base['n_books'] = len(per)
        base['close_novig'] = float(round(statistics.median(per.values()), 4))
        return base, None
    return None, f'game {g.get("away")} at {g.get("home")} not listed in any pre-commence {snaps.path} snapshot'


def locked_cents(cp):
    """(locked cents, basis) from the card price, or (None, reason)."""
    price = american(cp.get('card_american')) if cp.get('card_american') is not None else american(cp.get('odds'))
    if price is None:
        return None, 'card price missing'
    acc = accepted_entry(cp)
    if acc is not None:
        return Decimal(acc['entry_c']), 'accepted_entry'
    k = cp.get('kalshi')
    if isinstance(k, dict) and k.get('cents') is not None:
        try:
            if cents_to_american(k['cents']) == price:
                return Decimal(str(k['cents'])), 'kalshi_cents'
        except (ValueError, InvalidOperation, TypeError):
            pass
    imp = implied(price) * 100
    whole = imp.quantize(Decimal('1'))
    try:
        if Decimal(0) < whole < Decimal(100) and cents_to_american(whole) == price:
            return whole, 'card_cents'
    except ValueError:
        pass
    return imp.quantize(Decimal('0.01')), 'card_american_implied'


def card_index(root):
    """card date -> [card picks] over every manifests/ snapshot and the live manifest.json, under
    record_final's rule: the snapshot's date must equal its card date (card_date_of), and a pick's own
    PT game date is the card's date or the next day."""
    idx = {}
    for path in sorted(glob.glob(os.path.join(root, 'manifests', 'manifest-*.json'))) + [os.path.join(root, 'manifest.json')]:
        try:
            snap = json.load(open(path))
        except (OSError, ValueError):
            continue
        day = card_date_of(snap) if isinstance(snap, dict) else None
        if not day or snap.get('date') != day:
            continue
        nxt = (datetime.strptime(day, '%Y-%m-%d') + timedelta(days=1)).date().isoformat()
        for p in snap.get('picks') or []:
            if isinstance(p, dict):
                pd = _pt_date((p.get('game') or {}).get('commence'))
                if pd and day <= pd <= nxt:
                    idx.setdefault(day, []).append(p)
    return idx


def resolve(idx, card_date, name, grade_id=None):
    """(card pick, None) or (None, reason): every published copy must agree on the pick's identity
    (grade key) and price."""
    copies = [p for p in idx.get(card_date, []) if p.get('name') == name]
    if grade_id is not None:
        copies = [p for p in copies if card_key(p) == str(grade_id)]
    if not copies:
        return None, f'not on a published {card_date} card'
    if any(card_key(p) is None for p in copies):
        return None, 'the card pick has no grade key (no event id or market class)'
    if len({(card_key(p), str(p.get('card_american')), str(p.get('odds')), str(p.get('units'))) for p in copies}) != 1:
        return None, f'published copies of the {card_date} card disagree on this pick'
    return copies[0], None


def population(root, queued=True, date=None):
    rows = []
    hist = json.load(open(os.path.join(root, 'history.json')))
    on_record = set()
    for d in hist.get('days') or []:
        for p in d.get('picks') or []:
            if isinstance(p, dict) and p.get('result') in ('W', 'L', 'P'):
                rows.append({'card_date': d.get('date'), 'name': p.get('name'), 'result': p['result'], 'source': 'history',
                             'row_odds': p.get('odds')})
                on_record.add((d.get('date'), p.get('name')))
    rq = os.path.join(root, 'record_request.json')
    if queued and os.path.exists(rq):
        try:
            reqs = json.load(open(rq)).get('requests') or []
        except (OSError, ValueError, AttributeError):
            reqs = []
        for q in reqs:
            if not isinstance(q, dict) or not q.get('card_date') or (q['card_date'], q.get('pick')) in on_record:
                continue
            rows.append({'card_date': q['card_date'], 'name': q.get('pick'), 'grade_id': q.get('grade_id'),
                         'result': {'WON': 'W', 'LOST': 'L', 'PUSH': 'P'}.get(q.get('result'), q.get('result')),
                         'source': 'record_request (queued, not yet on the record)', 'row_odds': q.get('locked_american')})
    if date:
        rows = [r for r in rows if r['card_date'] == date]
    return sorted(rows, key=lambda r: (str(r['card_date']), str(r['name'])))


def build(root, queued=True, date=None, max_age_min=MAX_AGE_MIN):
    idx = card_index(root)
    snaps = {}
    out = []
    for r in population(root, queued, date):
        row = {k: r[k] for k in ('card_date', 'name', 'result', 'source')}
        cp, why = resolve(idx, r['card_date'], r['name'], r.get('grade_id'))
        if cp is None:
            out.append(dict(row, status='no_close', reason=why))
            continue
        mc = _market_class(cp)
        price = american(cp.get('card_american')) if cp.get('card_american') is not None else american(cp.get('odds'))
        row.update({'grade_key': card_key(cp), 'market_class': mc, 'side': cp.get('side'), 'line': cp.get('line'),
                    'card_american': price})
        if r.get('row_odds') is not None and american(r['row_odds']) != price:
            out.append(dict(row, status='no_close', reason=f'row odds {r["row_odds"]!r} differ from the card price {price!r}'))
            continue
        lc, basis = locked_cents(cp)
        if lc is None:
            out.append(dict(row, status='no_close', reason=basis))
            continue
        row.update({'locked_c': float(lc), 'locked_basis': basis})
        if mc not in SNAP_FILE:
            out.append(dict(row, status='no_close', reason=f'market class {mc!r} has no book snapshot file'))
            continue
        path = SNAP_FILE[mc]
        if path not in snaps:
            snaps[path] = Snapshots(root, path)
        close, why = close_for(snaps[path], cp, max_age_min)
        if close is None:
            out.append(dict(row, status='no_close', reason=why))
            continue
        row.update(close)
        row['clv_c'] = float((Decimal(str(close['close_novig'])) * 100 - lc).quantize(Decimal('0.01')))
        row['status'] = 'ok'
        out.append(row)
    ok = [r for r in out if r['status'] == 'ok']
    summary = {'rows': len(out), 'with_close': len(ok),
               'mean_clv_c': float(round(Decimal(str(statistics.mean(r['clv_c'] for r in ok))), 2)) if ok else None,
               'beat_close': sum(1 for r in ok if r['clv_c'] > 0)}
    return {'about': 'Internal closing-line-value ledger (scripts/clv_report.py). Not rendered on any page; not part of grading.',
            'method': dict(METHOD, close=METHOD['close'].format(max_age_min=max_age_min)), 'summary': summary, 'rows': out}


def main(argv=None):
    ap = argparse.ArgumentParser(description='internal CLV ledger (read-only on the record)')
    ap.add_argument('--root', default=os.path.normpath(os.path.join(HERE, '..')))
    ap.add_argument('--out', default=None, help='ledger path (default <root>/slates/clv_ledger.json)')
    ap.add_argument('--date', default=None, help='only this card date (YYYY-MM-DD)')
    ap.add_argument('--no-queued', action='store_true', help='leave out grades still queued in record_request.json')
    ap.add_argument('--max-age-min', type=int, default=MAX_AGE_MIN, help=f'oldest usable close, minutes before commence (default {MAX_AGE_MIN})')
    a = ap.parse_args(argv)
    root = os.path.abspath(a.root)
    try:
        _git(root, 'rev-parse', '--git-dir')
        ledger = build(root, queued=not a.no_queued, date=a.date, max_age_min=a.max_age_min)
    except (RuntimeError, OSError, ValueError) as e:
        print(f'clv_report: cannot read the repo or its history: {e}', file=sys.stderr)
        return 2
    out = a.out or os.path.join(root, 'slates', 'clv_ledger.json')
    with open(out, 'w') as f:
        json.dump(ledger, f, indent=1)
        f.write('\n')
    for r in ledger['rows']:
        if r['status'] == 'ok':
            print(f"{r['card_date']} {r['name']:<28} close {r['close_novig'] * 100:6.2f}% ({r['n_books']} books, {r['close_ts']}, {r['close_age_min']} min pre) "
                  f"locked {r['locked_c']:6.2f}c [{r['locked_basis']}] CLV {r['clv_c']:+.2f}c")
        else:
            print(f"{r['card_date']} {r['name']:<28} no close: {r['reason']}")
    s = ledger['summary']
    print(f"clv ledger: {s['with_close']}/{s['rows']} with a close, mean CLV {s['mean_clv_c']}c, beat the close {s['beat_close']} -> {out}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
