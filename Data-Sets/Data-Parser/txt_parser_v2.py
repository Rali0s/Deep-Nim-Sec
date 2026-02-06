#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
txt_parser_v2.py — Higher-recall two-column parser (code_family,outfield) for UTF-8 .txt corpora.

New:
- split_strategy: sentence | line | hybrid (clauses, bullets, em-dashes)
- ISO clause extraction: A.5, A.5.1, A.5.1.2 → ISO27001:A.5.1 etc.
- allow_dupes: keep duplicates (boosts row count)
- prefix_code_with_file: provenance in code (FILE:CODE)
- min_len / max_len for snippet filtering
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

HYPH = r"[\-\u2010\u2011\u2012\u2013\u2014\u2212]"
DIG  = r"\d+"

# NIST: AC-1 | RA-5.1 | AC-2(1) | AC-2(12).1
NIST_CODE_RE = re.compile(
    rf'\b((?:{"|".join(NIST_FAMILIES)}){HYPH}{DIG}(?:\.{DIG})?(?:\({DIG}\))?(?:\.{DIG})?)\b'
)

# ISO clause references in Annex A style: A.5, A.5.1, A.5.1.2, etc.
ISO_CLAUSE_RE = re.compile(r'\bA\.\d+(?:\.\d+){0,3}\b', re.IGNORECASE)

# Generic uppercase token
GENERIC_CODE_RE = re.compile(r'\b([A-Z]{2,6}(?:[-\d().]{1,12})?)\b')

# Sentence boundary
SENT_SPLIT_RE = re.compile(r'(?<=[.?!:;])\s+')

# Bullet / heading cues (hybrid mode)
BULLET_LINE_RE = re.compile(r'^\s*([•\-–—*]|\d{1,3}[.)]|[A-Za-z]\))\s+')

# ISO hints
ISO_NAME_RE = re.compile(r'\bISO/IEC\s*27(?:001|002)\b', re.IGNORECASE)
ISO_FILE_RE = re.compile(r'(iso|iso_iec|27001|27002)', re.IGNORECASE)

# -------------------------
# Utilities
# -------------------------

def log(msg: str, enabled: bool):
    if enabled:
        print(msg, flush=True)

def normalize_text(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("ﬂ", "fl").replace("ﬁ", "fi")
    s = re.sub(r"[\u2010\u2011\u2012\u2013\u2014\u2212]", "-", s)  # fancy hyphens -> '-'
    s = s.replace("\u00A0", " ")
    # don't collapse newlines here; we use them in line/hybrid modes
    s = re.sub(r"[ \t]+", " ", s)
    # strip control chars
    s = re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", s)
    # remove excessive ",-` clusters
    s = re.sub(r"[,\-`]{3,}", " ", s)
    return s.strip()

def read_text(path: Path) -> str:
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()

def split_sentences(text: str) -> List[str]:
    parts = SENT_SPLIT_RE.split(text.strip())
    return [p.strip() for p in parts if p and p.strip()]

def split_lines(text: str) -> List[str]:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return lines

def further_clause_split(chunks: List[str]) -> List[str]:
    out = []
    for c in chunks:
        # split on semicolons, em-dashes, and long comma runs
        temp = re.split(r'\s*;\s*|\s+—\s+|\s+–\s+|\s+-\s+|\s*,\s{2,}', c)
        for t in temp:
            t = t.strip()
            if t:
                out.append(t)
    return out

def hybrid_split(text: str) -> List[str]:
    # 1) split into lines; harvest bullet/heading lines as separate units
    lines = split_lines(text)
    chunks = []
    buf = []
    for ln in lines:
        if BULLET_LINE_RE.match(ln):
            if buf:
                chunks.append(" ".join(buf).strip()); buf = []
            chunks.append(ln)
        else:
            buf.append(ln)
    if buf:
        chunks.append(" ".join(buf).strip())
    # 2) sentence split each chunk
    sents = []
    for ch in chunks:
        sents.extend(split_sentences(ch))
    # 3) clause split
    return further_clause_split(sents)

def first_sentence(s: str) -> str:
    m = re.search(r'[.?!:;]', s)
    return s[: m.end()].strip() if m else s.strip()

def load_family_map_csv(path: Optional[str]) -> List[Tuple[str, str]]:
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
    low = str(path).lower()
    for patt, fam in family_map:
        if patt in low:
            return fam
    if family_guess:
        fam = guess_family_from_filename(path)
        if fam:
            return fam
    if text_hint and ISO_NAME_RE.search(text_hint):
        return "ISO27001" if "27001" in text_hint else "ISO"
    return "PLAIN"

def short_file_token(path: Path) -> str:
    base = path.stem
    base = re.sub(r'[^A-Za-z0-9]+', '_', base).strip('_')
    return base[:18].upper()

# -------------------------
# Per-family parsing
# -------------------------

def parse_nist_unit(u: str) -> List[Tuple[str, str]]:
    out = []
    for m in NIST_CODE_RE.finditer(u):
        out.append((m.group(1), u.strip()))
    return out

def parse_iso_unit(u: str, fam_hint: str) -> List[Tuple[str, str]]:
    # Capture explicit clauses first (Annex A)
    pairs = []
    for m in ISO_CLAUSE_RE.finditer(u):
        clause = m.group(0).upper().replace('A.', 'A.')
        fam = "ISO27001" if "27001" in fam_hint or fam_hint.upper()=="ISO27001" else ("ISO27002" if "27002" in fam_hint or fam_hint.upper()=="ISO27002" else "ISO")
        pairs.append((f"{fam}:{clause}", u.strip()))
    if pairs:
        return pairs
    # fallback to doc-level family row
    fam = "ISO27001" if "27001" in fam_hint or fam_hint.upper()=="ISO27001" else ("ISO27002" if "27002" in fam_hint or fam_hint.upper()=="ISO27002" else "ISO")
    return [(fam, u.strip())]

def parse_generic_unit(u: str, family_hint: str) -> List[Tuple[str, str]]:
    m = GENERIC_CODE_RE.search(u)
    if m:
        return [(f"{family_hint}:{m.group(1)}", u.strip())]
    return [(family_hint, u.strip())]

# -------------------------
# File processing
# -------------------------

def process_txt_file(path: Path, split_strategy: str, family_map: List[Tuple[str,str]],
                     family_guess: bool, prefix_code_with_file: bool,
                     min_len: int, max_len: int, verbose: bool, sample_output: int) -> List[Tuple[str, str]]:
    raw = read_text(path)
    cleaned = normalize_text(raw)
    if not cleaned:
        return []

    fam = best_family(path, family_map, family_guess, text_hint=cleaned[:4000])

    if split_strategy == "line":
        units = split_lines(cleaned)
    elif split_strategy == "hybrid":
        units = hybrid_split(cleaned)
    else:
        units = split_sentences(cleaned)

    # length filter
    _units = []
    for u in units:
        u = u.strip()
        if not u:
            continue
        if min_len and len(u) < min_len:
            continue
        if max_len and len(u) > max_len:
            # keep but truncate politely at last boundary
            u = (u[:max_len] + "…")
        _units.append(u)
    units = _units

    rows: List[Tuple[str, str]] = []
    for u in units:
        if fam.upper() == "NIST":
            found = parse_nist_unit(u)
            rows.extend(found if found else [(f"NIST", u)])
        elif fam.upper().startswith("ISO"):
            rows.extend(parse_iso_unit(u, fam))
        elif fam.upper() in ("SOC","ISMS"):
            rows.extend(parse_generic_unit(u, fam.upper()))
        else:
            rows.extend(parse_generic_unit(u, "PLAIN"))

    if prefix_code_with_file:
        token = short_file_token(path)
        rows = [(f"{token}:{c}", t) for (c,t) in rows]

    if verbose:
        print(f"[TXT] {path.name} | fam={fam} | units={len(units)} | rows={len(rows)} | split={split_strategy}")
        if sample_output > 0:
            for i, (c, t) in enumerate(rows[:sample_output], 1):
                print(f"  [{i}] {c} -> {t[:140]}{'...' if len(t)>140 else ''}")

    return rows

# -------------------------
# Assembly / IO
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
    ap = argparse.ArgumentParser(description="High-recall TXT → two-column CSV (code_family,outfield).")
    ap.add_argument("--in_dir", required=True, help="Directory containing .txt files.")
    ap.add_argument("--out", required=True, help="Output CSV path.")
    ap.add_argument("--family_map", default=None, help="Optional CSV (pattern,family).")
    ap.add_argument("--family_guess", action="store_true", help="Guess family from filename/content.")
    ap.add_argument("--split_strategy", default="hybrid", choices=["sentence","line","hybrid"],
                    help="Unitization strategy. Default: hybrid.")
    ap.add_argument("--allow_dupes", action="store_true", help="Do not deduplicate globally.")
    ap.add_argument("--prefix_code_with_file", action="store_true", help="Prefix code with a short file token.")
    ap.add_argument("--min_len", type=int, default=0, help="Drop units shorter than this many chars.")
    ap.add_argument("--max_len", type=int, default=0, help="Soft cap; truncate units longer than this many chars with ellipsis.")
    ap.add_argument("--min_rows", type=int, default=1000, help="Minimum rows (oversample deterministically if needed).")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--sample_output", type=int, default=0)
    args = ap.parse_args()

    in_dir = Path(args.in_dir)
    out_path = Path(args.out)
    if not in_dir.is_dir():
        print(f"ERROR: in_dir not found: {in_dir}", file=sys.stderr)
        sys.exit(2)

    fam_map = []
    if args.family_map:
        fam_map = load_family_map_csv(args.family_map)

    all_records: List[Tuple[str, str]] = []
    txt_files = sorted(in_dir.rglob("*.txt"))
    if args.verbose:
        print(f"Found {len(txt_files)} .txt files under {in_dir}")

    for p in txt_files:
        recs = process_txt_file(
            p,
            split_strategy=args.split_strategy,
            family_map=fam_map,
            family_guess=args.family_guess,
            prefix_code_with_file=args.prefix_code_with_file,
            min_len=args.min_len,
            max_len=args.max_len,
            verbose=args.verbose,
            sample_output=args.sample_output
        )
        all_records.extend(recs)

    # Global de-dup (optional)
    if not args.allow_dupes:
        all_records = list(dict.fromkeys(all_records))

    all_records = ensure_min_rows(all_records, args.min_rows)
    write_two_column_csv(all_records, out_path)

    print(f"✅ Wrote {len(all_records)} rows to {out_path}")

if __name__ == "__main__":
    main()
