import argparse
import tempfile
from pathlib import Path
import pdfkit

import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup


def _ordered_spine_ids(book):
    """Return spine idrefs in reading order (skip obvious non-doc entries like 'nav')."""
    idrefs = []
    for entry in getattr(book, "spine", []):
        if isinstance(entry, tuple):
            idref = entry[0]
        else:
            idref = entry.get_id() if hasattr(entry, "get_id") else str(entry)
        if idref and idref.lower() != "nav":
            idrefs.append(idref)
    return idrefs


def _iter_chapters_in_reading_order(book):
    """Yield EpubHtml items in spine order, then any stragglers."""
    idrefs = _ordered_spine_ids(book)
    seen = set()
    if idrefs:
        for idref in idrefs:
            try:
                item = book.get_item_with_id(idref)
            except Exception:
                item = None
            if item and item.get_type() == ebooklib.ITEM_DOCUMENT and idref not in seen:
                seen.add(idref)
                yield item
        # include any docs not referenced in spine
        for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
            if item.get_id() not in seen:
                yield item
    else:
        for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
            yield item


def _title_from_meta(book):
    t = book.get_metadata("DC", "title")
    return t[0][0] if t else ""


def _creator_from_meta(book):
    a = book.get_metadata("DC", "creator")
    return a[0][0] if a else ""


def _write_entire_epub(book, root: Path):
    """Dump every item from the EPUB to a temp directory (preserve internal paths)."""
    for it in book.get_items():
        p = root / it.get_name()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(it.get_content())


def _make_cover_html(root: Path, title: str, author: str) -> Path:
    """Create a simple, clean cover page HTML file."""
    html = f"""<!doctype html>
<html>
  <head>
    <meta charset="utf-8">
    <title>{title or "EPUB"}</title>
    <style>
      @page {{ size: A4; margin: 1in; }}
      body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }}
      .wrap {{
        height: 90vh; display: flex; flex-direction: column; justify-content: center; align-items: center; text-align: center;
      }}
      h1 {{ font-size: 2.2rem; margin: 0; }}
      h3 {{ font-weight: 400; color: #444; margin-top: .6rem; }}
    </style>
  </head>
  <body>
    <div class="wrap">
      <h1>{title or ""}</h1>
      {"<h3>by " + author + "</h3>" if author else ""}
    </div>
  </body>
</html>
"""
    path = root / "_cover.html"
    path.write_text(html, encoding="utf-8")
    return path


def epub_to_pdf_wkhtml(
    epub_path,
    pdf_path,
    include_cover=True,
    include_toc=False,
    wkhtml_options=None,
    wkhtml_executable=None,
):
    """
    Convert EPUB → PDF using wkhtmltopdf via pdfkit.
    - Extracts the EPUB to a temp directory so all relative URLs work.
    - Feeds each chapter HTML (spine order) to wkhtmltopdf as separate input files.
    - Optional cover page and table of contents.
    """

    # Sensible wkhtmltopdf defaults for print-like output
    options = {
        "enable-local-file-access": "",       # REQUIRED for local assets
        "quiet": "",                          # reduce noisy logs
        "print-media-type": "",               # use print CSS when present
        "encoding": "utf-8",
        "dpi": "300",
        "margin-top": "15mm",
        "margin-right": "15mm",
        "margin-bottom": "18mm",
        "margin-left": "15mm",
        # page numbers in footer; customize or remove as you like
        "footer-right": "[page]/[toPage]",
        "footer-font-size": "9",
    }
    if wkhtml_options:
        options.update(wkhtml_options)

    config = pdfkit.configuration(wkhtmltopdf=wkhtml_executable) if wkhtml_executable else None

    book = epub.read_epub(epub_path)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_entire_epub(book, root)

        # Build input file list: optional cover + chapter files in spine order
        files: list[str] = []

        title = _title_from_meta(book)
        author = _creator_from_meta(book)

        if include_cover:
            cover_html = _make_cover_html(root, title, author)
            files.append(str(cover_html))

        chapter_paths = []
        for chap in _iter_chapters_in_reading_order(book):
            # Write each chapter's HTML as its own file (already written), but we’ll
            # ensure it has a <base> tag so *any* doc-level relative URLs resolve cleanly.
            p = root / chap.get_name()
            # inject <base href="file://<root>/"> if there isn't one
            try:
                soup = BeautifulSoup(p.read_text(encoding="utf-8", errors="ignore"), "html.parser")
                head = soup.head or soup.new_tag("head")
                # remove any existing base tags
                for b in head.find_all("base"):
                    b.decompose()
                base_tag = soup.new_tag("base", href=f"file://{root.as_posix()}/")
                head.insert(0, base_tag)
                if not soup.head:
                    if soup.html:
                        soup.html.insert(0, head)
                    else:
                        soup.insert(0, head)
                p.write_text(str(soup), encoding="utf-8")
            except Exception:
                # If parsing fails, we still pass the file through; most EPUB xhtml is well-formed.
                pass
            chapter_paths.append(str(p))

        files.extend(chapter_paths)

        # Optional TOC: wkhtml can generate a ToC from the HTML headings it sees.
        toc = {"xsl-style-sheet": None} if include_toc else None

        # Produce the PDF
        # Note: pdfkit accepts a list of input files; wkhtmltopdf will insert a page break between them.
        pdfkit.from_file(files, pdf_path, options=options, toc=toc, configuration=config)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert EPUB to PDF using wkhtmltopdf (pdfkit).")
    parser.add_argument("epub", help="Path to input .epub")
    parser.add_argument("pdf", help="Path to output .pdf")
    parser.add_argument("--no-cover", action="store_true", help="Do not add a generated cover page")
    parser.add_argument("--toc", action="store_true", help="Include an auto-generated table of contents")
    parser.add_argument("--wkhtml", default=None, help="Path to wkhtmltopdf binary (if not on PATH)")
    args = parser.parse_args()

    epub_to_pdf_wkhtml(
        args.epub,
        args.pdf,
        include_cover=not args.no_cover,
        include_toc=args.toc,
        wkhtml_executable=args.wkhtml,
    )
