#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Unified two-column dataset builder (code_family, outfield) for mixed compliance sources.

Sources:
- NIST (TXT/CSV/PDF): extract control codes (e.g., AC-2(1).1) and the first sentence.
- MITRE ATT&CK (XLSX): read 'techniques' sheet and emit rows for
  Tactic > Technique (> Subtechnique), with code as either path acronym (default) or Technique ID.
- SOC / ISMS / other plaintext (TXT/CSV/PDF): best-effort 'codey' token or surrogate + first sentence.

Output:
- CSV with exactly two columns: code_family,outfield

CLI examples:
    python3 unified_dataset.py \
      --in_dir "/path/to/input" \
      --out "/path/to/out.csv"

    # Prefer official MITRE IDs instead of path acronyms:
    python3 unified_dataset.py \
      --in_dir "/path/to/input" \
      --out "/path/to/out.csv" \
      --mitre_code techid

    # Optional filename pattern → family CSV (pattern,family):
    python3 unified_dataset.py \
      --in_dir "/path/to/input" \
      --family_map "/path/to/family_map.csv" \
      --out "/path/to/out.csv"

Notes:
- No JSON is used; everything stays in CSV/plaintext.
- UTF-8 throughout; PDFs parsed best-effort (pdfminer if available, then PyPDF2).
"""

import argparse
import csv
import os
import re
import sys
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

# Optional libs: degrade gracefully if not installed
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
except Exception:
    print("ERROR: pandas is required. Install with: pip install pandas openpyxl", file=sys.stderr)
    raise

# -------------------------
# Config / Patterns
# -------------------------

# NIST control families
NIST_FAMILIES = [
    "AC","AT","AU","CA","CM","CP","IA","IR","MA","MP","PE","PL","PM","PS","RA",
    "SA","SC","SI","SR"
]

# NIST code regex: AC-1 | RA-5.1 | AC-2(1) | AC-2(12).1
NIST_CODE_RE = re.compile(
    rf'\b((?:{"|".join(NIST_FAMILIES)})-\d+(?:\.\d+)?(?:\(\d+\))?(?:\.\d+)?)\b'
)

# Generic "codey" token for SOC/ISMS/other
GENERIC_CODE_RE = re.compile(r'\b([A-Z]{2,6}(?:[-\d().]{1,12})?)\b')

# Sentence enders
SENT_END_RE = re.compile(r'[.?!:;]')

# -------------------------
# Helpers
# -------------------------

def read_text_from_txt_csv(path: Path) -> str:
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        return f.read()

def read_text_from_pdf(path: Path) -> str:
    # Prefer pdfminer for better extraction
    if pdfminer_extract_text is not None:
        try:
            return pdfminer_extract_text(str(path))
        except Exception:
            pass
    # Fallback to PyPDF2
    if PyPDF2 is not None:
        try:
            chunks = []
            with open(path, 'rb') as fh:
                reader = PyPDF2.PdfReader(fh)
                for page in reader.pages:
                    try:
                        chunks.append(page.extract_text() or "")
                    except Exception:
                        chunks.append("")
            return "\n".join(chunks)
        except Exception:
            pass
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
    parts = re.split(r"[^A-Za-z0-9]+", s.strip())
    return "".join([p[0].upper() for p in parts if p])

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

def best_family_from_map(path: Path, fam_map: List[Tuple[str,str]]) -> Optional[str]:
    low = str(path).lower()
    for patt, fam in fam_map:
        if patt in low:
            return fam
    return None

# -------------------------
# NIST parsing
# -------------------------

def parse_nist_plain_lines(lines: Iterable[str]) -> List[Tuple[str, str]]:
    """
    (code_family, outfield) for NIST-like plaintext lines.
    code_family: exact matched NIST control code (e.g., 'AC-2(1).1')
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
    Emit a 'codey' token if present; otherwise a sequential surrogate code.
    Always take the first sentence for outfield.
    """
    out = []
    seq = 0
    for ln in lines:
        text = first_sentence(ln)
        m = GENERIC_CODE_RE.search(ln)
        if m:
            code = m.group(1)
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
    """
    Open an Excel workbook and return the 'techniques' sheet (case-insensitive),
    or None if not present.
    """
    try:
        x = pd.ExcelFile(path)
    except Exception:
        return None

    sheet_map = {str(s).strip().lower(): s for s in x.sheet_names}
    if "techniques" not in sheet_map:
        return None

    df = x.parse(sheet_map["techniques"])
    # Leave general normalization to column getters
    return df

def _get_series(df: pd.DataFrame, col_name: str, default_value) -> pd.Series:
    """
    Return a Series for col_name if it exists (case-insensitive, stripped headers),
    else a Series filled with default_value (same length as df).
    """
    norm_map = {str(c).strip().lower(): c for c in df.columns}
    key = col_name.strip().lower()
    if key in norm_map:
        return df[norm_map[key]]
    # default series
    return pd.Series([default_value] * len(df), index=df.index)

def expand_mitre_rows(df: pd.DataFrame) -> pd.DataFrame:
    """
    Split rows by multi-tactic entries into one row per tactic.
    """
    name_ser   = _get_series(df, "name", "")
    tactics_ser= _get_series(df, "tactics", "")
    desc_ser   = _get_series(df, "description", "")
    id_ser     = _get_series(df, "ID", "")
    subflag    = _get_series(df, "is sub-technique", False)
    parent_ser = _get_series(df, "sub-technique of", "")

    # Normalize types robustly
    name_ser    = name_ser.astype(str).str.strip()
    tactics_ser = tactics_ser.astype(str).str.strip()
    desc_ser    = desc_ser.astype(str).str.strip()
    id_ser      = id_ser.astype(str).str.strip()
    parent_ser  = parent_ser.astype(str).str.strip()

    # Boolean-ish normalization
    subflag = (
        subflag.astype(str).str.strip().str.lower().isin(["true","1","yes","y","t"])
    )

    rows = []
    for i in df.index:
        tactics_raw = tactics_ser.loc[i] or ""
        # Split on common delimiters
        tactics = [t.strip() for t in re.split(r"[,;/]", tactics_raw) if t.strip()] or [""]
        for t in tactics:
            rows.append({
                "ID": id_ser.loc[i],
                "name": name_ser.loc[i],
                "tactics": t,
                "description": desc_ser.loc[i],
                "is_sub": bool(subflag.loc[i]),
                "parent_name": parent_ser.loc[i]
            })
    return pd.DataFrame(rows)

def build_mitre_pairs(df: pd.DataFrame, code_mode: str = "acronym") -> List[Tuple[str, str]]:
    """
    Return (code_family, outfield) for each technique/subtechnique per tactic.
    code_mode:
        - 'acronym': use path acronym (e.g., 'RDAIM')
        - 'techid' : use 'ID' field (e.g., 'T1548.001')
    outfield: Path + first sentence of description (if present)
    """
    if df is None or df.empty:
        return []

    df = expand_mitre_rows(df)

    parents = df[~df["is_sub"]].copy()
    children = df[df["is_sub"]].copy()

    out: List[Tuple[str, str]] = []

    def emit_row(tactic: str, technique: str, subtech: Optional[str], desc: str, tech_id: str):
        path_parts = [p for p in [tactic, technique, subtech] if p]
        path = " > ".join(path_parts).strip()

        if code_mode == "techid" and tech_id:
            code = tech_id
        else:
            code = "".join(acronym(p) for p in path_parts) or (tech_id if tech_id else "ATTACK")

        snippet = first_sentence(desc) if desc else ""
        outfield = path if not snippet else f"{path} — {snippet}"
        out.append((code, outfield))

    # Parents
    for _, r in parents.iterrows():
        tactic = r.get("tactics","")
        technique = r.get("name","")
        if not technique:
            continue
        emit_row(tactic, technique, None, r.get("description",""), r.get("ID",""))

    # Children
    for _, r in children.iterrows():
        tactic = r.get("tactics","")
        sub = r.get("name","")
        parent = r.get("parent_name","")
        if not sub:
            continue
        # Even if parent missing or tactic mismatch, still emit
        emit_row(tactic, parent or "(Unknown Parent)", sub, r.get("description",""), r.get("ID",""))

    # Deduplicate exact pairs
    uniq = list(dict.fromkeys(out))
    return uniq

# -------------------------
# Aggregation / IO
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

        # MITRE Excel (with 'techniques' sheet)
        if suffix in [".xlsx", ".xlsm", ".xls"]:
            df = read_mitre_techniques_from_excel(path)
            if df is not None:
                mitre_pairs = build_mitre_pairs(df, code_mode=mitre_code_mode)
                if mitre_pairs:
                    records.extend(mitre_pairs)
                # Skip treating Excel as plaintext
                continue

        # Plaintext-ish sources
        text = ""
        if suffix in [".txt", ".csv", ".tsv", ".md"]:
            text = read_text_from_txt_csv(path)
        elif suffix == ".pdf":
            text = read_text_from_pdf(path)
        else:
            continue  # unsupported type

        if not text.strip():
            continue

        # Family hint from map or filename
        family_hint = best_family_from_map(path, family_map)
        if family_hint is None:
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

        if family_hint.upper() == "NIST":
            pairs = parse_nist_plain_lines(lines)
            if not pairs:
                pairs = parse_plain_generic(lines, "NIST")
        else:
            pairs = parse_plain_generic(lines, family_hint.upper())

        records.extend(pairs)

    return records

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
    ap = argparse.ArgumentParser(description="Build unified 2-col CSV (code_family,outfield) from NIST/MITRE/SOC/ISMS sources.")
    ap.add_argument("--in_dir", required=True, help="Directory to crawl (PDF/XLSX/TXT/CSV).")
    ap.add_argument("--out", required=True, help="Output CSV path.")
    ap.add_argument("--family_map", default=None, help="Optional CSV mapping: pattern,family (first match wins).")
    ap.add_argument("--mitre_code", default="acronym", choices=["acronym","techid"],
                    help="MITRE code for rows: 'acronym' (RDAIM style) or 'techid' (T####). Default: acronym.")
    ap.add_argument("--min_rows", type=int, default=1000, help="Minimum rows in output (oversample if needed). Default: 1000.")
    args = ap.parse_args()

    in_dir = Path(args.in_dir)
    out_path = Path(args.out)

    if not in_dir.is_dir():
        print(f"ERROR: input directory not found: {in_dir}", file=sys.stderr)
        sys.exit(2)

    fam_map = load_family_map_csv(args.family_map)

    records = collect_records(in_dir, fam_map, args.mitre_code)
    # Deduplicate exact pairs (order-preserving)
    records = list(dict.fromkeys(records))

    final_rows = ensure_min_rows(records, args.min_rows)
    write_two_column_csv(final_rows, out_path)
    print(f"✅ Wrote {len(final_rows)} rows to {out_path}")

if __name__ == "__main__":
    main()
