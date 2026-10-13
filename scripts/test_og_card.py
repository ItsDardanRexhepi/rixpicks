"""The share image a link preview shows (og-card.png) is the brand card: 1200x630, the one from Sep 30. A daily
card's picture is shared on its own and never written over this file - on Oct 13 a text-message preview of the
site showed the Oct 10 picks three days later because a card publish had replaced it."""
import hashlib, os, struct, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, 'og-card.png')
SHA = 'f5e8afdeb42e4ea0c12048196b1d59b9fab1a6ba0cf020f8e4b158bf12d5fb9c'
def png_size(b):
    assert b[:8] == b'\x89PNG\r\n\x1a\n', 'og-card.png is not a PNG'
    w, h = struct.unpack('>II', b[16:24])
    return w, h
def main():
    b = open(PATH, 'rb').read()
    w, h = png_size(b)
    ok = True
    if (w, h) != (1200, 630):
        print(f'FAIL og-card.png is {w}x{h}, the brand card is 1200x630'); ok = False
    if hashlib.sha256(b).hexdigest() != SHA:
        print('FAIL og-card.png is not the brand card (sha mismatch) - a daily card must never overwrite it'); ok = False
    print('PASS og-card.png is the brand card' if ok else 'og-card.png: FAIL')
    return 0 if ok else 1
if __name__ == '__main__':
    sys.exit(main())
