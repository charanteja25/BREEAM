#!/usr/bin/env python3
"""
Reads a client evidence PDF page-by-page: strips header/footer, keeps the
real page number, extracts tables, and flags pages that need a human to
look at them (low text, real images, or a genuine diagram -- not just a
table's grid lines).

Usage:
    uv run python src/ingest_client.py test-docs/<file>.pdf
Output:
    data/ingested/<file>.json
"""
import sys
import re
import json
from pathlib import Path
import pymupdf

HEADER_BOTTOM = 70    # header text sits above this y
FOOTER_TOP = 790       # footer (file path + page no.) sits below this y

TEXT_DENSITY_THRESHOLD = 40
MIN_TOTAL_IMAGE_AREA = 20000
MIN_VECTOR_DRAWINGS = 50


CAPTION_RE = re.compile(r"^Table\s+[\d.]+\s*[\u2013-]")


def read_page(page):
    """Returns (page_number, body_text, positioned_blocks). positioned_blocks
    keeps each body block's y0 alongside its text, so a table's caption
    (the 'Table X.Y - ...' line right before it) can be found later."""
    body_blocks, footer_text = [], ""
    for x0, y0, x1, y1, text, *_ in page.get_text("blocks", sort=True):
        if y0 >= FOOTER_TOP:
            if text.strip():          # don't let an empty block overwrite a real one
                footer_text = text
        elif y1 <= HEADER_BOTTOM:
            continue   # drop running header
        else:
            body_blocks.append((y0, text))

    page_number = None
    if footer_text.strip():
        page_number = footer_text.strip().splitlines()[-1].strip()

    text = "\n".join(t for _, t in body_blocks)
    return page_number, text, body_blocks


def find_caption(positioned_blocks, table_bbox):
    """The nearest 'Table X.Y - ...' block directly above the table."""
    above = [(y0, t) for y0, t in positioned_blocks if y0 < table_bbox[1] and t.strip()]
    if not above:
        return None
    y0, t = max(above, key=lambda bt: bt[0])
    first_line = t.strip().splitlines()[0].strip()
    return " ".join(first_line.split()) if CAPTION_RE.match(first_line) else None


def inside(bbox, table_bbox, min_overlap=0.5):
    bx0, by0, bx1, by1 = bbox
    tx0, ty0, tx1, ty1 = table_bbox
    ix = max(0, min(bx1, tx1) - max(bx0, tx0))
    iy = max(0, min(by1, ty1) - max(by0, ty0))
    area = max((bx1 - bx0) * (by1 - by0), 1e-6)
    return ix * iy / area >= min_overlap


def page_has_significant_images(page):
    images = page.get_images(full=True)
    if len(images) < 3:
        return False
    total_area = sum(
        rect.width * rect.height
        for img in images
        for rect in page.get_image_rects(img[0])
    )
    return total_area >= MIN_TOTAL_IMAGE_AREA



def ingest(pdf_path):
    doc = pymupdf.open(pdf_path)
    image_dir = Path("data/page_images")
    image_dir.mkdir(parents=True, exist_ok=True)

    pages = []
    for i, page in enumerate(doc):
        page_number, text, positioned_blocks = read_page(page)

        tables = page.find_tables()
        real_tables = [t for t in tables.tables if t.bbox[1] < FOOTER_TOP and t.bbox[3] > HEADER_BOTTOM]
        table_data = [
            {"caption": find_caption(positioned_blocks, t.bbox), "rows": t.extract()}
            for t in real_tables
        ]

        low_text_density = len(text.strip()) < TEXT_DENSITY_THRESHOLD
        has_images = page_has_significant_images(page)
        needs_visual_review = low_text_density or has_images
        
        flagged_reason = "low_text" if low_text_density else ("has_images" if has_images else None)
    
        image_path = None
        if needs_visual_review:
            pix = page.get_pixmap(dpi=150)
            image_path = str(image_dir / f"{Path(pdf_path).stem}_p{i + 1}.png")
            pix.save(image_path)

        # a placeholder in the text so embedding/matching sees SOMETHING is
        # there, without the actual picture -- image_summary gets filled in
        # later, once a vision model has looked at image_path
        if image_path:
            text = text + "\n[IMAGE: " + Path(image_path).name + " -- summary pending]"

        pages.append({
            "pdf_page_index": i + 1,   # raw position in the PDF
            "page_number": page_number,  # the document's own printed page number
            "text": text,
            "tables": table_data,
            "needs_visual_review": needs_visual_review,
            "flagged_reason": flagged_reason,
            "image_path": image_path,
            "image_summary": None,   # filled in later by a vision model
        })

    return {"file": Path(pdf_path).name, "pages": pages}


if __name__ == "__main__":
    result = ingest(sys.argv[1])
    out_path = Path("data/ingested") / (Path(sys.argv[1]).stem + ".json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2))
    flagged = sum(1 for p in result["pages"] if p["needs_visual_review"])
    reasons = {}
    for p in result["pages"]:
        r = p.get("flagged_reason")
        if r:
            reasons[r] = reasons.get(r, 0) + 1
    print(f"Ingested {len(result['pages'])} pages from {result['file']}")
    print(f"{flagged} page(s) flagged: {reasons}")
    print(f"Wrote: {out_path}")