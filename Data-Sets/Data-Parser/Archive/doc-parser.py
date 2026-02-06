#!/usr/bin/env python3
# AI LLM Data-Set 2-COL Builder (General PDF → 2-Column CSV)
# Author: ChatGPT (GPT-5 Thinking)
#
# Features:
# - General-purpose parsing from manuals/standards/guides
# - Flexible "code" detection via multiple regex patterns
# - Greedy segment capture: each code + text until next code
# - Pre-cleaning: de-hyphenation, whitespace normalization
# - Fallback: heading-like line splitter if no code matches
# - CSV output with 2 columns: Code, Text
#
# Notes:
# - For two-column PDFs with mixed reading order, pypdf’s plain text
#   extraction can still be imperfect. If you have issues, consider installing
#   pdfplumber and swapping the extractor for better layout-aware text extraction.

import argparse
import re
import sys
from pathlib import Path
import pandas as pd

try:
    from pypdf import PdfReader
except Exception as e:
    print("pypdf is required: pip install pypdf", file=sys.stderr)
    raise

# ------------------------------
# 1) Default Configuration
# ------------------------------
DEFAULT_CODE_PATTERNS = [
    # Numeric dotted like 5.11 or 6.2.3
    r"(?:^|\n)\s*(\d{1,2}\.\d{1,2}(?:\.\d{1,2})?)\s+",

    # Annex/lettered dotted like A.5.1 or B.2.3
    r"(?:^|\n)\s*([A-Z]\.\d{1,2}(?:\.\d{1,2})?)\s+",

    # Hyphen/letter prefixed codes like CM-01, AC-2, REQ-1.1, CTRL-12
    r"(?:^|\n)\s*([A-Z]{2,}-\d+(?:\.\d+){0,2})\s+",

    # “REQ 1.1.1” or “REQ 1.1” forms (space instead of hyphen)
    r"(?:^|\n)\s*([A-Z]{2,}\s+\d+(?:\.\d+){0,2})\s+",
]

# Heuristic heading-like line: shortish line, Title Case or all-caps, ends with no punctuation.
HEADING_LINE_RE = re.compile(r"^[A-Z0-9][A-Za-z0-9 \-/()]{1,80}$")

# ------------------------------
# 2) Text Extraction
# ------------------------------
def extract_text_from_pdf(pdf_path: Path) -> str:
    reader = PdfReader(str(pdf_path))
    chunks = []
    for i, page in enumerate(reader.pages):
        try:
            txt = page.extract_text() or ""
        except Exception:
            txt = ""
        chunks.append(txt)
    text = "\n\n".join(chunks)
    return text

# ------------------------------
# 3) Pre-cleaning Utilities
# ------------------------------
def normalize_text(raw: str) -> str:
    if not raw:
        return ""
    # De-hyphenate common PDF line breaks: "infor-\nmation" -> "information"
    txt = re.sub(r"(\w)-\n(\w)", r"\1\2", raw)
    # Normalize newlines
    txt = txt.replace("\r\n", "\n").replace("\r", "\n")
    # Collapse multiple blank lines to max 2
    txt = re.sub(r"\n{3,}", "\n\n", txt)
    # Strip trailing spaces on lines
    txt = re.sub(r"[ \t]+\n", "\n", txt)
    return txt

# ------------------------------
# 4) Core Parse by Codes
# ------------------------------
def build_master_code_regex(code_patterns):
    # Combine into one big OR, with each pattern ensuring a capturing group for the code
    wrapped = [f"({p})" if "(?" not in p else p for p in code_patterns]  # conservative wrap
    # We need exactly one capture (the code). Ensure inner patterns already have one (as provided).
    # Join with OR while maintaining original capture group positions.
    combined = "|".join(code_patterns)
    # We’ll search with re.finditer on the combined pattern with MULTILINE and DOTALL off.
    return re.compile(combined, flags=re.MULTILINE)

def parse_by_codes(full_text: str, code_patterns) -> list[dict]:
    code_re = build_master_code_regex(code_patterns)

    # Find all code “anchors” as (start_index, end_index, code_text)
    anchors = []
    for m in code_re.finditer(full_text):
        # Identify which inner alt matched: one of the groups will be the code
        code = None
        # Scan groups to find the one that captured something that looks like a code token
        for g in m.groups():
            if g and len(g.strip()) > 0:
                code = g.strip()
                break
        if code:
            anchors.append((m.start(), m.end(), code))

    if not anchors:
        return []

    # Build segments between anchors
    segments = []
    for idx, (s, e, code) in enumerate(anchors):
        start_of_text = e
        end_of_text = anchors[idx + 1][0] if idx + 1 < len(anchors) else len(full_text)
        body = full_text[start_of_text:end_of_text].strip()
        body = cleanup_segment_body(body, code_patterns)
        if body:
            segments.append({"Code": code, "Text": body})

    return segments

def cleanup_segment_body(body: str, code_patterns) -> str:
    # Remove a stray leading code pattern if mis-extracted
    for p in code_patterns:
        try:
            body = re.sub(p, "", body, count=1, flags=re.MULTILINE)
        except re.error:
            # If flags unsupported in caller version, try without flags
            body = re.sub(p, "", body, count=1)
    # Normalize whitespace inside segment
    body = re.sub(r"[ \t]+", " ", body)
    body = re.sub(r"\s*\n\s*", " ", body)
    body = re.sub(r"\s{2,}", " ", body)
    return body.strip()

# ------------------------------
# 5) Fallback Parse (Heading-like lines)
# ------------------------------
def parse_by_headings(full_text: str) -> list[dict]:
    """
    If we can’t detect codes, use a heuristic:
    - A line that "looks like" a heading starts a segment.
    - Capture lines until the next heading-like line.
    """
    lines = full_text.split("\n")
    segments = []
    current_code = None
    current_buf = []

    def flush():
        if current_code and current_buf:
            text = " ".join([ln.strip() for ln in current_buf if ln.strip()])
            text = re.sub(r"\s{2,}", " ", text).strip()
            if text:
                segments.append({"Code": current_code, "Text": text})

    for ln in lines:
        line = ln.strip()
        if HEADING_LINE_RE.match(line):
            # New heading → flush old
            flush()
            current_code = line
            current_buf = []
        else:
            current_buf.append(line)

    flush()
    return segments

# ------------------------------
# 6) Main Orchestration
# ------------------------------
def build_dataset(
    pdf_path: Path,
    output_csv: Path,
    code_patterns: list[str] = None,
    prefer_headings_if_empty: bool = True,
    min_chars: int = 30
):
    text = extract_text_from_pdf(pdf_path)
    text = normalize_text(text)

    patterns = code_patterns or DEFAULT_CODE_PATTERNS
    rows = parse_by_codes(text, patterns)

    if (not rows or sum(len(r["Text"]) for r in rows) < min_chars) and prefer_headings_if_empty:
        # Fallback if we found nothing (or text too tiny)
        rows = parse_by_headings(text)

    # Deduplicate by (Code, Text)
    dedup = []
    seen = set()
    for r in rows:
        key = (r["Code"], r["Text"])
        if key not in seen:
            seen.add(key)
            dedup.append(r)

    df = pd.DataFrame(dedup)
    if not df.empty:
        df = df[["Code", "Text"]]
    df.to_csv(output_csv, index=False)
    return df

# ------------------------------
# 7) CLI
# ------------------------------
def parse_cli():
    ap = argparse.ArgumentParser(
        description="General PDF → 2-column CSV (Code, Text) using regex-based code anchors or heading heuristics."
    )
    ap.add_argument("pdf", help="Path to input PDF")
    ap.add_argument("out_csv", help="Path to output CSV file")
    ap.add_argument(
        "--pattern",
        action="append",
        default=[],
        help="Add a custom code regex (with exactly one capturing group for the code). "
             "Repeat flag to add multiple patterns. Example: --pattern '(^|\\n)\\s*(REQ-\\d+(?:\\.\\d+){0,2})\\s+'"
    )
    ap.add_argument(
        "--no-fallback",
        action="store_true",
        help="Disable heading-based fallback parsing."
    )
    ap.add_argument(
        "--min-chars",
        type=int,
        default=30,
        help="If total captured text is less than this and no-fallback is off, fallback to heading parsing."
    )
    return ap.parse_args()

def main():
    args = parse_cli()
    pdf_path = Path(args.pdf).expanduser()
    out_csv = Path(args.out_csv).expanduser()
    patterns = args.pattern if args.pattern else None

    if not pdf_path.exists():
        print(f"Error: PDF not found at {pdf_path}", file=sys.stderr)
        sys.exit(1)

    df = build_dataset(
        pdf_path=pdf_path,
        output_csv=out_csv,
        code_patterns=patterns,
        prefer_headings_if_empty=(not args.no_fallback),
        min_chars=args.min_chars
    )
    print(f"Created: {out_csv}")
    print(f"Total rows: {len(df)}")

if __name__ == "__main__":
    main()
