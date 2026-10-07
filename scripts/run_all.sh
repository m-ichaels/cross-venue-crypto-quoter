#!/usr/bin/env bash
# Full pipeline after a recording: books -> lead-lag -> replay -> figures -> summary -> README -> tests.
# Usage: scripts/run_all.sh [--quick]      (--quick: base replay configuration only)
#   The recording itself:  python -m cvq.recorder --out data/raw --binance-bbo BTCUSDT --minutes 320
#   (and a second, lighter process is not needed: one process records all four streams).
set -euo pipefail
cd "$(dirname "$0")/.."
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-2}"
python scripts/build_books.py
python scripts/run_leadlag.py
python scripts/run_replay.py "$@"
python scripts/plots.py
python scripts/summarize.py
python scripts/readme.py
python -m pytest
echo done
