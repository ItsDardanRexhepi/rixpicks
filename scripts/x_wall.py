"""Shared X API billing/access wall detector (main 9:05 class fix: every X-calling
step skips-and-continues on the owner-side wall so chain verification is not
hostage to billing; anything else fails loud).

Wall = EVERY observed failure is a uniform owner-side access/billing denial:
402 (payment required / credits exhausted) or 403 (plan access denied).
401 (token), 429 (backoff), network errors, and mixed codes stay loud.
"""
import re

WALL_CODES = {'402', '403'}


def http_code(err):
    m = re.search(r'HTTP Error (\d+)', str(err))
    return m.group(1) if m else None


def is_wall(codes):
    return bool(codes) and set(codes) <= WALL_CODES


def wall_skip(step):
    print(f'X billing/access wall (uniform 402/403) at {step}: pull skipped, prior artifacts preserved; chain continues on frozen pool')
