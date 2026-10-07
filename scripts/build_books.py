#!/usr/bin/env python3
"""Rebuild the books from data/raw and write the hourly normalised tables to data/derived.

    python scripts/build_books.py [--raw data/raw] [--out data/derived] [--venues binance coinbase bitstamp binance_bbo]
                                  [--hours 2026-10-07T15 ...] [--report results/books.json]

Hour files are processed in time order per venue (the book state carries across hours; every hour file also starts
with a full-book reset so it can be read alone). A hour whose raw file is still being written is read up to the last
complete line and marked truncated in the report; rerun the script when the recording has finished.
"""
import argparse
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from cvq import books, raw  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", default=os.path.join(ROOT, "data", "raw"))
    ap.add_argument("--out", default=os.path.join(ROOT, "data", "derived"))
    ap.add_argument("--venues", nargs="*", default=list(books.VENUES) + list(books.BBO_VENUES))
    ap.add_argument("--hours", nargs="*", default=None, help="restrict to these hour keys (YYYY-MM-DDTHH)")
    ap.add_argument("--report", default=os.path.join(ROOT, "results", "books.json"))
    args = ap.parse_args(argv)
    t0 = time.time()
    reports = []
    for venue in args.venues:
        files = raw.hour_files(args.raw, venue)
        if args.hours:
            files = [f for f in files if raw.hour_key(f) in set(args.hours)]
        if not files:
            print(f"{venue}: no raw files under {args.raw}")
            continue
        reports += books.build_venue(args.raw, args.out, venue, files=files)
    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    with open(args.report, "w", encoding="utf-8") as f:
        json.dump({"built_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "seconds": round(time.time() - t0, 1),
                   "hours": reports}, f, indent=1)
    print(f"done in {time.time() - t0:.0f} s -> {args.report}")


if __name__ == "__main__":
    main()
