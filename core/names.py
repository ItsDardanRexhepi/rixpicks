"""Canonical player-name normalization: ONE normalizer across grader, binder,
and props producer. norm() lowercases and strips non-alphanumerics, so
hyphens, apostrophes, periods and spaces all fold onto the same key:
'Pete Crow-Armstrong' -> 'petecrowarmstrong' (fixes the hyphen-mismatch grader
miss), "De'Von Achane" -> 'devonachane', 'T.J. Watt Jr.' -> 'tjwattjr'."""
import re

def norm(name):
    """Shared player-name normalization: lowercase, strip non-alphanumerics."""
    return re.sub(r'[^a-z0-9]', '', (name or '').lower())
