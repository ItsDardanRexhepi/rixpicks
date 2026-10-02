#!/usr/bin/env python3
"""Fixture: paid X pulls are PAUSED unless the repo variable X_PAID_PULLS is explicitly set (owner, Oct 2: pulling
starts again only on his go). The x-feed workflow must default an unset variable to 'off'."""
import os, re, sys
p = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.github', 'workflows', 'x_feed.yml')
t = open(p).read()
m = re.search(r"X_PAID_PULLS:\s*\$\{\{\s*vars\.X_PAID_PULLS\s*\|\|\s*'off'\s*\}\}", t)
if not m:
    print("FAIL x_feed.yml must set X_PAID_PULLS: ${{ vars.X_PAID_PULLS || 'off' }} (paused by default)"); sys.exit(1)
print("X PAID PULLS DEFAULT FIXTURE: PASS (unset = off)")
