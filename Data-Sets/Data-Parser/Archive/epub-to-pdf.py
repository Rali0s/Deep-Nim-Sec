import io
import os
import posixpath
from urllib.parse import urljoin

import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup  # pip install beautifulsoup4
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas


PAGE_SIZE = LETTER
MARGIN = 72  # 1 inch
LINE_SPACING = 14
FONT_NAME = "Helvetica"
FONT_SIZE = 11
H1_SIZE = 18
H2_SIZE = 14
H3_SIZE = 12


def _wrap_text(c, text, max_width):
    """Wrap text to fit within max_width using current font on canvas."""
    if not text:
        return []
    words = text.split()
    lines, line = [], []
    space_w = pdfmetrics.stringWidth(" ", c._fontname, c._fontsize)
    cur_w = 0.0
    for w in words:
        w_w = pdfmetrics.stringWidth(w, c._fontname, c._fontsize)
        if line and (cur_w + space_w + w_w) > max_width:
            lines.append(" ".join(line))
            line = [w]
            cur_w = w_w
        else:
            if line:
                cur_w += space_w + w_w
                line.append(w)
            else:
                line = [w]
                cur_w = w_w
    if line:
        lines.append(" ".join(line))
    return lines


def _draw_paragraph(c, text, x, y, max_width):
    """Draw a paragraph (wrapping). Return new y."""
    for line in _wrap_text(c, text, max_width):
        if y < MARGIN + LINE_SPACING:
            c.showPage()
            _set_default_font(c)
            y = PAGE_SIZE[1] - MARGIN
        c.drawString(x, y, line)
        y -= LINE_SPACING
    return y


def _set_default_font(c):
    c.setFont(FONT_NAME, FONT_SIZE)


def _chapter_base_href(item):
    # Items use POSIX-style paths inside EPUB.
    return item.get_name()  # e.g., "Text/chapter01.xhtml"


def _resolve_item_href(chapter_item, asset_href):
    """Resolve a relative asset href (e.g., image) against the chapter's base href."""
    base = _chapter_base_href(chapter_item)
    base_dir = posixpath.dirname(base)
    joined = posixpath.normpath(posixpath.join(base_dir, asset_href))
    return joined


def _get_image_item(book, href):
    try:
        return book.get_item_with_href(href)
    except Exception:
        return None


def _draw_image(c, img_bytes, x, y, max_width):
    """Draw an image that fits within max_width, respecting aspect ratio.
    Returns updated y (with some padding)."""
    if y < MARGIN + 150:  # crude space check; new page if too low
        c.showPage()
        _set_default_font(c)
        y = PAGE_SIZE[1] - MARGIN

    image = ImageReader(io.BytesIO(img_bytes))
    iw, ih = image.getSize()
    # target width: up to max_width
    scale = min(max_width / float(iw), 1.0)
    tw = iw * scale
    th = ih * scale

    c.drawImage(image, x, y - th, width=tw, height=th, preserveAspectRatio=True, mask='auto')
    return y - th - LINE_SPACING


def _render_html_item_to_pdf(c, book, chapter_item, x, y, max_width):
    """Parse simple HTML content and render as text + images."""
    body_bytes = chapter_item.get_body_content()  # bytes
    soup = BeautifulSoup(body_bytes, "html.parser")

    # Keep a simple block order: headers, paragraphs, lists, images, hr
    for el in soup.find_all(["h1", "h2", "h3", "p", "li", "img", "hr"]):
        tag = el.name

        if tag in ("h1", "h2", "h3"):
            # spacing
            if y < MARGIN + 2 * LINE_SPACING:
                c.showPage()
                _set_default_font(c)
                y = PAGE_SIZE[1] - MARGIN
            # header font
            size = H1_SIZE if tag == "h1" else H2_SIZE if tag == "h2" else H3_SIZE
            c.setFont(FONT_NAME, size)
            y -= LINE_SPACING
            txt = el.get_text(" ", strip=True)
            y = _draw_paragraph(c, txt, x, y, max_width)
            c.setFont(FONT_NAME, FONT_SIZE)
            y -= LINE_SPACING // 2

        elif tag == "p":
            txt = el.get_text(" ", strip=True)
            if txt:
                y = _draw_paragraph(c, txt, x, y, max_width)
                y -= LINE_SPACING // 2

        elif tag == "li":
            txt = "• " + el.get_text(" ", strip=True)
            y = _draw_paragraph(c, txt, x, y, max_width)

        elif tag == "img":
            src = el.get("src")
            if src:
                resolved = _resolve_item_href(chapter_item, src)
                img_item = _get_image_item(book, resolved)
                if img_item:
                    y = _draw_image(c, img_item.get_content(), x, y, max_width)

        elif tag == "hr":
            # draw a simple rule
            if y < MARGIN + LINE_SPACING:
                c.showPage()
                _set_default_font(c)
                y = PAGE_SIZE[1] - MARGIN
            c.line(x, y, x + max_width, y)
            y -= LINE_SPACING

    return y


def _title_from_meta(book):
    t = book.get_metadata("DC", "title")
    return t[0][0] if t else ""


def _creator_from_meta(book):
    a = book.get_metadata("DC", "creator")
    return a[0][0] if a else ""


def _ordered_spine_ids(book):
    """
    Return a list of (idref, linear_flag) in spine order.
    Some items in the spine can be 'non-linear'; we include them but you could skip if desired.
    """
    # EbookLib exposes spine on the book as a list of either ids or item objects,
    # but reading order should follow the spine entries.
    # Normalize to idrefs.
    spine = getattr(book, "spine", [])
    idrefs = []
    for entry in spine:
        if isinstance(entry, tuple):
            # sometimes stored as (idref, attrs_dict) depending on version
            idref, _attrs = entry[0], entry[1] if len(entry) > 1 else {}
            idrefs.append(idref)
        else:
            # 'nav' or id string or EpubHtml object
            if hasattr(entry, "get_id"):
                idrefs.append(entry.get_id())
            else:
                idrefs.append(str(entry))
    return idrefs


def _iter_chapters_in_reading_order(book):
    """
    Yield EpubHtml items in spine order; fall back to ITEM_DOCUMENT order if spine is missing.
    """
    idrefs = _ordered_spine_ids(book)
    if idrefs:
        seen = set()
        for idref in idrefs:
            # typical values: 'nav' (skip), or chapter id
            try:
                item = book.get_item_with_id(idref)
            except Exception:
                item = None
            if item and item.get_type() == ebooklib.ITEM_DOCUMENT and idref not in seen:
                seen.add(idref)
                yield item
        # include any docs not referenced in spine (edge cases)
        for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
            if item.get_id() not in seen:
                yield item
    else:
        for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
            yield item


def convert_epub_to_pdf(epub_path, pdf_path):
    book = epub.read_epub(epub_path)

    c = canvas.Canvas(pdf_path, pagesize=PAGE_SIZE)
    _set_default_font(c)
    x = MARGIN
    y = PAGE_SIZE[1] - MARGIN
    max_width = PAGE_SIZE[0] - 2 * MARGIN

    # Simple title page from metadata
    title = _title_from_meta(book)
    author = _creator_from_meta(book)
    if title or author:
        c.setFont(FONT_NAME, 20)
        if title:
            y = _draw_paragraph(c, title, x, y, max_width)
        if author:
            c.setFont(FONT_NAME, 14)
            y -= LINE_SPACING
            y = _draw_paragraph(c, f"by {author}", x, y, max_width)
        c.showPage()
        _set_default_font(c)
        y = PAGE_SIZE[1] - MARGIN

    # Chapters in spine order
    for chap in _iter_chapters_in_reading_order(book):
        # Chapter heading
        heading = (getattr(chap, "title", None) or "").strip()
        if heading:
            c.setFont(FONT_NAME, H1_SIZE)
            y = _draw_paragraph(c, heading, x, y, max_width)
            c.setFont(FONT_NAME, FONT_SIZE)
            y -= LINE_SPACING

        y = _render_html_item_to_pdf(c, book, chap, x, y, max_width)

        # spacing between chapters
        y -= LINE_SPACING
        if y < MARGIN + 3 * LINE_SPACING:
            c.showPage()
            _set_default_font(c)
            y = PAGE_SIZE[1] - MARGIN

    c.save()


if __name__ == "__main__":
    epub_input = input("Enter the path to the EPUB file: ")
    pdf_output = input("Enter the path for the output PDF file: ")
    convert_epub_to_pdf(epub_input, pdf_output)
