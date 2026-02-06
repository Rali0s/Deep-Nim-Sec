#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
txt_parser.py — Build a unified two-column dataset (code_family,outfield) from UTF-8 .txt files.

Features
- Cleans PDF artifacts (weird punctuation, NBSP, ligatures) and normalizes to UTF-8.
- Splits into sentences.
- Detects codes/families:
    • NIST controls (AC-1, RA-5.1, AC-2(1), AC-2(12).1, etc.)
    • ISO/IEC 27001/27002 (filename/content; uses generic 'ISO27001'/'ISO27002' codes)
    • SOC, ISMS, or fallback 'PLAIN' with a generic uppercase token or a surrogate code
- Optional CSV family map (pattern,family) — first match wins (case-insensitive substring).
- Verbose logging with per-file stats and sample output preview.
- Enforces a minimum row count (default 1000) via deterministic oversampling.

CLI Examples
    python3 txt_parser.py \
      --in_dir "/path/to/TXT" \
      --out "/path/to/out.csv" \
      --verbose --sample_output 5

    python3 txt_parser.py \
      --in_dir "/path/to/TXT" \
      --out "/path/to/out.csv" \
      --family_map "/path/to/family_map.csv" \
      --min_rows 5000 --verbose

      --family_map /path/to/family_map.csv --family_guess.
"""

import argparse
import csv
import os
import re
import sys
import unicodedata
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

# -------------------------
# Patterns & Config
# -------------------------

NIST_FAMILIES = [
    "AC","AT","AU","CA","CM","CP","IA","IR","MA","MP","PE","PL","PM","PS","RA",
    "SA","SC","SI","SR"
]

# Accept ASCII hyphen and common Unicode hyphens for NIST codes
HYPH = r"[\-\u2010\u2011\u2012\u2013\u2014\u2212]"  # -, ‐, -, ‒, –, —, −
DIG  = r"\d+"

# NIST code: AC-1 | RA-5.1 | AC-2(1) | AC-2(12).1
NIST_CODE_RE = re.compile(
    rf'\b((?:{"|".join(NIST_FAMILIES)}){HYPH}{DIG}(?:\.{DIG})?(?:\({DIG}\))?(?:\.{DIG})?)\b'
)

# Generic "codey" token (for SOC/ISMS/PLAIN fallback)
GENERIC_CODE_RE = re.compile(r'\b([A-Z]{2,6}(?:[-\d().]{1,12})?)\b')

# Sentence boundary split (keeps punctuation with the sentence)
SENT_SPLIT_RE = re.compile(r'(?<=[.?!:;])\s+')

# Recognize ISO family by filename/content hints
ISO_NAME_RE = re.compile(r'\bISO/IEC\s*27(?:001|002)\b', re.IGNORECASE)
ISO_FILE_RE = re.compile(r'(iso|iso_iec|27001|27002)', re.IGNORECASE)

# -------------------------
# Utilities
# -------------------------

def log(msg: str, enabled: bool):
    if enabled:
        print(msg, flush=True)

def normalize_text(s: str) -> str:
    """Unicode normalize + clean common PDF artifacts."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s)
    # ligatures
    s = s.replace("ﬂ", "fl").replace("ﬁ", "fi")
    # fancy hyphens → '-'
    s = re.sub(r"[\u2010\u2011\u2012\u2013\u2014\u2212]", "-", s)
    # NBSP → space
    s = s.replace("\u00A0", " ")
    # collapse punctuation clusters like ",,,-`-`,,`"
    s = re.sub(r"[,\-`]{2,}", " ", s)
    # strip control chars
    s = re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", s)
    # collapse whitespace
    s = re.sub(r"\s+", " ", s)
    return s.strip()

def read_text(path: Path) -> str:
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()

def split_sentences(text: str) -> List[str]:
    text = text.strip()
    if not text:
        return []
    parts = SENT_SPLIT_RE.split(text)
    # Clean & drop empties
    return [p.strip() for p in parts if p and p.strip()]

def first_sentence(s: str) -> str:
    m = re.search(r'[.?!:;]', s)
    return s[: m.end()].strip() if m else s.strip()

def load_family_map_csv(path: Optional[str]) -> List[Tuple[str, str]]:
    """
    CSV header: pattern,family
    Returns ordered list of (pattern_lower, family) for first-match wins.
    """
    if not path:
        return []
    rows = []
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        rdr = csv.DictReader(f)
        for r in rdr:
            patt = (r.get('pattern') or '').strip().lower()
            fam = (r.get('family') or '').strip()
            if patt and fam:
                rows.append((patt, fam))
    return rows

def guess_family_from_filename(path: Path) -> Optional[str]:
    name = path.name
    if ISO_FILE_RE.search(name):
        # Choose a simple code per doc type; refine if needed
        if "27001" in name:
            return "ISO27001"
        if "27002" in name:
            return "ISO27002"
        return "ISO"
    low = name.lower()
    if "nist" in low:
        return "NIST"
    if "soc" in low:
        return "SOC"
    if "isms" in low:
        return "ISMS"
    return None

def best_family(path: Path, family_map: List[Tuple[str,str]], family_guess: bool, text_hint: Optional[str]) -> str:
    # family_map first
    low = str(path).lower()
    for patt, fam in family_map:
        if patt in low:
            return fam
    # filename guess
    if family_guess:
        fam = guess_family_from_filename(path)
        if fam:
            return fam
    # content hint for ISO
    if text_hint and ISO_NAME_RE.search(text_hint):
        return "ISO27001" if "27001" in text_hint else "ISO"
    return "PLAIN"

# -------------------------
# Per-family sentence parsing
# -------------------------

def parse_nist_sentence(s: str) -> List[Tuple[str, str]]:
    """Return list of (code_family, outfield) for a sentence with 0..n NIST codes."""
    out = []
    for m in NIST_CODE_RE.finditer(s):
        code = m.group(1)
        outfield = first_sentence(s)
        out.append((code, outfield))
    return out

def parse_iso_sentence(s: str) -> List[Tuple[str, str]]:
    """
    ISO sentences usually don't have machine-parseable codes like NIST.
    We emit a stable family code (ISO27001/ISO27002/ISO) + the sentence.
    (You can later refine with clause parsing if you add an ISO regex.)
    """
    fam = "ISO27001" if "27001" in s else ("ISO27002" if "27002" in s else "ISO")
    return [(fam, first_sentence(s))]

def parse_generic_sentence(s: str, family_hint: str) -> List[Tuple[str, str]]:
    """
    SOC/ISMS/PLAIN fallback:
    Use a generic uppercase token if present, else create surrogate sequence later.
    Here we just try to capture a token; if none, we still emit with a placeholder family.
    """
    outfield = first_sentence(s)
    m = GENERIC_CODE_RE.search(s)
    if m:
        code = f"{family_hint}:{m.group(1)}"
    else:
        code = f"{family_hint}"  # will remain as-is (no sequence here)
    return [(code, outfield)]

# -------------------------
# Main file processing
# -------------------------

def process_txt_file(path: Path, family_map: List[Tuple[str,str]], family_guess: bool, verbose: bool, sample_output: int) -> List[Tuple[str, str]]:
    raw = read_text(path)
    cleaned = normalize_text(raw)
    if not cleaned:
        return []

    # Best-effort family
    fam = best_family(path, family_map, family_guess, text_hint=cleaned[:2000])  # peek start of doc
    sentences = split_sentences(cleaned)

    rows: List[Tuple[str, str]] = []
    for s in sentences:
        if fam.upper() == "NIST":
            found = parse_nist_sentence(s)
            if found:
                rows.extend(found)
            else:
                # fallback generic row to keep coverage (optional)
                rows.extend(parse_generic_sentence(s, "NIST"))
        elif fam.upper().startswith("ISO"):
            rows.extend(parse_iso_sentence(s))
        elif fam.upper() in ("SOC", "ISMS"):
            rows.extend(parse_generic_sentence(s, fam.upper()))
        else:
            rows.extend(parse_generic_sentence(s, "PLAIN"))

    # Dedup identical pairs from the same file
    rows = list(dict.fromkeys(rows))

    if verbose:
        print(f"[TXT] {path.name} | fam={fam} | sentences={len(sentences)} | rows={len(rows)}")
        if sample_output > 0:
            for i, (c, t) in enumerate(rows[:sample_output], 1):
                print(f"  [{i}] {c} -> {t[:120]}{'...' if len(t)>120 else ''}")

    return rows

# -------------------------
# Final assembly
# -------------------------

def ensure_min_rows(records: List[Tuple[str, str]], min_rows: int) -> List[Tuple[str, str]]:
    if len(records) >= min_rows:
        return records
    if not records:
        return records
    out = list(records)
    idx = 0
    while len(out) < min_rows:
        out.append(records[idx % len(records)])
        idx += 1
    return out

def write_two_column_csv(records: List[Tuple[str,str]], out_path: Path):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(["code_family", "outfield"])
        for code, text in records:
            one_line = " ".join((text or "").split())
            w.writerow([code, one_line])

# -------------------------
# CLI
# -------------------------

def main():
    ap = argparse.ArgumentParser(description="Parse normalized UTF-8 .txt files into a two-column dataset (code_family,outfield).")
    ap.add_argument("--in_dir", required=True, help="Directory containing .txt files (recursively).")
    ap.add_argument("--out", required=True, help="Output CSV path.")
    ap.add_argument("--family_map", default=None, help="Optional CSV (pattern,family) first-match wins.")
    ap.add_argument("--family_guess", action="store_true", help="Enable filename/content-based family guessing.")
    ap.add_argument("--verbose", action="store_true", help="Print per-file stats and progress.")
    ap.add_argument("--sample_output", type=int, default=0, help="Print N sample rows per file (for debugging).")
    ap.add_argument("--min_rows", type=int, default=1000, help="Minimum rows to output (oversample deterministically).")
    args = ap.parse_args()

    in_dir = Path(args.in_dir)
    out_path = Path(args.out)
    if not in_dir.is_dir():
        print(f"ERROR: in_dir not found: {in_dir}", file=sys.stderr)
        sys.exit(2)

    fam_map = load_family_map_csv(args.family_map)

    all_records: List[Tuple[str, str]] = []
    txt_files = sorted(in_dir.rglob("*.txt"))
    if args.verbose:
        print(f"Found {len(txt_files)} .txt files under {in_dir}")

    for p in txt_files:
        recs = process_txt_file(p, fam_map, args.family_guess, args.verbose, args.sample_output)
        all_records.extend(recs)

    # Deduplicate globally
    all_records = list(dict.fromkeys(all_records))
    all_records = ensure_min_rows(all_records, args.min_rows)
    write_two_column_csv(all_records, out_path)

    print(f"✅ Wrote {len(all_records)} rows to {out_path}")

if __name__ == "__main__":
    main()
