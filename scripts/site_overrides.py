#!/usr/bin/env python3
"""Changes asked for on the Trinity chat that last: wording, style and new content, applied to every build.

The home page is rebuilt from scripts/build_gh_page_v2.py every few minutes, so a change made in index.html
itself is gone by the next refresh. The people signed in on the chat change the site through three data files
instead, and both builder twins apply them at the end of every build:

  slates/site_text.json    wording: [{"find": "old words", "replace": "new words"}, ...]
                           applied to the text people read only - never inside a script, a style or a tag - and
                           always written back escaped, so a replacement can never become markup
  slates/site_style.css    extra style rules, appended in one <style id="site-style"> block; no markup, no
                           @import, no expression(), no script URL
  slates/site_blocks.json  new content: [{"slot": "home-top", "html": "<p>...</p>"}, ...]
                           a note, a banner, a picture or a link, cleaned to an allowlist of plain tags and
                           attributes before it is placed; slots are "<tab>-top" for each tab and "footer"

Nothing here runs anything: the wording is text, the style is CSS, and the content keeps only tags that cannot
run (no script, no handler, no frame, no form, no script URL). Run as a script it patches an already built page
in place, so a change shows now rather than at the next rebuild:  python3 scripts/site_overrides.py index.html
"""
import html
import json
import os
import re
import sys
from html.parser import HTMLParser

TEXT = 'slates/site_text.json'
STYLE = 'slates/site_style.css'
BLOCKS = 'slates/site_blocks.json'

MAX_TEXT = 100
MAX_BLOCKS = 40
MAX_BLOCK_CHARS = 20000
MAX_STYLE_CHARS = 30000

_SEGMENTS = re.compile(r'(<script\b.*?</script\s*>|<style\b.*?</style\s*>|<!--.*?-->|<[^>]*>)', re.I | re.S)


def _load_json(root, rel, default):
    try:
        with open(os.path.join(root, rel), encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


# --------------------------------------------------------------------------------------------------- wording
def _pairs(root):
    raw = _load_json(root, TEXT, [])
    if isinstance(raw, dict):
        raw = raw.get('replace') or raw.get('text') or []
    out = []
    for r in raw if isinstance(raw, list) else []:
        if isinstance(r, dict) and isinstance(r.get('find'), str) and isinstance(r.get('replace'), str):
            find, rep = r['find'], r['replace']
            if 2 < len(find) <= 500 and len(rep) <= 2000 and find != rep:
                out.append((find, rep))
    return out[:MAX_TEXT]


def apply_text(page, pairs):
    """Replace words in the text people read. A segment is touched only when it contains a `find`; it is then
    unescaped, replaced and escaped again, so neither side of a pair can ever produce a tag."""
    if not pairs:
        return page
    parts = _SEGMENTS.split(page)
    for i in range(0, len(parts), 2):                  # even parts are text between tags
        seg = parts[i]
        if not seg or not seg.strip():
            continue
        plain = html.unescape(seg)
        new = plain
        for find, rep in pairs:
            if find in new:
                new = new.replace(find, rep)
        if new != plain:
            parts[i] = html.escape(new, quote=False)
    return ''.join(parts)


# ----------------------------------------------------------------------------------------------------- style
_URL = re.compile(r'url\(\s*([\'"]?)\s*([^)\'"]*)\1\s*\)', re.I)


def clean_style(css):
    css = str(css or '')[:MAX_STYLE_CHARS]
    css = css.replace('<', '').replace('\\', '')
    css = re.sub(r'@import[^;]*;?', '', css, flags=re.I)
    css = re.sub(r'expression\s*\(', '(', css, flags=re.I)
    css = re.sub(r'(?:java|vb)script\s*:', '', css, flags=re.I)
    css = re.sub(r'-moz-binding|behavior\s*:', '', css, flags=re.I)

    def url(m):
        u = m.group(2).strip()
        ok = u.startswith('https://') or (u and not re.match(r'^[a-z][a-z0-9+.-]*:', u, re.I) and not u.startswith('//'))
        return f'url("{u}")' if ok and '"' not in u else 'none'
    return _URL.sub(url, css)


def _style(root):
    try:
        with open(os.path.join(root, STYLE), encoding='utf-8') as f:
            return clean_style(f.read())
    except OSError:
        return ''


_STYLE_BLOCK = re.compile(r'<style id="site-style">.*?</style>', re.S)


def apply_style(page, css):
    page = _STYLE_BLOCK.sub('', page)
    if not css.strip():
        return page
    block = '<style id="site-style">' + css + '</style>'
    i = page.lower().rfind('</head>')
    return page[:i] + block + page[i:] if i >= 0 else block + page


# ---------------------------------------------------------------------------------------------------- content
ALLOWED_TAGS = {'p', 'br', 'strong', 'b', 'em', 'i', 'u', 'span', 'div', 'a', 'img', 'ul', 'ol', 'li', 'h2', 'h3',
                'h4', 'small', 'blockquote', 'hr'}
VOID = {'br', 'img', 'hr'}
DROP_WITH_CONTENT = {'script', 'style', 'iframe', 'object', 'embed', 'template', 'noscript', 'svg', 'math',
                     'textarea', 'select', 'form', 'frame', 'frameset', 'applet', 'title', 'head'}


def _safe_url(u, for_img=False):
    u = (u or '').strip()
    if not u or any(c in u for c in '"<>\\') or u.startswith('//'):
        return None
    if re.match(r'^[a-z][a-z0-9+.-]*:', u, re.I):
        return u if u.lower().startswith('https://') or (not for_img and u.lower().startswith('mailto:')) else None
    return u


class _Clean(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.skip, self.open = [], 0, []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in DROP_WITH_CONTENT:
            self.skip += 1
            return
        if self.skip or tag not in ALLOWED_TAGS:
            return
        kept = []
        for k, v in attrs:
            k = (k or '').lower()
            if k == 'class' and v and re.fullmatch(r'[\w -]{1,80}', v):
                kept.append(f'class="{v}"')
            elif k in ('alt', 'title') and v is not None:
                kept.append(f'{k}="{html.escape(v[:300])}"')
            elif k == 'href' and tag == 'a':
                u = _safe_url(v)
                if u:
                    kept.append(f'href="{html.escape(u)}"')
            elif k == 'src' and tag == 'img':
                u = _safe_url(v, for_img=True)
                if u:
                    kept.append(f'src="{html.escape(u)}"')
        if tag == 'a':
            kept.append('rel="noopener noreferrer"')
        if tag == 'img' and not any(a.startswith('src=') for a in kept):
            return
        self.out.append('<' + tag + (' ' + ' '.join(kept) if kept else '') + '>')
        if tag not in VOID:
            self.open.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag.lower() not in VOID and self.open and self.open[-1] == tag.lower():
            self.open.pop()
            self.out.append(f'</{tag.lower()}>')

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in DROP_WITH_CONTENT:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip or tag not in ALLOWED_TAGS or tag in VOID or tag not in self.open:
            return
        while self.open:
            t = self.open.pop()
            self.out.append(f'</{t}>')
            if t == tag:
                break

    def handle_data(self, data):
        if not self.skip:
            self.out.append(html.escape(data, quote=False))

    def result(self):
        while self.open:
            self.out.append(f'</{self.open.pop()}>')
        return ''.join(self.out)


def clean_html(fragment):
    """A fragment of content cut down to tags and attributes that cannot run anything."""
    p = _Clean()
    p.feed(str(fragment or '')[:MAX_BLOCK_CHARS])
    p.close()
    return p.result()


def _blocks(root):
    raw = _load_json(root, BLOCKS, [])
    if isinstance(raw, dict):
        raw = raw.get('blocks') or []
    out = {}
    for b in (raw if isinstance(raw, list) else [])[:MAX_BLOCKS]:
        if not isinstance(b, dict):
            continue
        slot, frag = str(b.get('slot') or ''), b.get('html')
        if not re.fullmatch(r'[a-z0-9_]{1,30}-top|footer', slot) or not isinstance(frag, str):
            continue
        clean = clean_html(frag)
        if clean.strip():
            out.setdefault(slot, []).append(clean)
    return out


_HOLDER = re.compile(r'<div class="site-blocks" data-slot="([a-z0-9_-]+)">.*?<!--/site-blocks--></div>', re.S)


def apply_blocks(page, blocks):
    page = _HOLDER.sub('', page)
    for slot, frags in blocks.items():
        holder = (f'<div class="site-blocks" data-slot="{slot}">' + ''.join(f'<div class="site-block">{f}</div>'
                                                                           for f in frags)
                  + '<!--/site-blocks--></div>')
        if slot == 'footer':
            i = page.find('<div class="foot">')
            if i >= 0:
                page = page[:i] + holder + page[i:]
            continue
        key = slot[:-len('-top')]
        m = re.search(r'<div class="state" id="st-' + re.escape(key) + r'"[^>]*>', page)
        if m:
            page = page[:m.end()] + holder + page[m.end():]
    return page


# --------------------------------------------------------------------------------------------------- the page
_TRINITY_OPEN = '<div class="state" id="st-trinity">'


def _trinity_span(page):
    """Where the Trinity tab sits in the page: the chat and its sign-in, which nothing here may change."""
    i = page.find(_TRINITY_OPEN)
    if i < 0:
        return None
    j = page.find('</script></div>', i)
    return (i, j + len('</script></div>')) if j >= 0 else (i, len(page))


def apply(page, root='.'):
    """Every change from the three files, applied to a built page. Safe to run on a page it already ran on.
    The Trinity tab is cut out first and put back untouched: wording and content never reach the chat."""
    span = _trinity_span(page)
    held = ''
    if span:
        held = page[span[0]:span[1]]
        page = page[:span[0]] + '\x00TRINITY\x00' + page[span[1]:]
    blocks = {k: v for k, v in _blocks(root).items() if k != 'trinity-top'}
    page = apply_text(page, _pairs(root))
    page = apply_style(page, _style(root))
    page = apply_blocks(page, blocks)
    return page.replace('\x00TRINITY\x00', held, 1) if span else page


def main(argv=None):
    a = list(sys.argv[1:] if argv is None else argv)
    if len(a) != 1:
        print('usage: python3 scripts/site_overrides.py index.html')
        return 2
    path = a[0]
    root = os.path.dirname(os.path.abspath(path)) or '.'
    with open(path, encoding='utf-8') as f:
        page = f.read()
    new = apply(page, root)
    if new != page:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(new)
    print(f'site overrides: {"applied" if new != page else "nothing to change"} in {os.path.basename(path)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
