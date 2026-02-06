#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Robust PDF → UTF-8 TXT extraction:
Tries multiple engines and keeps the best result:
  1) pdfminer.six (with LAParams)
  2) pdfplumber
  3) PyMuPDF (fitz)
  4) pypdfium2
  5) Poppler 'pdftotext' CLI
Optional OCR fallback via pdf2image + Tesseract if requested.

Outputs:
  out_dir/<relative/path>.txt
Audit CSV (optional):
  pdf_path, txt_path, engine, chars_raw, chars_norm, note

Usage:
  python3 pdf_to_txt_best.py \
    --in_dir "/path/to/pdfs" \
    --out_dir "/path/to/txt" \
    --audit "/path/to/audit.csv"

  # Enable OCR only if needed:
  --ocr         (fallback if text tiny)
  --force_ocr   (skip text engines; OCR everything)

  python3 pdf_to_txt_best.py --in_dir ".../RAW/Compliance" --out_dir ".../TXT" --audit ".../TXT/pdf_audit.csv" --ocr

"""

import argparse, csv, os, re, sys, unicodedata, shutil, subprocess
from pathlib import Path

# -------- Optional imports (engines) --------
ENGINES = []

# pdfminer.six
try:
    from pdfminer.high_level import extract_text as pdfminer_extract_text
    from pdfminer.layout import LAParams
    ENGINES.append("pdfminer")
except Exception:
    pdfminer_extract_text = None

# pdfplumber
try:
    import pdfplumber
    ENGINES.append("pdfplumber")
except Exception:
    pdfplumber = None

# PyMuPDF
try:
    import fitz  # pymupdf
    ENGINES.append("pymupdf")
except Exception:
    fitz = None

# pypdfium2
try:
    import pypdfium2 as pdfium
    ENGINES.append("pypdfium2")
except Exception:
    pdfium = None

# Poppler's pdftotext (CLI)
PDFTOTEXT_BIN = shutil.which("pdftotext")
if PDFTOTEXT_BIN:
    ENGINES.append("pdftotext")

# OCR stack (optional)
try:
    from pdf2image import convert_from_path
    from PIL import Image
    import pytesseract
    OCR_AVAILABLE = True
except Exception:
    OCR_AVAILABLE = False

# --------------------------------------------

def normalize_text(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s)
    # normalize hyphens to ASCII '-'
    s = re.sub(r"[\u2010\u2011\u2012\u2013\u2014\u2212]", "-", s)
    # NBSP to space
    s = s.replace("\u00A0", " ")
    # collapse whitespace
    s = re.sub(r"\s+", " ", s)
    return s.strip()

def extract_pdf_pdfminer(path: Path, max_pages: int = None) -> str:
    if not pdfminer_extract_text:
        return ""
    try:
        laparams = LAParams(line_margin=0.2, char_margin=2.0, word_margin=0.1, detect_vertical=False)
        # pdfminer doesn't expose per-page limit directly; good compromise is full run
        return pdfminer_extract_text(str(path), laparams=laparams) or ""
    except Exception:
        return ""

def extract_pdf_pdfplumber(path: Path, max_pages: int = None) -> str:
    if not pdfplumber:
        return ""
    try:
        out = []
        with pdfplumber.open(str(path)) as pdf:
            for i, page in enumerate(pdf.pages):
                if max_pages and i >= max_pages:
                    break
                txt = page.extract_text() or ""
                out.append(txt)
        return "\n".join(out)
    except Exception:
        return ""

def extract_pdf_pymupdf(path: Path, max_pages: int = None) -> str:
    if not fitz:
        return ""
    try:
        out = []
        with fitz.open(str(path)) as doc:
            for i, page in enumerate(doc):
                if max_pages and i >= max_pages:
                    break
                # textpage options: "text" (layout text), "blocks", or "rawdict"
                txt = page.get_text("text") or ""
                out.append(txt)
        return "\n".join(out)
    except Exception:
        return ""

def extract_pdf_pypdfium2(path: Path, max_pages: int = None) -> str:
    if not pdfium:
        return ""
    try:
        out = []
        pdf = pdfium.PdfDocument(str(path))
        n = len(pdf)
        limit = n if max_pages is None else min(n, max_pages)
        for i in range(limit):
            page = pdf.get_page(i)
            txtpage = page.get_textpage()
            txt = txtpage.get_text_range()
            out.append(txt or "")
            txtpage.close()
            page.close()
        return "\n".join(out)
    except Exception:
        return ""

def extract_pdf_pdftotext_cli(path: Path) -> str:
    if not PDFTOTEXT_BIN:
        return ""
    try:
        # -layout sometimes helps; try without first for fidelity, then with layout if short
        txt = subprocess.run([PDFTOTEXT_BIN, "-enc", "UTF-8", str(path), "-"],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True).stdout.decode("utf-8", "ignore")
        if len(txt.strip()) < 20:
            txt2 = subprocess.run([PDFTOTEXT_BIN, "-layout", "-enc", "UTF-8", str(path), "-"],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True).stdout.decode("utf-8", "ignore")
            if len(txt2.strip()) > len(txt.strip()):
                return txt2
        return txt
    except Exception:
        return ""

def extract_pdf_ocr(path: Path, lang: str = None, dpi: int = 300, max_pages: int = None) -> str:
    if not OCR_AVAILABLE:
        return ""
    try:
        images = convert_from_path(str(path), dpi=dpi)  # requires poppler
    except Exception:
        return ""
    out = []
    for i, im in enumerate(images):
        if max_pages and i >= max_pages:
            break
        try:
            txt = pytesseract.image_to_string(im, lang=lang) if lang else pytesseract.image_to_string(im)
            out.append(txt or "")
        except Exception:
            out.append("")
    return "\n".join(out)

ENGINE_FUNCS = {
    "pdfminer":   extract_pdf_pdfminer,
    "pdfplumber": extract_pdf_pdfplumber,
    "pymupdf":    extract_pdf_pymupdf,
    "pypdfium2":  extract_pdf_pypdfium2,
    "pdftotext":  extract_pdf_pdftotext_cli,
}

def best_text_from_all(path: Path, enable_ocr: bool, force_ocr: bool, lang: str, min_chars_threshold: int, max_pages: int = None):
    tried = []
    best = ("", "", 0)  # (text, engine, chars_norm)

    def consider(label, text):
        nonlocal best, tried
        norm = normalize_text(text)
        score = len(norm)
        tried.append((label, len(text), score))
        if score > best[2]:
            best = (text, label, score)

    if not force_ocr:
        for eng in ENGINES:
            text = ENGINE_FUNCS[eng](path, max_pages=max_pages) if eng in ("pdfminer","pdfplumber","pymupdf","pypdfium2") else ENGINE_FUNCS[eng](path)
            consider(eng, text)
            # If we already exceed threshold, keep going to see if others beat it,
            # but you can early-stop here if you want performance.
        if best[2] < min_chars_threshold and enable_ocr:
            text = extract_pdf_ocr(path, lang=lang, dpi=300, max_pages=max_pages)
            consider("ocr", text)
    else:
        text = extract_pdf_ocr(path, lang=lang, dpi=300, max_pages=max_pages)
        consider("ocr", text)

    return best, tried

def write_utf8(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)

def main():
    ap = argparse.ArgumentParser(description="Robust multi-engine PDF→TXT extractor.")
    ap.add_argument("--in_dir", required=True, help="Folder with PDFs (recursively).")
    ap.add_argument("--out_dir", required=True, help="Folder for .txt outputs.")
    ap.add_argument("--audit", default=None, help="CSV to log engine choice and char counts.")
    ap.add_argument("--ocr", action="store_true", help="Enable OCR fallback if text short/empty.")
    ap.add_argument("--force_ocr", action="store_true", help="Force OCR for all PDFs.")
    ap.add_argument("--lang", default=None, help="Tesseract language, e.g. 'eng'.")
    ap.add_argument("--min_chars_threshold", type=int, default=50, help="Below this, OCR fallback may be used.")
    ap.add_argument("--max_pages", type=int, default=None, help="Limit pages per PDF for speed (debug).")
    args = ap.parse_args()

    in_dir  = Path(args.in_dir)
    out_dir = Path(args.out_dir)
    if not in_dir.is_dir():
        print(f"ERROR: in_dir not found: {in_dir}", file=sys.stderr); sys.exit(2)

    if not ENGINES and not args.ocr and not args.force_ocr:
        print("WARNING: No text engines available and OCR disabled. Install one of: pdfminer.six, pdfplumber, pymupdf, pypdfium2, or 'pdftotext' (poppler).", file=sys.stderr)

    audit_rows = []
    count = 0

    for pdf in sorted(in_dir.rglob("*.pdf")):
        rel = pdf.relative_to(in_dir)
        out_txt = out_dir / rel.with_suffix(".txt")

        (best_text, best_engine, best_score), tried = best_text_from_all(
            pdf, enable_ocr=args.ocr, force_ocr=args.force_ocr,
            lang=args.lang, min_chars_threshold=args.min_chars_threshold,
            max_pages=args.max_pages
        )
        norm = normalize_text(best_text)
        write_utf8(out_txt, norm)
        count += 1

        row = {
            "pdf_path": str(pdf),
            "txt_path": str(out_txt),
            "engine": best_engine or "none",
            "chars_raw": len(best_text or ""),
            "chars_norm": len(norm or ""),
            "note": "; ".join([f"{lab}:{raw}/{norm}" for (lab, raw, norm) in tried])
        }
        audit_rows.append(row)

    if args.audit:
        apath = Path(args.audit)
        apath.parent.mkdir(parents=True, exist_ok=True)
        with open(apath, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["pdf_path","txt_path","engine","chars_raw","chars_norm","note"])
            w.writeheader()
            for r in audit_rows:
                w.writerow(r)

    print(f"✅ Converted {count} PDFs to {out_dir}")
    if args.audit:
        print(f"🧾 Audit written to {args.audit}")

if __name__ == "__main__":
    main()
