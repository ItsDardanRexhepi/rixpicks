#!/bin/bash
# The standing fixture runner discovers this wrapper automatically.
set -eu
cd "$(dirname "$0")/.."
node tests/dingers_home_regression.cjs
