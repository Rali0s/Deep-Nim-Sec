#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Build a unified 2-column CSV dataset (code_family, outfield) from mixed sources:
- NIST plaintext (TXT/CSV/PDF): extract control codes (e.g., AC-2(1).1) and first sentence.
- MITRE ATT&CK Excel (techniques sheet): build path and code (acronym or Technique ID) + concise text.
- SOC / ISMS / other plaintext (TXT/CSV/PDF): best-effort code token or surrogate + first sentence.

Design goals:
- Plaintext UTF-8 processing.
- Minimum rows enforced (default 1000).
- No JSON dependencies; optional CSV "family map" for filename/dir pattern → family label.
- Output schema: code_family,outfield (two columns only).

Usage (examples):
    python build_unified_two_column_dataset.py \
        --in_dir "/path/to/folder_with_files" \
        --out "/path/to/unified_two_col.csv"

    # Prefer MITRE Technique ID instead of acronym:
    python build_unified_two_column_dataset.py \
        --in_dir "/path/to/folder" --mitre_code techid --out "/path/to/out.csv"

    # Provide a CSV family map (pattern,family) to tag SOC/ISMS/others:
    python build_unified_two_column_dataset.py \
        --in_dir "/path/to/folder" --family_map "/path/to/family_map.csv" \
        --out "/path/to/out.csv"

family_map.csv format (no header assumptions needed; first row is header):
    pattern,family
    nist,NIST
    soc,SOC
    isms,ISMS
    mitre,ATTACK
The script uses first matching pattern (case-insensitive substring in the path).
"""

import argparse
import csv
import os
import re
import sys
from pathlib import Path
from typing import Iterable, List, Optional, Tuple, Dict

# Optional dependencies; script degrades gracefully if not installed
try:
    from pdfminer.high_level import extract_text as pdfminer_extract_text
except Exception:
    pdfminer_extract_text = None

try:
    import PyPDF2
except Exception:
    PyPDF2 = None

try:
    import pandas as pd
except Exception as e:
    print("ERROR: pandas is required (pip install pandas openpyxl).", file=sys.stderr)
    raise

# -------------------------
# Config / Patterns
# -------------------------

# NIST control families (for anchored matching)
NIST_FAMILIES = [
    "AC","AT","AU","CA","CM","CP","IA","IR","MA","MP","PE","PL","PM","PS","RA",
    "SA","SC","SI","SR"
]

# Regex that matches:
#   AC-1
#   RA-5.1
#   AC-2(1)
#   AC-2(12).1
NIST_CODE_RE = re.compile(
    rf'\b((?:{"|".join(NIST_FAMILIES)})-\d+(?:\.\d+)?(?:\(\d+\))?(?:\.\d+)?)\b'
)

# Heuristic “codey” token for SOC/ISMS/other lines if a NIST-like token not found:
# - One of: WORD (2-6 uppercase letters) optionally followed by -digits and decorations
GENERIC_CODE_RE = re.compile(r'\b([A-Z]{2,6}(?:[-\d().]{1,12})?)\b')

# Sentence end for “first sentence” extraction
SENT_END_RE = re.compile(r'[.?!:;]')

# -------------------------
# Helpers
# -------------------------

def read_text_from_txt_csv(path: Path) -> str:
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        return f.read()

def read_text_from_pdf(path: Path) -> str:
    # Try pdfminer first for better layout/text capture
    if pdfminer_extract_text is not None:
        try:
            return pdfminer_extract_text(str(path))
        except Exception:
            pass
    # Fallback to PyPDF2
    if PyPDF2 is not None:
        try:
            text_chunks = []
            with open(path, 'rb') as fh:
                reader = PyPDF2.PdfReader(fh)
                for page in reader.pages:
                    try:
                        text_chunks.append(page.extract_text() or "")
                    except Exception:
                        text_chunks.append("")
            return "\n".join(text_chunks)
        except Exception:
            pass
    # Last resort
    return ""

def iter_lines(text: str) -> Iterable[str]:
    for raw in text.splitlines():
        line = raw.strip()
        if line:
            yield line

def first_sentence(s: str) -> str:
    m = SENT_END_RE.search(s)
    return s[: m.end()].strip() if m else s.strip()

def acronym(s: str) -> str:
    # Split by any non-alphanumeric, take first char of each token
    parts = re.split(r"[^A-Za-z0-9]+", s.strip())
    return "".join([p[0].upper() for p in parts if p])

def best_family_from_map(path: Path, fam_map: List[Tuple[str,str]]) -> Optional[str]:
    low = str(path).lower()
    for patt, fam in fam_map:
        if patt and patt in low:
            return fam
    return None

def load_family_map_csv(path: Optional[str]) -> List[Tuple[str,str]]:
    """
    CSV with header: pattern,family
    Returns ordered list of (pattern_lower, family_str).
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

# -------------------------
# NIST parsing
# -------------------------

def parse_nist_plain_lines(lines: Iterable[str]) -> List[Tuple[str, str]]:
    """
    Return list of (code_family, outfield) from NIST-like plaintext.
    code_family: exact matched control code (e.g., 'AC-2(1).1')
    outfield: first sentence from the line containing the code
    """
    out = []
    for ln in lines:
        m = NIST_CODE_RE.search(ln)
        if not m:
            continue
        code = m.group(1)
        text = first_sentence(ln)
        out.append((code, text))
    return out

# -------------------------
# SOC/ISMS/other plaintext
# -------------------------

def parse_plain_generic(lines: Iterable[str], default_family: str) -> List[Tuple[str, str]]:
    """
    Find a 'codey' token if present (uppercase leading token), otherwise build surrogate code.
    We still emit first sentence as outfield.
    """
    out = []
    seq = 0
    for ln in lines:
        text = first_sentence(ln)
        # Prefer a clear code token at the start
        m = GENERIC_CODE_RE.search(ln)
        if m:
            code = m.group(1)
            # Avoid collisions with NIST exact codes; this is generic
            code_family = f"{default_family}:{code}"
        else:
            seq += 1
            code_family = f"{default_family}-{seq:06d}"
        out.append((code_family, text))
    return out

# -------------------------
# MITRE ATT&CK (Excel: techniques sheet)
# -------------------------

def read_mitre_techniques_from_excel(path: Path) -> Optional[pd.DataFrame]:
    try:
        df = pd.read_excel(path, sheet_name="techniques")
    except Exception:
        return None
    # Light normalization
    for col in ["ID", "name", "tactics", "is sub-technique", "sub-technique of", "description"]:
        if col in df.columns:
            df[col] = df[col].fillna("").astype(str).str.strip()
    return df

def expand_mitre_rows(df: pd.DataFrame) -> pd.DataFrame:
    """
    Split multi-tactic rows into multiple rows.
    """
    rows = []
    for _, r in df.iterrows():
        tactics_raw = r.get("tactics", "")
        tactics = [t.strip() for t in re.split(r"[,;/]", tactics_raw) if t.strip()] or [""]
        for t in tactics:
            rr = dict(r)
            rr["tactics"] = t
            rows.append(rr)
    return pd.DataFrame(rows)

def build_mitre_pairs(df: pd.DataFrame, code_mode: str = "acronym") -> List[Tuple[str, str]]:
    """
    Return (code_family, outfield) for each technique/subtechnique per tactic.
    code_mode:
        - 'acronym': use path acronym (e.g., 'RDAIM')
        - 'techid' : use 'ID' field (e.g., 'T1548.001')
    outfield: single text field (Path + first sentence of description if present)
    """
    if df is None or df.empty:
        return []

    df = expand_mitre_rows(df)

    # Partition
    is_sub = df.get("is sub-technique", "").str.lower().isin(["true","1","yes"])
    parents = df.loc[~is_sub].copy()
    children = df.loc[is_sub].copy()

    # Prepare quick lookup of parent by (tactic,name)
    pkey = parents.assign(_key=lambda d: d["tactics"].str.lower().str.strip() + "||" + d["name"].str.lower().str.strip())
    pkeys = set(pkey["_key"])

    out: List[Tuple[str, str]] = []

    def make_row(tactic: str, technique: str, subtech: Optional[str], desc: str, tech_id: str):
        path_parts = [p for p in [tactic, technique, subtech] if p]
        path = " > ".join(path_parts).strip()
        # Build code
        if code_mode == "techid" and tech_id:
            code = tech_id
        else:
            code = "".join(acronym(p) for p in path_parts) or (tech_id if tech_id else "ATTACK")
        # outfield = concise single field: Path + (optional first sentence of description)
        snippet = first_sentence(desc) if desc else ""
        outfield = path if not snippet else f"{path} — {snippet}"
        out.append((code, outfield))

    # Parents
    for _, r in parents.iterrows():
        tactic = r.get("tactics","")
        technique = r.get("name","")
        if not technique:
            continue
        make_row(tactic, technique, None, r.get("description",""), r.get("ID",""))

    # Children
    for _, r in children.iterrows():
        tactic = r.get("tactics","")
        sub = r.get("name","")
        parent = r.get("sub-technique of","")
        key = (tactic or "").strip().lower() + "||" + (parent or "").strip().lower()
        if not sub:
            continue
        # Even if parent not found under same tactic, still emit using given names
        make_row(tactic, parent or "(Unknown Parent)", sub, r.get("description",""), r.get("ID",""))

    # Deduplicate exact duplicates
    seen = set()
    uniq = []
    for k, v in out:
        if (k, v) in seen:
            continue
        seen.add((k, v))
        uniq.append((k, v))
    return uniq

# -------------------------
# Main aggregation
# -------------------------

def collect_records(
    in_dir: Path,
    family_map: List[Tuple[str,str]],
    mitre_code_mode: str
) -> List[Tuple[str, str]]:
    records: List[Tuple[str, str]] = []

    for path in sorted(in_dir.rglob("*")):
        if not path.is_file():
            continue

        suffix = path.suffix.lower()
        # MITRE Excel (look for techniques sheet)
        if suffix in [".xlsx", ".xlsm", ".xls"]:
            df = read_mitre_techniques_from_excel(path)
            if df is not None and "techniques" in [s.lower() for s in ["techniques"]]:
                mitre_pairs = build_mitre_pairs(df, code_mode=mitre_code_mode)
                if mitre_pairs:
                    records.extend(mitre_pairs)
                continue  # done with this file; do not treat as plaintext

        # Plaintext-ish sources
        text = ""
        if suffix in [".txt", ".csv", ".tsv", ".md"]:
            text = read_text_from_txt_csv(path)
        elif suffix in [".pdf"]:
            text = read_text_from_pdf(path)
        else:
            # Unsupported format; skip quietly
            continue

        if not text.strip():
            continue

        # Decide family via map (pattern → family), default fallback by file hint
        family_hint = best_family_from_map(path, family_map)
        if family_hint is None:
            # Heuristic: if filename looks nist-ish or soc/isms-ish
            low = path.name.lower()
            if "nist" in low:
                family_hint = "NIST"
            elif "soc" in low:
                family_hint = "SOC"
            elif "isms" in low:
                family_hint = "ISMS"
            else:
                family_hint = "PLAIN"

        lines = list(iter_lines(text))

        # If NIST family, try strict NIST code extraction first
        if family_hint.upper() == "NIST":
            pairs = parse_nist_plain_lines(lines)
            if not pairs:
                # fallback to generic parsing if nothing matched
                pairs = parse_plain_generic(lines, "NIST")
        else:
            # SOC/ISMS/Other
            pairs = parse_plain_generic(lines, family_hint.upper())

        records.extend(pairs)

    return records

def ensure_min_rows(records: List[Tuple[str, str]], min_rows: int) -> List[Tuple[str, str]]:
    if len(records) >= min_rows:
        return records
    if not records:
        return records
    # Deterministic oversampling: repeat from start until we reach min_rows
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
            # Enforce single-line outfield (plain CSV-friendly)
            one_line = " ".join(text.split())
            w.writerow([code, one_line])

def main():
    ap = argparse.ArgumentParser(description="Build a unified 2-col CSV (code_family,outfield) from mixed NIST/MITRE/SOC/ISMS sources.")
    ap.add_argument("--in_dir", required=True, help="Input directory to crawl for files (TXT, CSV, PDF, XLSX).")
    ap.add_argument("--out", required=True, help="Output CSV path for the unified two-column dataset.")
    ap.add_argument("--family_map", default=None, help="Optional CSV with columns: pattern,family (first match wins).")
    ap.add_argument("--mitre_code", default="acronym", choices=["acronym","techid"],
                    help="Code to use for MITRE rows: 'acronym' (e.g., RDAIM) or 'techid' (e.g., T1548.001). Default: acronym.")
    ap.add_argument("--min_rows", type=int, default=1000, help="Minimum rows to output (will oversample if necessary). Default: 1000.")
    args = ap.parse_args()

    in_dir = Path(args.in_dir)
    out_path = Path(args.out)

    if not in_dir.is_dir():
        print(f"ERROR: input directory not found: {in_dir}", file=sys.stderr)
        sys.exit(2)

    fam_map = load_family_map_csv(args.family_map)

    records = collect_records(in_dir, fam_map, args.mitre_code)
    # Deduplicate exact pairs
    dedup = list(dict.fromkeys(records))
    final_rows = ensure_min_rows(dedup, args.min_rows)
    write_two_column_csv(final_rows, out_path)
    print(f"✅ Wrote {len(final_rows)} rows to {out_path}")


if __name__ == "__main__":
    main()
