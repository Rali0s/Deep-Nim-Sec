#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Unified two-column dataset builder (code_family, outfield) with audit.

New in this version:
- Unicode normalization (smart hyphens → '-', quotes, NBSP, etc.).
- Parse by SENTENCE for NIST/SOC/ISMS (captures more hits than line-only).
- File-level AUDIT CSV summarizing coverage per file.
- Sample of UNPARSED sentences per file (cap with --max_unparsed_examples).

Output (main): code_family,outfield
Output (audit): file_path,file_type,family_hint,total_sentences,matched_sentences,match_rate,notes
"""

import argparse
import csv
import os
import re
import sys
import unicodedata
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

# Optional deps; degrade gracefully
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

NIST_FAMILIES = [
    "AC","AT","AU","CA","CM","CP","IA","IR","MA","MP","PE","PL","PM","PS","RA",
    "SA","SC","SI","SR"
]

# Accept ASCII hyphen and common Unicode hyphens
HYPH = r"[\-\u2010\u2011\u2012\u2013\u2014\u2212]"  # -, ‐, -, ‒, –, —, −
DIG  = r"\d+"

# NIST code regex (robust to unicode hyphens):
# AC-1 | RA-5.1 | AC-2(1) | AC-2(12).1
NIST_CODE_RE = re.compile(
    rf'\b((?:{"|".join(NIST_FAMILIES)}){HYPH}{DIG}(?:\.{DIG})?(?:\({DIG}\))?(?:\.{DIG})?)\b'
)

# Generic uppercase token for SOC/ISMS/other
GENERIC_CODE_RE = re.compile(r'\b([A-Z]{2,6}(?:[-\d().]{1,12})?)\b')

# Sentence boundary (greedy enough to capture bullets, colons, etc.)
SENT_SPLIT_RE = re.compile(r'(?<=[.?!:;])\s+')

# -------------------------
# Helpers
# -------------------------

def normalize_text(s: str) -> str:
    """Unicode NFKC normalization and common substitutions for parsing."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s)
    # Normalize fancy hyphens to ASCII hyphen
    s = re.sub(r"[\u2010\u2011\u2012\u2013\u2014\u2212]", "-", s)
    # Normalize non-breaking spaces
    s = s.replace("\u00A0", " ")
    # Collapse whitespace
    s = re.sub(r"\s+", " ", s)
    return s.strip()

def read_text_from_txt_csv(path: Path) -> str:
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        return f.read()

def read_text_from_pdf(path: Path) -> str:
    # Prefer pdfminer
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

def split_sentences(text: str) -> List[str]:
    text = normalize_text(text)
    if not text:
        return []
    # First try to split on standard sentence boundaries
    parts = SENT_SPLIT_RE.split(text)
    # Clean up and drop empties
    parts = [p.strip() for p in parts if p and p.strip()]
    return parts

def first_sentence(s: str) -> str:
    # We already split by sentences, but keep this guard:
    m = re.search(r'[.?!:;]', s)
    return s[: m.end()].strip() if m else s.strip()

def acronym(s: str) -> str:
    parts = re.split(r"[^A-Za-z0-9]+", s.strip())
    return "".join([p[0].upper() for p in parts if p])

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

def best_family_from_map(p: Path, fam_map: List[Tuple[str,str]]) -> Optional[str]:
    low = str(p).lower()
    for patt, fam in fam_map:
        if patt in low:
            return fam
    return None

# -------------------------
# NIST parsing (by sentences)
# -------------------------

def parse_nist_sentences(sentences: List[str]) -> List[Tuple[str, str]]:
    out = []
    for s in sentences:
        for m in NIST_CODE_RE.finditer(s):
            code = normalize_text(m.group(1))
            outfield = first_sentence(s)
            out.append((code, outfield))
    return out

# -------------------------
# SOC/ISMS/other parsing (by sentences)
# -------------------------

def parse_generic_sentences(sentences: List[str], default_family: str) -> List[Tuple[str, str]]:
    out = []
    seq = 0
    for s in sentences:
        s_norm = normalize_text(s)
        m = GENERIC_CODE_RE.search(s_norm)
        if m:
            code = m.group(1)
            code_family = f"{default_family}:{code}"
        else:
            seq += 1
            code_family = f"{default_family}-{seq:06d}"
        outfield = first_sentence(s_norm)
        out.append((code_family, outfield))
    return out

# -------------------------
# MITRE ATT&CK (Excel: techniques sheet)
# -------------------------

def read_mitre_techniques_from_excel(path: Path) -> Optional[pd.DataFrame]:
    try:
        x = pd.ExcelFile(path)
    except Exception:
        return None
    sheet_map = {str(s).strip().lower(): s for s in x.sheet_names}
    if "techniques" not in sheet_map:
        return None
    df = x.parse(sheet_map["techniques"])
    return df

def _get_series(df: pd.DataFrame, col_name: str, default_value) -> pd.Series:
    norm_map = {str(c).strip().lower(): c for c in df.columns}
    key = col_name.strip().lower()
    if key in norm_map:
        return df[norm_map[key]]
    return pd.Series([default_value] * len(df), index=df.index)

def expand_mitre_rows(df: pd.DataFrame) -> pd.DataFrame:
    name_ser   = _get_series(df, "name", "")
    tactics_ser= _get_series(df, "tactics", "")
    desc_ser   = _get_series(df, "description", "")
    id_ser     = _get_series(df, "ID", "")
    subflag    = _get_series(df, "is sub-technique", False)
    parent_ser = _get_series(df, "sub-technique of", "")

    # Normalize text
    name_ser    = name_ser.astype(str).map(normalize_text)
    tactics_ser = tactics_ser.astype(str).map(normalize_text)
    desc_ser    = desc_ser.astype(str).map(normalize_text)
    id_ser      = id_ser.astype(str).map(normalize_text)
    parent_ser  = parent_ser.astype(str).map(normalize_text)

    subflag = (
        subflag.astype(str).str.strip().str.lower().isin(["true","1","yes","y","t"])
    )

    rows = []
    for i in df.index:
        tactics_raw = tactics_ser.loc[i] or ""
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
    if df is None or df.empty:
        return []
    df = expand_mitre_rows(df)
    parents  = df[~df["is_sub"]].copy()
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

    for _, r in parents.iterrows():
        tactic = r.get("tactics","")
        technique = r.get("name","")
        if not technique:
            continue
        emit_row(tactic, technique, None, r.get("description",""), r.get("ID",""))

    for _, r in children.iterrows():
        tactic = r.get("tactics","")
        sub = r.get("name","")
        parent = r.get("parent_name","")
        if not sub:
            continue
        emit_row(tactic, parent or "(Unknown Parent)", sub, r.get("description",""), r.get("ID",""))

    uniq = list(dict.fromkeys(out))
    return uniq

# -------------------------
# Aggregation + Audit
# -------------------------

def collect_records_with_audit(
    in_dir: Path,
    family_map: List[Tuple[str,str]],
    mitre_code_mode: str,
    max_unparsed_examples: int
) -> Tuple[List[Tuple[str, str]], List[dict]]:
    """
    Returns: (records, audit_rows)
      records: [(code_family, outfield), ...]
      audit_rows: list of dicts for audit CSV
    """
    records: List[Tuple[str, str]] = []
    audit: List[dict] = []

    for path in sorted(in_dir.rglob("*")):
        if not path.is_file():
            continue

        suffix = path.suffix.lower()
        file_type = "other"
        notes = ""
        matched = 0
        total_sent = 0
        unparsed_samples = []

        # Excel → MITRE techniques
        if suffix in [".xlsx", ".xlsm", ".xls"]:
            df = read_mitre_techniques_from_excel(path)
            if df is not None:
                file_type = "excel-mitre"
                mitre_pairs = build_mitre_pairs(df, code_mode=mitre_code_mode)
                matched = len(mitre_pairs)
                total_sent = matched  # treat each pair as a 'unit'
                records.extend(mitre_pairs)
                audit.append({
                    "file_path": str(path),
                    "file_type": file_type,
                    "family_hint": "ATTACK",
                    "total_sentences": total_sent,
                    "matched_sentences": matched,
                    "match_rate": f"{(matched/total_sent*100 if total_sent else 0):.1f}%",
                    "notes": notes
                })
                continue  # done; don't treat as plaintext

        # TXT/CSV/PDF → plaintext sentences
        text = ""
        if suffix in [".txt", ".csv", ".tsv", ".md"]:
            file_type = "plaintext"
            text = read_text_from_txt_csv(path)
        elif suffix == ".pdf":
            file_type = "pdf"
            text = read_text_from_pdf(path)
        else:
            # unsupported
            continue

        text = normalize_text(text)
        sentences = split_sentences(text)
        total_sent = len(sentences)

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

        if family_hint.upper() == "NIST":
            pairs = parse_nist_sentences(sentences)
            # If nothing matched, fall back to generic
            if not pairs:
                pairs = parse_generic_sentences(sentences, "NIST")
        else:
            pairs = parse_generic_sentences(sentences, family_hint.upper())

        matched = len(pairs)
        # Sample a few unparsed sentences (no constraints here—just a glimpse)
        if max_unparsed_examples > 0 and total_sent > matched:
            want = max_unparsed_examples
            # Mark matched sentences for quick filter
            matched_outfields = set([p[1] for p in pairs])
            for s in sentences:
                if first_sentence(s) not in matched_outfields:
                    unparsed_samples.append(first_sentence(s))
                    if len(unparsed_samples) >= want:
                        break

        records.extend(pairs)
        audit.append({
            "file_path": str(path),
            "file_type": file_type,
            "family_hint": family_hint,
            "total_sentences": total_sent,
            "matched_sentences": matched,
            "match_rate": f"{(matched/total_sent*100 if total_sent else 0):.1f}%",
            "notes": " | ".join(unparsed_samples) if unparsed_samples else ""
        })

    return records, audit

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

def write_audit_csv(audit_rows: List[dict], out_path: Optional[Path]):
    if not out_path:
        return
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cols = ["file_path","file_type","family_hint","total_sentences","matched_sentences","match_rate","notes"]
    with open(out_path, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in audit_rows:
            w.writerow({c: r.get(c, "") for c in cols})

# -------------------------
# CLI
# -------------------------

def main():
    ap = argparse.ArgumentParser(description="Build unified 2-col CSV (code_family,outfield) with audit.")
    ap.add_argument("--in_dir", required=True, help="Directory to crawl (PDF/XLSX/TXT/CSV).")
    ap.add_argument("--out", required=True, help="Output CSV path.")
    ap.add_argument("--family_map", default=None, help="Optional CSV: pattern,family (first match wins).")
    ap.add_argument("--mitre_code", default="acronym", choices=["acronym","techid"],
                    help="MITRE code: 'acronym' (RDAIM-style) or 'techid' (T####). Default: acronym.")
    ap.add_argument("--min_rows", type=int, default=1000, help="Minimum rows (oversample if needed). Default: 1000.")
    ap.add_argument("--audit_csv", default=None, help="Optional audit CSV path with per-file coverage stats.")
    ap.add_argument("--max_unparsed_examples", type=int, default=3,
                    help="Number of example unparsed sentences to log per file in the audit. Default: 3.")
    args = ap.parse_args()

    in_dir = Path(args.in_dir)
    out_path = Path(args.out)
    audit_path = Path(args.audit_csv) if args.audit_csv else None

    if not in_dir.is_dir():
        print(f"ERROR: input directory not found: {in_dir}", file=sys.stderr)
        sys.exit(2)

    fam_map = load_family_map_csv(args.family_map)

    records, audit_rows = collect_records_with_audit(
        in_dir, fam_map, args.mitre_code, args.max_unparsed_examples
    )

    # Deduplicate exact pairs
    records = list(dict.fromkeys(records))

    final_rows = ensure_min_rows(records, args.min_rows)
    write_two_column_csv(final_rows, out_path)
    write_audit_csv(audit_rows, audit_path)

    print(f"✅ Wrote {len(final_rows)} rows to {out_path}")
    if audit_path:
        print(f"🧾 Audit written to {audit_path}")

if __name__ == "__main__":
    main()
