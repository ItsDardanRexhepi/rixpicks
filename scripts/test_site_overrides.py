#!/usr/bin/env python3
"""Changes made on the Trinity chat that last (scripts/site_overrides.py): wording, style and new content.

- wording changes only the text people read, never a script, a style or a tag, and can never become markup;
- the style block carries no markup, no @import, no expression() and no script URL;
- new content keeps only plain tags and attributes: no script, handler, frame, form or script URL survives;
- applied twice it is the same page, and a slot that no longer has content is emptied;
- run as a script it patches a built page in place;
- both builder twins apply it at the end of a build, and a tree without the module builds unchanged.
Builds run in throwaway trees with the network blocked (dead proxy). No side effects.
Run: python3 scripts/test_site_overrides.py"""
import json, os, shutil, subprocess, sys, tempfile

SD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SD)
sys.path.insert(0, SD)
import site_overrides as SO  # noqa: E402
sys.path.insert(0, ROOT)
from fixtures.card_contract import stamped  # noqa: E402

failures = 0


def check(name, ok, detail=''):
    global failures
    print(('OK   ' if ok else 'FAIL ') + name + ('' if ok or not detail else '  [%s]' % (detail,)))
    if not ok:
        failures += 1


PAGE = ('<!DOCTYPE html><html><head><style>.foot{color:red}</style></head><body>'
        '<div class="state" id="st-home"><div class="sect">Today&rsquo;s picks</div><p>Bet responsibly.</p>'
        '<a href="x" title="Bet responsibly.">link</a>'
        '<script>var s="Bet responsibly.";</script></div>'
        '<div class="state" id="st-wooder"><p>Wooder</p></div>'
        '<div class="foot">Bet responsibly. <span>Share</span></div></body></html>')


def tree(text=None, style=None, blocks=None):
    d = tempfile.mkdtemp(prefix='rp-overrides-')
    os.makedirs(os.path.join(d, 'slates'))
    if text is not None:
        json.dump(text, open(os.path.join(d, SO.TEXT), 'w'))
    if style is not None:
        open(os.path.join(d, SO.STYLE), 'w').write(style)
    if blocks is not None:
        json.dump(blocks, open(os.path.join(d, SO.BLOCKS), 'w'))
    return d


# wording: the text people read, and only that
d = tree(text=[{'find': 'Bet responsibly.', 'replace': 'Please bet responsibly.'},
               {'find': 'Today’s picks', 'replace': 'Tonight’s picks'},
               {'find': 'Wooder', 'replace': '<script>alert(1)</script>'}])
out = SO.apply(PAGE, d)
check('wording replaced in the text people read', out.count('Please bet responsibly.') == 2, out)
check('an entity in the page is matched as the character it shows', 'Tonight' in out)
check('a script is never touched', 'var s="Bet responsibly.";' in out)
check('an attribute is never touched', 'title="Bet responsibly."' in out)
check('a replacement can never become markup', '<script>alert(1)</script>' not in out
      and '&lt;script&gt;alert(1)&lt;/script&gt;' in out, out)
check('a find too short to be safe is ignored', SO.apply('<p>ab</p>', tree(text=[{'find': 'ab', 'replace': 'x'}])) == '<p>ab</p>')

# style: no markup, no import, no script
css = ('.foot{color:blue}</style><script>alert(1)</script>@import url(https://evil.example/x.css);'
       '.a{background:url(javascript:alert(1))}.b{width:expression(alert(1))}.c{background:url(img/x.png)}'
       '.d{background:url(https://cdn.example/x.png)}.e{background:url(data:text/html,hi)}')
c = SO.clean_style(css)
check('the style carries no markup', '<' not in c, c)
check('no @import', '@import' not in c.lower(), c)
check('no script URL and no expression()', 'javascript' not in c.lower() and 'expression(' not in c.lower(), c)
check('a relative or https image is kept, any other scheme is not',
      'url("img/x.png")' in c and 'url("https://cdn.example/x.png")' in c and 'data:' not in c, c)
hostile = SO.apply(PAGE, tree(style=css))
check('the style the page gets is the cleaned one', '<script>alert(1)</script>' not in hostile
      and '@import' not in hostile.lower() and 'javascript' not in hostile.lower(), hostile[:400])
out = SO.apply(PAGE, tree(style='.foot{color:blue}'))
check('the style goes in one block before </head>', out.count('<style id="site-style">.foot{color:blue}</style></head>') == 1)
check('applied again it is still one block', SO.apply(out, tree(style='.foot{color:green}')).count('id="site-style"') == 1)

# content: plain tags only
bad = ('<p onclick="alert(1)" class="note">Hi <b>there</b></p><script>alert(1)</script><img src=x onerror=alert(1)>'
       '<img src="javascript:alert(1)"><a href="javascript:alert(1)">x</a><a href="//evil.example">y</a>'
       '<iframe src="https://evil.example"></iframe><form action="https://evil.example"><input name=p></form>'
       '<svg><script>alert(1)</script></svg><a href="https://wooder.example/t" target="_blank">tickets</a>'
       '<img src="assets/uploads/ticket.jpg" alt="ticket"><style>body{display:none}</style>')
cl = SO.clean_html(bad)
for frag, what in (('onclick', 'a handler'), ('<script', 'a script'), ('onerror', 'an onerror'),
                   ('javascript:', 'a script URL'), ('//evil', 'a protocol-relative link'), ('<iframe', 'a frame'),
                   ('<form', 'a form'), ('<input', 'an input'), ('<svg', 'an svg'), ('<style', 'a style'),
                   ('target=', 'an attribute off the list'), ('alert(1)', 'script text')):
    check(f'content: {what} does not survive', frag not in cl, cl)
check('content: plain tags, an https link and an uploaded picture survive',
      '<p class="note">Hi <b>there</b></p>' in cl and 'href="https://wooder.example/t"' in cl
      and '<img src="assets/uploads/ticket.jpg" alt="ticket">' in cl, cl)
blocks = [{'slot': 'home-top', 'html': '<p>Big night</p>'}, {'slot': 'wooder-top', 'html': '<p>New tickets</p>'},
          {'slot': 'footer', 'html': '<small>Thanks</small>'}, {'slot': 'nowhere"><script>', 'html': '<p>x</p>'}]
out = SO.apply(PAGE, tree(blocks=blocks))
check('a block lands at the top of its tab', '<div class="state" id="st-home"><div class="site-blocks" data-slot="home-top">'
      '<div class="site-block"><p>Big night</p></div>' in out, out)
check('and at the top of another', 'id="st-wooder"><div class="site-blocks" data-slot="wooder-top">' in out)
check('and above the footer', '<div class="site-blocks" data-slot="footer"><div class="site-block"><small>Thanks'
      '</small></div><!--/site-blocks--></div><div class="foot">' in out, out)
check('a slot name that is not a slot is ignored', '<script>' not in out.split('</head>')[1].replace(
    '<script>var s="Bet responsibly.";</script>', ''))
again = SO.apply(out, tree(blocks=blocks))
check('applied twice it is the same page', again == out)
emptied = SO.apply(out, tree(blocks=[]))
check('a slot with no content left is emptied', 'site-blocks' not in emptied and emptied == SO.apply(PAGE, tree()))

# the Trinity tab is never touched
TPAGE = PAGE.replace('<div class="foot">', '<div class="state" id="st-trinity"><p>Ask Trinity. Bet responsibly.</p>'
                     '<script>var t=1;</script></div><div class="foot">')
out = SO.apply(TPAGE, tree(text=[{'find': 'Bet responsibly.', 'replace': 'Changed.'}, {'find': 'Ask Trinity', 'replace': 'X'}],
                           blocks=[{'slot': 'trinity-top', 'html': '<p>sneaky</p>'}]))
check('wording never reaches the Trinity tab', '<p>Ask Trinity. Bet responsibly.</p>' in out and 'Changed.' in out, out)
check('nor does content', 'sneaky' not in out)

# run as a script: patch a built page in place
d = tree(text=[{'find': 'Bet responsibly.', 'replace': 'Please bet responsibly.'}])
open(os.path.join(d, 'index.html'), 'w').write(PAGE)
r = subprocess.run([sys.executable, os.path.join(SD, 'site_overrides.py'), os.path.join(d, 'index.html')],
                   capture_output=True, text=True)
check('run as a script it patches the built page in place',
      r.returncode == 0 and 'Please bet responsibly.' in open(os.path.join(d, 'index.html')).read(), r.stdout + r.stderr)

# both builder twins apply it, and a tree without it builds unchanged
DEAD = 'http://127.0.0.1:9'
ENV = dict(os.environ, RP_REFRESH='1', http_proxy=DEAD, https_proxy=DEAD, HTTP_PROXY=DEAD, HTTPS_PROXY=DEAD)
MAN = {'date': '2099-10-01', 'date_label': 'Thursday, Oct 1', 'updated': 'Oct 1, 8:42 AM PT', 'record': '21-11',
       'units_pl': '+4.76u', 'units_ledger': None, 'yesterday': '', 'status_note': '', 'preview': False, 'parlay': None,
       'picks': []}


def build(builder, with_module, with_files):
    t = tempfile.mkdtemp(prefix='rp-overrides-build-')
    os.makedirs(os.path.join(t, 'scripts'))
    os.makedirs(os.path.join(t, 'slates'))
    shutil.copy(builder, os.path.join(t, 'scripts', 'build_gh_page_v2.py'))
    for f in ('index_v2.js', 'index_v2.css', 'game_page_template.html', 'team_page_template.html', 'poly_us.py'):
        src = os.path.join(SD, f)
        if os.path.exists(src):
            shutil.copy(src, os.path.join(t, 'scripts', f))
    for f in ('feed_arbiter.js', 'feed_registry.json', 'config_leagues.json'):
        shutil.copy(os.path.join(ROOT, f), os.path.join(t, f))
    json.dump([], open(os.path.join(t, 'slates', 'odds_prefill.json'), 'w'))
    if with_module:
        shutil.copy(os.path.join(SD, 'site_overrides.py'), os.path.join(t, 'scripts', 'site_overrides.py'))
    if with_files:
        json.dump([{'find': 'Bet responsibly.', 'replace': 'Please bet responsibly, always.'}],
                  open(os.path.join(t, SO.TEXT), 'w'))
        json.dump([{'slot': 'home-top', 'html': '<p class="note">Note from the chat</p><script>alert(1)</script>'}],
                  open(os.path.join(t, SO.BLOCKS), 'w'))
    json.dump(stamped(builder, MAN), open(os.path.join(t, 'manifest.json'), 'w'), indent=1)
    r = subprocess.run([sys.executable, 'scripts/build_gh_page_v2.py', 'manifest.json', 'index.html'], cwd=t,
                       env=ENV, capture_output=True, text=True, timeout=600)
    page = open(os.path.join(t, 'index.html')).read() if os.path.exists(os.path.join(t, 'index.html')) else ''
    return r.returncode, page, r.stderr[-400:]


for name in ('build_gh_page_v2.py', '_build_nocanon_v2.py'):
    rc, page, err = build(os.path.join(SD, name), True, True)
    check(f'{name}: a build applies the chat\'s wording', rc == 0 and 'Please bet responsibly, always.' in page, err)
    check(f'{name}: and its content, cleaned', '<p class="note">Note from the chat</p>' in page
          and 'alert(1)' not in page, err)
    rc0, page0, err0 = build(os.path.join(SD, name), False, True)
    check(f'{name}: a tree without the module builds unchanged', rc0 == 0 and 'Note from the chat' not in page0, err0)

print('SITE OVERRIDES: ' + ('ALL OK' if not failures else f'{failures} FAILURES'))
sys.exit(1 if failures else 0)
