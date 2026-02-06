#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Batch convert PDFs to UTF-8 .txt with normalization and optional OCR fallback.

Cascade:
  1) pdfminer.six
  2) PyPDF2
  3) (optional) Tesseract OCR via pytesseract if text appears empty/too short

Outputs:
  out_dir/<basename>.txt  (UTF-8)
Also writes a simple audit CSV summarizing extraction.

Install:
  pip install pdfminer.six PyPDF2 pillow pytesseract
And install Tesseract binary if you enable --ocr:
  macOS (brew): brew install tesseract
  Ubuntu:        sudo apt-get install tesseract-ocr

Usage:
  python3 pdf_to_txt_batch.py --in_dir "/path/to/pdfs" --out_dir "/path/to/txt" --audit "/path/to/audit.csv" --ocr
"""

import argparse
import csv
import io
import os
import re
import sys
import unicodedata
from pathlib import Path
from typing import Optional, Tuple

# Optional imports
try:
    from pdfminer.high_level import extract_text as pdfminer_extract_text
except Exception:
    pdfminer_extract_text = None

try:
    import PyPDF2
except Exception:
    PyPDF2 = None

# OCR stack (optional)
try:
    from PIL import Image
    import pytesseract
    OCR_AVAILABLE = True
except Exception:
    OCR_AVAILABLE = False

def normalize_text(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s)
    # normalize hyphens and spaces
    s = re.sub(r"[\u2010\u2011\u2012\u2013\u2014\u2212]", "-", s)  # fancy hyphens -> '-'
    s = s.replace("\u00A0", " ")  # NBSP -> space
    # collapse whitespace
    s = re.sub(r"\s+", " ", s)
    return s.strip()

def extract_with_pdfminer(pdf_path: Path) -> str:
    if pdfminer_extract_text is None:
        return ""
    try:
        return pdfminer_extract_text(str(pdf_path)) or ""
    except Exception:
        return ""

def extract_with_pypdf2(pdf_path: Path) -> str:
    if PyPDF2 is None:
        return ""
    try:
        out = []
        with open(pdf_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                try:
                    out.append(page.extract_text() or "")
                except Exception:
                    out.append("")
        return "\n".join(out)
    except Exception:
        return ""

def pdf_page_images_to_pil(pdf_path: Path, dpi: int = 300):
    """
    Minimal image render via 'pdftoppm' if available, else no OCR image rendering.
    This avoids heavy dependencies (pdf2image/poppler) for portability.
    If you want better OCR, install 'pdf2image' + poppler and render page images properly.
    """
    # Try poppler's pdftoppm if present
    import shutil, subprocess, tempfile
    if shutil.which("pdftoppm") is None:
        return []  # no rendering available
    images = []
    with tempfile.TemporaryDirectory() as tmpdir:
        out_prefix = Path(tmpdir) / "pg"
        cmd = ["pdftoppm", "-r", str(dpi), "-png", str(pdf_path), str(out_prefix)]
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            for png in sorted(Path(tmpdir).glob("pg-*.png")):
                try:
                    images.append(Image.open(png).convert("RGB"))
                except Exception:
                    pass
        except Exception:
            return []
    return images

def ocr_pdf(pdf_path: Path, lang: Optional[str] = None, dpi: int = 300) -> str:
    if not OCR_AVAILABLE:
        return ""
    # Render each page to image, then OCR
    pages = pdf_page_images_to_pil(pdf_path, dpi=dpi)
    if not pages:
        return ""
    out = []
    for img in pages:
        try:
            txt = pytesseract.image_to_string(img, lang=lang) if lang else pytesseract.image_to_string(img)
            out.append(txt or "")
        except Exception:
            out.append("")
    return "\n".join(out)

def extract_pdf_text_best(pdf_path: Path, enable_ocr: bool, min_chars_threshold: int = 50) -> Tuple[str, str]:
    """
    Returns (text, method) where method ∈ {'pdfminer','pypdf2','ocr','none'}
    min_chars_threshold: if under this after pdfminer/pypdf2, treat as 'no text' and try OCR (if enabled)
    """
    text = extract_with_pdfminer(pdf_path)
    if len(text.strip()) >= min_chars_threshold:
        return text, "pdfminer"
    text2 = extract_with_pypdf2(pdf_path)
    if len(text2.strip()) >= min_chars_threshold:
        return text2, "pypdf2"
    if enable_ocr:
        text3 = ocr_pdf(pdf_path)
        if len(text3.strip()) >= 1:  # OCR may be short, still valuable
            return text3, "ocr"
    return "", "none"

def write_utf8(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)

def main():
    ap = argparse.ArgumentParser(description="Batch convert PDFs to normalized UTF-8 .txt with optional OCR.")
    ap.add_argument("--in_dir", required=True, help="Folder containing PDFs (recursively).")
    ap.add_argument("--out_dir", required=True, help="Folder to write .txt files.")
    ap.add_argument("--audit", default=None, help="Optional CSV to log extraction stats.")
    ap.add_argument("--ocr", action="store_true", help="Enable OCR fallback (requires Tesseract + pytesseract).")
    ap.add_argument("--lang", default=None, help="Tesseract language code(s), e.g., 'eng' or 'eng+deu'.")
    ap.add_argument("--min_chars_threshold", type=int, default=50, help="Chars threshold to decide 'no text' for OCR fallback.")
    args = ap.parse_args()

    in_dir = Path(args.in_dir)
    out_dir = Path(args.out_dir)
    audit_path = Path(args.audit) if args.audit else None

    if not in_dir.is_dir():
        print(f"ERROR: in_dir not found: {in_dir}", file=sys.stderr)
        sys.exit(2)

    # Prepare audit
    audit_rows = []
    processed = 0

    for pdf in sorted(in_dir.rglob("*.pdf")):
        rel = pdf.relative_to(in_dir)
        out_txt = out_dir / rel.with_suffix(".txt")
        text, method = extract_pdf_text_best(pdf, enable_ocr=args.ocr, min_chars_threshold=args.min_chars_threshold)

        # Normalize to UTF-8 friendly plain text
        norm = normalize_text(text)

        write_utf8(out_txt, norm)
        processed += 1

        audit_rows.append({
            "pdf_path": str(pdf),
            "txt_path": str(out_txt),
            "method": method,
            "chars_raw": len(text or ""),
            "chars_norm": len(norm or "")
        })

    if audit_path:
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        with open(audit_path, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["pdf_path","txt_path","method","chars_raw","chars_norm"])
            w.writeheader()
            for r in audit_rows:
                w.writerow(r)

    print(f"✅ Converted {processed} PDFs to {out_dir}")
    if audit_path:
        print(f"🧾 Audit written to {audit_path}")

if __name__ == "__main__":
    main()
