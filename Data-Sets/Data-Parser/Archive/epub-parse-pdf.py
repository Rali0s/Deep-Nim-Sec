import os
import io
import posixpath
import tempfile
from pathlib import Path

import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup  # pip install beautifulsoup4
from weasyprint import HTML     # pip install weasyprint


def _ordered_spine_ids(book):
    idrefs = []
    for entry in getattr(book, "spine", []):
        if isinstance(entry, tuple):
            idrefs.append(entry[0])
        else:
            if hasattr(entry, "get_id"):
                idrefs.append(entry.get_id())
            else:
                idrefs.append(str(entry))
    return idrefs


def _iter_chapters_in_reading_order(book):
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
        for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
            if item.get_id() not in seen:
                yield item
    else:
        for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
            yield item


def _write_epub_to_tempdir(book, temp_root: Path):
    """Dump all EPUB resources to a real directory so WeasyPrint can load relative URLs."""
    for item in book.get_items():
        rel = Path(item.get_name())  # POSIX paths inside EPUB
        out_path = temp_root / rel
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(item.get_content())


def _rewrite_relative_urls(chapter_item, soup: BeautifulSoup):
    """
    Make URLs in this chapter absolute to the EPUB root (temp_root) by
    prefixing the chapter's directory. This keeps links working inside
    a single master HTML whose base_url is the EPUB root.
    """
    base = Path(chapter_item.get_name())  # e.g. Text/ch01.xhtml
    base_dir = base.parent.as_posix()

    def _join(rel):
        if not rel or rel.startswith(("http://", "https://", "data:", "file:/")):
            return rel
        # keep anchors untouched
        if rel.startswith("#"):
            return rel
        # normalize POSIX path
        merged = posixpath.normpath(posixpath.join(base_dir, rel))
        return merged

    # Typical attributes that hold URLs
    ATTRS = [
        ("img", "src"),
        ("image", "href"),      # <image href> in inline SVG
        ("link", "href"),
        ("script", "src"),
        ("a", "href"),
        ("source", "srcset"),
        ("video", "poster"),
    ]

    for tag, attr in ATTRS:
        for el in soup.find_all(tag):
            val = el.get(attr)
            if not val:
                continue
            if attr == "srcset":
                # Handle multiple entries: "img1.png 1x, img2.png 2x"
                parts = []
                for chunk in val.split(","):
                    seg = chunk.strip().split()
                    if not seg:
                        continue
                    seg[0] = _join(seg[0])
                    parts.append(" ".join(seg))
                el[attr] = ", ".join(parts)
            else:
                el[attr] = _join(val)

    # Also set a <base> to the EPUB root so any missed relative URLs resolve there
    head = soup.head or soup.new_tag("head")
    base_tag = soup.new_tag("base", href="/")
    # remove existing <base> if any
    for b in head.find_all("base"):
        b.decompose()
    head.insert(0, base_tag)
    if not soup.head:
        soup.html.insert(0, head)

    return soup


def _title_from_meta(book):
    t = book.get_metadata("DC", "title")
    return t[0][0] if t else ""


def _creator_from_meta(book):
    a = book.get_metadata("DC", "creator")
    return a[0][0] if a else ""


def convert_epub_to_pdf_weasyprint(epub_path, pdf_path):
    book = epub.read_epub(epub_path)

    # 1) Extract entire EPUB into a temp folder
    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        _write_epub_to_tempdir(book, tmp_root)

        # 2) Build a single master HTML (respect spine order), page break per chapter
        title = _title_from_meta(book)
        author = _creator_from_meta(book)

        # Collect all CSS files seen in EPUB to link them
        css_links = []
        for css_item in book.get_items_of_type(ebooklib.ITEM_STYLE):
            css_links.append(f'<link rel="stylesheet" href="{css_item.get_name()}">')

        # Title page
        parts = [
            "<!doctype html>",
            "<html><head>",
            '<meta charset="utf-8">',
            *css_links,
            "<style>@page { size: A4; margin: 1in; }"
            "section.chapter { break-before: page; }"
            "section.chapter:first-of-type { break-before: auto; }</style>",
            "</head><body>",
        ]
        if title or author:
            parts.append("<section>")
            if title:
                parts.append(f"<h1>{title}</h1>")
            if author:
                parts.append(f"<h3>by {author}</h3>")
            parts.append("</section>")

        # Chapters
        first = True
        for chap in _iter_chapters_in_reading_order(book):
            # Use full XHTML so we keep per-chapter structures, then strip to <body> contents
            raw = chap.get_content()
            soup = BeautifulSoup(raw, "html.parser")
            soup = _rewrite_relative_urls(chap, soup)

            # Prefer chapter title if present, else use item title attr
            heading = ""
            if soup.title and soup.title.string:
                heading = soup.title.string.strip()
            elif getattr(chap, "title", None):
                heading = str(chap.title).strip()

            body = soup.body or soup  # fallback
            chapter_html = body.decode_contents()

            # Wrap with a section and optional heading; add page break except on first
            cls = "chapter"  # CSS ensures break-before except first
            parts.append(f'<section class="{cls}">')
            if heading:
                parts.append(f"<h1>{heading}</h1>")
            parts.append(chapter_html)
            parts.append("</section>")
            first = False

        parts.append("</body></html>")
        master_html = "\n".join(parts)

        # 3) Render to PDF with WeasyPrint, base_url ensures resources resolve from tmp_root
        HTML(string=master_html, base_url=str(tmp_root)).write_pdf(pdf_path)


if __name__ == "__main__":
    epub_input = input("Enter the path to the EPUB file: ")
    pdf_output = input("Enter the path for the output PDF file: ")
    convert_epub_to_pdf_weasyprint(epub_input, pdf_output)
