#!/usr/bin/env python3
"""Run the published-site checks included in the repository's fixture suite."""
from pathlib import Path
import runpy

if __name__ == '__main__':
    runpy.run_path(str(Path(__file__).resolve().parents[1] / '.github/pages-release/test_build.py'), run_name='__main__')
