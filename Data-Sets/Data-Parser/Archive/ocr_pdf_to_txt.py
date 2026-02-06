#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Robust PDF→TXT:
- pdfminer → PyPDF2 → (optional) OCR via pdf2image + Tesseract.
- --force_ocr forces OCR for all PDFs.
- Normalizes to clean UTF-8 text.
"""

import argparse, csv, re, sys, unicodedata
from pathlib import Path

# text extractors
try:
    from pdfminer.high_level import extract_text as pdfminer_extract_text
except Exception:
    pdfminer_extract_text = None

try:
    import PyPDF2
except Exception:
    PyPDF2 = None

# OCR stack
try:
    from pdf2image import convert_from_path  # needs poppler
    from PIL import Image
    import pytesseract
    OCR_STACK = True
except Exception:
    OCR_STACK = False

def normalize_text(s: str) -> str:
    if not s: return ""
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"[\u2010\u2011\u2012\u2013\u2014\u2212]", "-", s)  # fancy hyphens → -
    s = s.replace("\u00A0", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s

def extract_with_pdfminer(p: Path) -> str:
    if not pdfminer_extract_text: return ""
    try: return pdfminer_extract_text(str(p)) or ""
    except Exception: return ""

def extract_with_pypdf2(p: Path) -> str:
    if not PyPDF2: return ""
    try:
        out=[]
        with open(p, "rb") as fh:
            r=PyPDF2.PdfReader(fh)
            if getattr(r, "is_encrypted", False):
                # Attempt no-pass decrypt (sometimes works)
                try: r.decrypt("")
                except Exception: return ""
            for pg in r.pages:
                try: out.append(pg.extract_text() or "")
                except Exception: out.append("")
        return "\n".join(out)
    except Exception:
        return ""

def ocr_with_pdf2image(p: Path, lang: str=None, dpi: int=300) -> str:
    if not OCR_STACK: return ""
    try:
        images = convert_from_path(str(p), dpi=dpi)  # uses poppler
    except Exception:
        return ""
    out=[]
    for img in images:
        try:
            txt = pytesseract.image_to_string(img, lang=lang) if lang else pytesseract.image_to_string(img)
            out.append(txt or "")
        except Exception:
            out.append("")
    return "\n".join(out)

def extract_pdf_text_best(pdf_path: Path, enable_ocr: bool, force_ocr: bool, min_chars_threshold: int, lang: str=None) -> (str, str):
    """
    Returns (text, method) where method ∈ {'pdfminer','pypdf2','ocr','none'}
    """
    if not force_ocr:
        t1 = extract_with_pdfminer(pdf_path)
        if len((t1 or "").strip()) >= min_chars_threshold:
            return t1, "pdfminer"
        t2 = extract_with_pypdf2(pdf_path)
        if len((t2 or "").strip()) >= min_chars_threshold:
            return t2, "pypdf2"

    if enable_ocr or force_ocr:
        t3 = ocr_with_pdf2image(pdf_path, lang=lang, dpi=300)
        if len((t3 or "").strip()) >= 1:
            return t3, "ocr"

    return "", "none"

def write_utf8(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)

def main():
    ap = argparse.ArgumentParser(description="Robust PDF→TXT with optional OCR (pdf2image+tesseract).")
    ap.add_argument("--in_dir", required=True)
    ap.add_argument("--out_dir", required=True)
    ap.add_argument("--audit", default=None)
    ap.add_argument("--ocr", action="store_true", help="Enable OCR fallback if text is empty/short.")
    ap.add_argument("--force_ocr", action="store_true", help="Force OCR for all PDFs (skip text extractors).")
    ap.add_argument("--lang", default=None, help="Tesseract language (e.g., 'eng' or 'eng+spa').")
    ap.add_argument("--min_chars_threshold", type=int, default=50, help="If extractor text < threshold → try OCR.")
    args = ap.parse_args()

    in_dir  = Path(args.in_dir)
    out_dir = Path(args.out_dir)
    if not in_dir.is_dir():
        print(f"ERROR: in_dir not found: {in_dir}", file=sys.stderr); sys.exit(2)

    audit_rows=[]
    count=0

    for pdf in sorted(in_dir.rglob("*.pdf")):
        rel = pdf.relative_to(in_dir)
        out_txt = out_dir / rel.with_suffix(".txt")

        text, method = extract_pdf_text_best(pdf, enable_ocr=args.ocr, force_ocr=args.force_ocr,
                                             min_chars_threshold=args.min_chars_threshold, lang=args.lang)
        norm = normalize_text(text)
        write_utf8(out_txt, norm)
        count += 1

        audit_rows.append({
            "pdf_path": str(pdf),
            "txt_path": str(out_txt),
            "method": method,
            "chars_raw": len(text or ""),
            "chars_norm": len(norm or ""),
            "ocr_stack_available": OCR_STACK
        })

    if args.audit:
        apath = Path(args.audit)
        apath.parent.mkdir(parents=True, exist_ok=True)
        with open(apath, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["pdf_path","txt_path","method","chars_raw","chars_norm","ocr_stack_available"])
            w.writeheader()
            for r in audit_rows:
                w.writerow(r)

    print(f"✅ Converted {count} PDFs to {out_dir}")
    if args.audit:
        print(f"🧾 Audit written to {args.audit}")

if __name__ == "__main__":
    main()
