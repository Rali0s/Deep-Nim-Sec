#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
txt_excel_parser.py — High-recall two-column dataset builder from TXT + Excel.

Outputs:
  1) Two-column CSV: code_family,outfield
  2) Optional Family Map CSV: per file/sheet stats

Features:
- Parses UTF-8 .txt files with hybrid/sentence/line strategies (same as txt_parser_v3).
- Parses Excel (.xlsx/.xlsm/.xls):
    • Auto-detects MITRE ATT&CK 'techniques' sheet → emits path-acronym or Technique ID (--mitre_code).
    • For all other sheets: flattens cells to text and runs the same parser as TXT.
- Family detection via filename/content and optional CSV (pattern,family).
- ISO clause extraction (A.5, A.5.1, A.5.1.2).
- NIST control code extraction.
- Options for duplicates, provenance prefix, min/max unit length, sampling, verbose logs.

Install:
  pip install pandas openpyxl xlrd pdfminer.six pdfplumber pymupdf pypdfium2
"""

import argparse
import csv
import os
import re
import sys
import unicodedata
from pathlib import Path
from typing import Iterable, List, Optional, Tuple, Dict

# ---------- Optional pandas ----------
try:
    import pandas as pd
except Exception:
    print("ERROR: pandas is required. Install with: pip install pandas openpyxl xlrd", file=sys.stderr)
    raise

# ---------- Patterns & Config ----------
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

# ISO Annex A: A.5, A.5.1, A.5.1.2...
ISO_CLAUSE_RE = re.compile(r'\bA\.\d+(?:\.\d+){0,3}\b', re.IGNORECASE)

# Generic uppercase token
GENERIC_CODE_RE = re.compile(r'\b([A-Z]{2,6}(?:[-\d().]{1,12})?)\b')

# Sentence boundary
SENT_SPLIT_RE = re.compile(r'(?<=[.?!:;])\s+')

# Bullets / headings for hybrid split
BULLET_LINE_RE = re.compile(r'^\s*([•\-–—*]|\d{1,3}[.)]|[A-Za-z]\))\s+')

# ISO hints
ISO_NAME_RE = re.compile(r'\bISO/IEC\s*27(?:001|002)\b', re.IGNORECASE)
ISO_FILE_RE = re.compile(r'(iso|iso_iec|27001|27002)', re.IGNORECASE)

# ---------- Utils ----------
def log(msg: str, enabled: bool):
    if enabled:
        print(msg, flush=True)

def normalize_text(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("ﬂ", "fl").replace("ﬁ", "fi")
    s = re.sub(r"[\u2010\u2011\u2012\u2013\u2014\u2212]", "-", s)  # fancy hyphens → '-'
    s = s.replace("\u00A0", " ")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", s)      # strip control chars
    s = re.sub(r"[,\-`]{3,}", " ", s)               # collapse punctuation noise
    return s.strip()

def read_text(path: Path) -> str:
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()

def split_sentences(text: str) -> List[str]:
    parts = SENT_SPLIT_RE.split(text.strip())
    return [p.strip() for p in parts if p and p.strip()]

def split_lines(text: str) -> List[str]:
    return [ln.strip() for ln in text.splitlines() if ln.strip()]

def further_clause_split(chunks: List[str]) -> List[str]:
    out = []
    for c in chunks:
        temp = re.split(r'\s*;\s*|\s+—\s+|\s+–\s+|\s+-\s+|\s*,\s{2,}', c)
        for t in temp:
            t = t.strip()
            if t:
                out.append(t)
    return out

def hybrid_split(text: str) -> List[str]:
    lines = split_lines(text)
    chunks, buf = [], []
    for ln in lines:
        if BULLET_LINE_RE.match(ln):
            if buf:
                chunks.append(" ".join(buf).strip()); buf = []
            chunks.append(ln)
        else:
            buf.append(ln)
    if buf:
        chunks.append(" ".join(buf).strip())
    sents = []
    for ch in chunks:
        sents.extend(split_sentences(ch))
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
    if "mitre" in low or "attack" in low:
        return "ATTACK"
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
    return base[:24].upper()

# ---------- Per-family parsing ----------
def parse_nist_unit(u: str) -> List[Tuple[str, str]]:
    out = []
    for m in NIST_CODE_RE.finditer(u):
        out.append((m.group(1), u.strip()))
    return out

def parse_iso_unit(u: str, fam_hint: str) -> List[Tuple[str, str]]:
    pairs = []
    for m in ISO_CLAUSE_RE.finditer(u):
        clause = m.group(0).upper()
        fam = "ISO27001" if ("27001" in fam_hint or fam_hint.upper()=="ISO27001") \
              else ("ISO27002" if ("27002" in fam_hint or fam_hint.upper()=="ISO27002") else "ISO")
        pairs.append((f"{fam}:{clause}", u.strip()))
    if pairs:
        return pairs
    fam = "ISO27001" if ("27001" in fam_hint or fam_hint.upper()=="ISO27001") \
          else ("ISO27002" if ("27002" in fam_hint or fam_hint.upper()=="ISO27002") else "ISO")
    return [(fam, u.strip())]

def parse_generic_unit(u: str, family_hint: str) -> List[Tuple[str, str]]:
    m = GENERIC_CODE_RE.search(u)
    if m:
        return [(f"{family_hint}:{m.group(1)}", u.strip())]
    return [(family_hint, u.strip())]

# ---------- MITRE (Excel techniques) ----------
def excel_open(path: Path) -> Optional[pd.ExcelFile]:
    try:
        return pd.ExcelFile(path)
    except Exception:
        return None

def read_mitre_techniques_df(xl: pd.ExcelFile) -> Optional[pd.DataFrame]:
    sheet_map = {str(s).strip().lower(): s for s in xl.sheet_names}
    if "techniques" not in sheet_map:
        return None
    try:
        df = xl.parse(sheet_map["techniques"])
    except Exception:
        return None
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

    # Normalize
    name_ser    = name_ser.astype(str).map(normalize_text)
    tactics_ser = tactics_ser.astype(str).map(normalize_text)
    desc_ser    = desc_ser.astype(str).map(normalize_text)
    id_ser      = id_ser.astype(str).map(normalize_text)
    parent_ser  = parent_ser.astype(str).map(normalize_text)
    subflag     = subflag.astype(str).str.strip().str.lower().isin(["true","1","yes","y","t"])

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

def mitre_pairs_from_df(df: pd.DataFrame, code_mode: str = "acronym") -> List[Tuple[str, str]]:
    if df is None or df.empty:
        return []
    dfe = expand_mitre_rows(df)
    parents  = dfe[~dfe["is_sub"]].copy()
    children = dfe[dfe["is_sub"]].copy()
    out: List[Tuple[str, str]] = []

    def acronym(s: str) -> str:
        parts = re.split(r"[^A-Za-z0-9]+", s.strip())
        return "".join([p[0].upper() for p in parts if p])

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

    return list(dict.fromkeys(out))

# ---------- Excel (generic sheet → text) ----------
def flatten_sheet_to_text(df: pd.DataFrame, max_rows: int = 0, max_cols: int = 0, sep: str = " | ") -> str:
    """
    Convert a DataFrame to a loose text block, row-by-row.
    Limits can be set with max_rows/max_cols (0 = no limit).
    """
    if df is None or df.empty:
        return ""
    if max_rows > 0:
        df = df.head(max_rows)
    if max_cols > 0:
        df = df.iloc[:, :max_cols]

    # Convert all to strings and normalize
    df2 = df.fillna("").astype(str).applymap(lambda x: normalize_text(x))
    lines = []
    # include header row (if not all blank)
    header = sep.join(list(df2.columns))
    if header.strip():
        lines.append(header)
    for _, row in df2.iterrows():
        line = sep.join(list(row.values))
        if line.strip():
            lines.append(line)
    return "\n".join(lines)

# ---------- TXT processing ----------
def process_txt_file(
    path: Path,
    split_strategy: str,
    family_map: List[Tuple[str,str]],
    family_guess: bool,
    prefix_code_with_file: bool,
    min_len: int,
    max_len: int,
    verbose: bool,
    sample_output: int
) -> Tuple[List[Tuple[str, str]], dict]:
    raw = read_text(path)
    cleaned = normalize_text(raw)
    if not cleaned:
        return [], {
            "file_token": short_file_token(path),
            "file_name": path.name,
            "sheet": "",
            "family": "EMPTY",
            "split_strategy": split_strategy,
            "units": 0,
            "rows": 0,
            "unique_codes": 0,
            "example_codes": "",
            "path": str(path),
        }

    fam = best_family(path, family_map, family_guess, text_hint=cleaned[:4000])

    if split_strategy == "line":
        units = split_lines(cleaned)
    elif split_strategy == "hybrid":
        units = hybrid_split(cleaned)
    else:
        units = split_sentences(cleaned)

    # length filter
    filt_units = []
    for u in units:
        u = u.strip()
        if not u:
            continue
        if min_len and len(u) < min_len:
            continue
        if max_len and len(u) > max_len:
            u = (u[:max_len] + "…")
        filt_units.append(u)
    units = filt_units

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

    # stats
    file_token = short_file_token(path)
    seen_codes, examples = set(), []
    for c, _ in rows:
        if c not in seen_codes:
            seen_codes.add(c)
            examples.append(c)
        if len(examples) >= 8:
            break
    stats = {
        "file_token": file_token,
        "file_name": path.name,
        "sheet": "",
        "family": fam,
        "split_strategy": split_strategy,
        "units": len(units),
        "rows": len(rows),
        "unique_codes": len(seen_codes),
        "example_codes": "; ".join(examples),
        "path": str(path),
    }

    if verbose:
        print(f"[TXT] {path.name} | fam={fam} | units={len(units)} | rows={len(rows)} | split={split_strategy}")
        if sample_output > 0:
            for i, (c, t) in enumerate(rows[:sample_output], 1):
                print(f"  [{i}] {file_token}:{c} -> {t[:140]}{'...' if len(t)>140 else ''}")

    return rows, stats

# ---------- Excel processing ----------
def process_excel_file(
    path: Path,
    mitre_code: str,
    split_strategy: str,
    family_map: List[Tuple[str,str]],
    family_guess: bool,
    prefix_code_with_file: bool,
    min_len: int,
    max_len: int,
    excel_max_rows: int,
    excel_max_cols: int,
    excel_sheet_filter: Optional[str],
    verbose: bool,
    sample_output: int
) -> Tuple[List[Tuple[str,str]], List[dict]]:
    xl = excel_open(path)
    if xl is None:
        return [], [{
            "file_token": short_file_token(path),
            "file_name": path.name,
            "sheet": "(open-error)",
            "family": "EMPTY",
            "split_strategy": split_strategy,
            "units": 0,
            "rows": 0,
            "unique_codes": 0,
            "example_codes": "",
            "path": str(path),
        }]

    # If it has a MITRE techniques sheet, handle it explicitly
    mitre_df = read_mitre_techniques_df(xl)
    rows_all: List[Tuple[str,str]] = []
    stats_all: List[dict] = []

    if mitre_df is not None and (excel_sheet_filter is None or re.search(excel_sheet_filter, "techniques", re.I)):
        mitre_rows = mitre_pairs_from_df(mitre_df, code_mode=mitre_code)
        if prefix_code_with_file:
            token = short_file_token(path)
            mitre_rows = [(f"{token}:{c}", t) for (c,t) in mitre_rows]
        rows_all.extend(mitre_rows)

        # stats
        file_token = short_file_token(path)
        seen_codes, examples = set(), []
        for c, _ in mitre_rows:
            if c not in seen_codes:
                seen_codes.add(c); examples.append(c)
            if len(examples) >= 8: break
        stats_all.append({
            "file_token": file_token,
            "file_name": path.name,
            "sheet": "techniques",
            "family": "ATTACK",
            "split_strategy": "mitre",
            "units": len(mitre_rows),       # treated as 'units'
            "rows": len(mitre_rows),
            "unique_codes": len(seen_codes),
            "example_codes": "; ".join(examples),
            "path": str(path),
        })
        # Continue to process other sheets too, below.

    # Process all other sheets generically
    for sheet_name in xl.sheet_names:
        if sheet_name.strip().lower() == "techniques":
            continue
        if excel_sheet_filter and not re.search(excel_sheet_filter, sheet_name, flags=re.I):
            continue

        try:
            df = xl.parse(sheet_name)
        except Exception:
            # unreadable sheet
            stats_all.append({
                "file_token": short_file_token(path),
                "file_name": path.name,
                "sheet": sheet_name,
                "family": "EMPTY",
                "split_strategy": split_strategy,
                "units": 0,
                "rows": 0,
                "unique_codes": 0,
                "example_codes": "",
                "path": str(path),
            })
            continue

        flat_text = flatten_sheet_to_text(df, max_rows=excel_max_rows, max_cols=excel_max_cols)
        flat_text = normalize_text(flat_text)
        if not flat_text:
            stats_all.append({
                "file_token": short_file_token(path),
                "file_name": path.name,
                "sheet": sheet_name,
                "family": "EMPTY",
                "split_strategy": split_strategy,
                "units": 0,
                "rows": 0,
                "unique_codes": 0,
                "example_codes": "",
                "path": str(path),
            })
            continue

        fam = best_family(path, family_map, family_guess, text_hint=flat_text[:4000])

        # unitization
        if split_strategy == "line":
            units = split_lines(flat_text)
        elif split_strategy == "hybrid":
            units = hybrid_split(flat_text)
        else:
            units = split_sentences(flat_text)

        # length filter
        u2 = []
        for u in units:
            u = u.strip()
            if not u:
                continue
            if min_len and len(u) < min_len:
                continue
            if max_len and len(u) > max_len:
                u = (u[:max_len] + "…")
            u2.append(u)
        units = u2

        # parse units
        rows: List[Tuple[str,str]] = []
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

        # stats
        file_token = short_file_token(path)
        seen_codes, examples = set(), []
        for c, _ in rows:
            if c not in seen_codes:
                seen_codes.add(c); examples.append(c)
            if len(examples) >= 8: break
        stats_all.append({
            "file_token": file_token,
            "file_name": path.name,
            "sheet": sheet_name,
            "family": fam,
            "split_strategy": split_strategy,
            "units": len(units),
            "rows": len(rows),
            "unique_codes": len(seen_codes),
            "example_codes": "; ".join(examples),
            "path": f"{path}#{sheet_name}",
        })

        if verbose:
            print(f"[XLSX] {path.name} | sheet={sheet_name} | fam={fam} | units={len(units)} | rows={len(rows)} | split={split_strategy}")
            if sample_output > 0:
                for i, (c, t) in enumerate(rows[:sample_output], 1):
                    print(f"  [{i}] {file_token}:{c} -> {t[:140]}{'...' if len(t)>140 else ''}")

        rows_all.extend(rows)

    return rows_all, stats_all

# ---------- Assembly / IO ----------
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

def write_family_map_csv(stats_rows: List[dict], out_path: Path):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cols = ["file_token","file_name","sheet","family","split_strategy","units","rows","unique_codes","example_codes","path"]
    with open(out_path, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in stats_rows:
            w.writerow({c: r.get(c, "") for c in cols})

# ---------- CLI ----------
def main():
    ap = argparse.ArgumentParser(description="Parse TXT + Excel into a two-column dataset with Family Map summary.")
    ap.add_argument("--in_dir", required=True, help="Directory to crawl for .txt and Excel files.")
    ap.add_argument("--out", required=True, help="Output CSV path (two columns).")
    ap.add_argument("--family_map_out", default=None, help="Optional CSV path for per-file/per-sheet summary.")
    ap.add_argument("--family_map", default=None, help="Optional CSV (pattern,family) for detection.")
    ap.add_argument("--family_guess", action="store_true", help="Guess family from filename/content.")
    ap.add_argument("--split_strategy", default="hybrid", choices=["sentence","line","hybrid"], help="Unitization strategy. Default: hybrid.")
    ap.add_argument("--allow_dupes", action="store_true", help="Do not deduplicate globally.")
    ap.add_argument("--prefix_code_with_file", action="store_true", help="Prefix code with short file token.")
    ap.add_argument("--min_len", type=int, default=0, help="Drop units shorter than this many chars.")
    ap.add_argument("--max_len", type=int, default=0, help="Truncate units longer than this many chars with an ellipsis.")
    ap.add_argument("--min_rows", type=int, default=1000, help="Minimum rows in output (oversample deterministically).")
    # Excel-specific
    ap.add_argument("--mitre_code", default="acronym", choices=["acronym","techid"], help="MITRE code mode for techniques: acronym (default) or techid.")
    ap.add_argument("--excel_max_rows", type=int, default=0, help="Max rows to read per sheet (0 = no limit).")
    ap.add_argument("--excel_max_cols", type=int, default=0, help="Max columns to read per sheet (0 = no limit).")
    ap.add_argument("--excel_sheet_filter", default=None, help="Regex to include only matching sheet names (applied to generic sheets).")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--sample_output", type=int, default=0)
    args = ap.parse_args()

    in_dir = Path(args.in_dir)
    out_path = Path(args.out)
    if not in_dir.is_dir():
        print(f"ERROR: in_dir not found: {in_dir}", file=sys.stderr)
        sys.exit(2)

    fam_map = load_family_map_csv(args.family_map) if args.family_map else []

    all_records: List[Tuple[str, str]] = []
    stats_rows: List[dict] = []

    # Find files
    txt_files = sorted(in_dir.rglob("*.txt"))
    xls_files = []
    xls_files += list(in_dir.rglob("*.xlsx"))
    xls_files += list(in_dir.rglob("*.xlsm"))
    xls_files += list(in_dir.rglob("*.xls"))

    if args.verbose:
        print(f"Found {len(txt_files)} .txt and {len(xls_files)} Excel files under {in_dir}")

    # TXT
    for p in txt_files:
        recs, stats = process_txt_file(
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
        stats_rows.append(stats)

    # Excel
    for p in xls_files:
        recs, stat_list = process_excel_file(
            p,
            mitre_code=args.mitre_code,
            split_strategy=args.split_strategy,
            family_map=fam_map,
            family_guess=args.family_guess,
            prefix_code_with_file=args.prefix_code_with_file,
            min_len=args.min_len,
            max_len=args.max_len,
            excel_max_rows=args.excel_max_rows,
            excel_max_cols=args.excel_max_cols,
            excel_sheet_filter=args.excel_sheet_filter,
            verbose=args.verbose,
            sample_output=args.sample_output
        )
        all_records.extend(recs)
        stats_rows.extend(stat_list)

    # Global de-dup (optional)
    if not args.allow_dupes:
        all_records = list(dict.fromkeys(all_records))

    all_records = ensure_min_rows(all_records, args.min_rows)
    write_two_column_csv(all_records, out_path)

    if args.family_map_out:
        write_family_map_csv(stats_rows, Path(args.family_map_out))

    print(f"✅ Wrote {len(all_records)} rows to {out_path}")
    if args.family_map_out:
        print(f"🧭 Family Map written to {args.family_map_out}")

if __name__ == "__main__":
    main()
