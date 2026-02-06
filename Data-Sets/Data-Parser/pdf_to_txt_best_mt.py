#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Threaded, verbose PDF → UTF-8 TXT extractor with per-file logging and timeouts.

- Tries multiple engines and chooses the best (largest normalized text):
    1) pdfminer.six (LAParams tuned)
    2) pdfplumber
    3) PyMuPDF (fitz)
    4) pypdfium2
    5) Poppler 'pdftotext' CLI
    6) (optional) OCR via pdf2image + Tesseract (fallback or forced)

- Threaded processing with a worker pool and per-file timeouts
- Verbose prints (start/finish + engine results)
- Audit CSV: engine used, char counts, and engine-by-engine short metrics

Install (macOS):
    brew install poppler tesseract
    pip3 install pdfminer.six pdfplumber pymupdf pypdfium2 pdf2image pillow pytesseract

Usage:
    python3 pdf_to_txt_best_mt.py \
      --in_dir "/path/to/pdfs" \
      --out_dir "/path/to/txt" \
      --audit "/path/to/audit.csv" \
      --workers 6 --verbose --ocr

    # If you suspect stalls:
    --file_timeout 120  (seconds per file)
"""

import argparse, csv, os, re, sys, time, unicodedata, shutil, subprocess, traceback
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError

# ---------- Optional imports (engines) ----------
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
    import fitz  # PyMuPDF
    ENGINES.append("pymupdf")
except Exception:
    fitz = None

# pypdfium2
try:
    import pypdfium2 as pdfium
    ENGINES.append("pypdfium2")
except Exception:
    pdfium = None

# Poppler 'pdftotext' CLI
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

# -----------------------------------------------

def now_ts():
    return time.strftime("%H:%M:%S")

def normalize_text(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"[\u2010\u2011\u2012\u2013\u2014\u2212]", "-", s)  # fancy hyphens → '-'
    s = s.replace("\u00A0", " ")  # NBSP → space
    s = re.sub(r"\s+", " ", s)
    return s.strip()

def extract_pdf_pdfminer(path: Path, max_pages: int = None) -> str:
    if not pdfminer_extract_text:
        return ""
    try:
        # Tweak layout params for better word joining
        laparams = LAParams(line_margin=0.2, char_margin=2.0, word_margin=0.1, detect_vertical=False)
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
                if max_pages and i >= max_pages: break
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
                if max_pages and i >= max_pages: break
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
        # First try default, then layout if too short
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
        images = convert_from_path(str(path), dpi=dpi)
    except Exception:
        return ""
    out = []
    for i, im in enumerate(images):
        if max_pages and i >= max_pages: break
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

def best_text_from_all(path: Path, enable_ocr: bool, force_ocr: bool, lang: str,
                       min_chars_threshold: int, max_pages: int, verbose: bool):
    tried = []
    best_text, best_engine, best_score = "", "", 0

    def consider(label, text):
        nonlocal best_text, best_engine, best_score
        norm = normalize_text(text)
        score = len(norm)
        tried.append((label, len(text), score))
        if score > best_score:
            best_text, best_engine, best_score = text, label, score

    if not force_ocr:
        for eng in ENGINES:
            try:
                if eng in ("pdfminer","pdfplumber","pymupdf","pypdfium2"):
                    text = ENGINE_FUNCS[eng](path, max_pages=max_pages)
                else:
                    text = ENGINE_FUNCS[eng](path)
                consider(eng, text)
            except Exception as e:
                tried.append((eng, 0, 0))
                if verbose:
                    print(f"[{now_ts()}]   ! Engine {eng} error on {path.name}: {e}")
        if best_score < min_chars_threshold and enable_ocr:
            try:
                t = extract_pdf_ocr(path, lang=lang, dpi=300, max_pages=max_pages)
                consider("ocr", t)
            except Exception as e:
                tried.append(("ocr", 0, 0))
                if verbose:
                    print(f"[{now_ts()}]   ! OCR error on {path.name}: {e}")
    else:
        # Force OCR path
        try:
            t = extract_pdf_ocr(path, lang=lang, dpi=300, max_pages=max_pages)
            consider("ocr", t)
        except Exception as e:
            tried.append(("ocr", 0, 0))
            if verbose:
                print(f"[{now_ts()}]   ! OCR error on {path.name}: {e}")

    return (best_text, best_engine, best_score), tried

def write_utf8(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)

def process_one(pdf: Path, base_in: Path, out_dir: Path, args) -> dict:
    start = time.time()
    rel = pdf.relative_to(base_in)
    out_txt = out_dir / rel.with_suffix(".txt")
    if args.verbose:
        print(f"[{now_ts()}] ▶ Start: {pdf}")

    (best_text, best_engine, best_score), tried = best_text_from_all(
        pdf, enable_ocr=args.ocr, force_ocr=args.force_ocr,
        lang=args.lang, min_chars_threshold=args.min_chars_threshold,
        max_pages=args.max_pages, verbose=args.verbose
    )
    norm = normalize_text(best_text)
    write_utf8(out_txt, norm)
    elapsed = time.time() - start

    if args.verbose:
        print(f"[{now_ts()}] ✓ Done:  {pdf} | engine={best_engine or 'none'} | chars={len(norm)} | {elapsed:.2f}s")

    note = "; ".join([f"{lab}:{raw}/{normc}" for (lab, raw, normc) in tried])
    return {
        "pdf_path": str(pdf),
        "txt_path": str(out_txt),
        "engine": best_engine or "none",
        "chars_raw": len(best_text or ""),
        "chars_norm": len(norm or ""),
        "elapsed_sec": f"{elapsed:.2f}",
        "note": note
    }

def main():
    ap = argparse.ArgumentParser(description="Threaded, verbose PDF→TXT extractor with audit and timeouts.")
    ap.add_argument("--in_dir", required=True, help="Folder with PDFs (recursively).")
    ap.add_argument("--out_dir", required=True, help="Folder for .txt outputs.")
    ap.add_argument("--audit", default=None, help="CSV to log engine choice and char counts.")
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 4, help="Number of threads.")
    ap.add_argument("--file_timeout", type=int, default=300, help="Per-file timeout (seconds).")
    ap.add_argument("--ocr", action="store_true", help="Enable OCR fallback if text short/empty.")
    ap.add_argument("--force_ocr", action="store_true", help="Force OCR for all PDFs.")
    ap.add_argument("--lang", default=None, help="Tesseract language code, e.g., 'eng'.")
    ap.add_argument("--min_chars_threshold", type=int, default=50, help="Below this, OCR fallback may be used.")
    ap.add_argument("--max_pages", type=int, default=None, help="Limit pages per PDF (debug/speed).")
    ap.add_argument("--verbose", action="store_true", help="Print verbose progress logs.")
    args = ap.parse_args()

    in_dir  = Path(args.in_dir)
    out_dir = Path(args.out_dir)
    if not in_dir.is_dir():
        print(f"ERROR: in_dir not found: {in_dir}", file=sys.stderr); sys.exit(2)

    if not ENGINES and not args.ocr and not args.force_ocr:
        print("WARNING: No text engines available and OCR disabled. Install one of: pdfminer.six, pdfplumber, pymupdf, pypdfium2, or 'pdftotext' (poppler).", file=sys.stderr)

    pdfs = sorted(in_dir.rglob("*.pdf"))
    total = len(pdfs)
    if total == 0:
        print("No PDFs found."); sys.exit(0)

    if args.verbose:
        print(f"[{now_ts()}] Found {total} PDFs. Using {args.workers} worker(s).")

    audit_rows = []
    done = 0
    errors = 0

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {
            ex.submit(process_one, pdf, in_dir, out_dir, args): pdf
            for pdf in pdfs
        }
        for fut in as_completed(futures):
            pdf = futures[fut]
            try:
                row = fut.result(timeout=args.file_timeout)
                audit_rows.append(row)
            except TimeoutError:
                errors += 1
                if args.verbose:
                    print(f"[{now_ts()}] ✖ TIMEOUT: {pdf} (> {args.file_timeout}s)")
                audit_rows.append({
                    "pdf_path": str(pdf),
                    "txt_path": "",
                    "engine": "timeout",
                    "chars_raw": 0,
                    "chars_norm": 0,
                    "elapsed_sec": str(args.file_timeout),
                    "note": "timeout"
                })
            except Exception as e:
                errors += 1
                if args.verbose:
                    print(f"[{now_ts()}] ✖ ERROR: {pdf} | {e}")
                    traceback.print_exc()
                audit_rows.append({
                    "pdf_path": str(pdf),
                    "txt_path": "",
                    "engine": "error",
                    "chars_raw": 0,
                    "chars_norm": 0,
                    "elapsed_sec": "0",
                    "note": f"error: {e}"
                })
            finally:
                done += 1
                if args.verbose:
                    print(f"[{now_ts()}] Progress: {done}/{total} complete | errors={errors}")

    if args.audit:
        apath = Path(args.audit)
        apath.parent.mkdir(parents=True, exist_ok=True)
        with open(apath, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["pdf_path","txt_path","engine","chars_raw","chars_norm","elapsed_sec","note"])
            w.writeheader()
            for r in audit_rows:
                w.writerow(r)
        print(f"🧾 Audit written to {args.audit}")

    ok_count = sum(1 for r in audit_rows if r["engine"] not in ("timeout","error"))
    print(f"✅ Done. Files: {total} | OK: {ok_count} | Errors/Timeouts: {errors} | Out: {out_dir}")

if __name__ == "__main__":
    main()
