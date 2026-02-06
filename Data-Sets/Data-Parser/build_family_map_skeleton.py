#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Build a starter family_map CSV by scanning paths and suggesting families.
Output columns: pattern,family,example_path
- 'pattern' is a lowercase token (directory name or keyword) you can refine.
- 'family' is our guess (NIST/SOC/ISMS/ATTACK/PLAIN); you can edit it.
- 'example_path' shows where we found it.

Use:
  python3 build_family_map_skeleton.py \
    --in_dir "/path/to/RAW/Compliance" \
    --out "/path/to/family_map.csv"
"""

import argparse
import csv
import re
from pathlib import Path

HINTS = [
    ("nist", "NIST"),
    ("mitre", "ATTACK"),
    ("attack", "ATTACK"),
    ("soc", "SOC"),
    ("isms", "ISMS"),
    ("policy", "PLAIN"),
    ("standard", "PLAIN"),
    ("procedure", "PLAIN"),
]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in_dir", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    in_dir = Path(args.in_dir)
    seen_patterns = {}
    for p in sorted(in_dir.rglob("*")):
        if not p.is_file():
            continue
        low = str(p).lower()

        # propose patterns from directories and filename tokens
        candidates = set()

        # directory names as patterns
        for part in p.parts:
            tok = part.strip().lower()
            if len(tok) >= 3:
                candidates.add(tok)

        # keyword hints
        for kw, fam in HINTS:
            if kw in low:
                candidates.add(kw)

        for c in candidates:
            # assign a guess family from HINTS if any
            guess = None
            for kw, fam in HINTS:
                if kw == c:
                    guess = fam
                    break
            seen_patterns.setdefault(c, {"family": guess or "", "example": str(p)})

    # write CSV
    with open(args.out, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["pattern","family","example_path"])
        for patt, meta in sorted(seen_patterns.items()):
            w.writerow([patt, meta["family"], meta["example"]])

    print(f"✅ Wrote family map skeleton with {len(seen_patterns)} patterns to {args.out}")

if __name__ == "__main__":
    main()
