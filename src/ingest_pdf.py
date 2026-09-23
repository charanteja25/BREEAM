#!/usr/bin/env python3
import sys
import json
from pathlib import Path
import pymupdf

TEXT_DENSITY_THRESHOLD = 40
MIN_TOTAL_IMAGE_AREA = 20000
MIN_VECTOR_DRAWINGS = 50

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

def page_has_complex_drawing(page):
    return len(page.get_drawings()) >= MIN_VECTOR_DRAWINGS

def ingest(pdf_path):
    doc = pymupdf.open(pdf_path)
    image_dir = Path("data/page_images")
    image_dir.mkdir(parents=True, exist_ok=True)

    pages = []
    for page_num, page in enumerate(doc, start=1):
        text = page.get_text()
        tables = page.find_tables()
        table_data = [t.extract() for t in tables.tables] if tables.tables else []

        low_text_density = len(text.strip()) < TEXT_DENSITY_THRESHOLD
        has_images = page_has_significant_images(page)
        has_diagram = page_has_complex_drawing(page)
        needs_visual_review = low_text_density or has_images or has_diagram

        flagged_reason = None
        if low_text_density:
            flagged_reason = "low_text"
        elif has_images:
            flagged_reason = "has_images"
        elif has_diagram:
            flagged_reason = "complex_drawing"

        image_path = None
        if needs_visual_review:
            pix = page.get_pixmap(dpi=150)
            image_path = str(image_dir / f"{Path(pdf_path).stem}_p{page_num}.png")
            pix.save(image_path)

        pages.append({
            "page": page_num,
            "text": text,
            "tables": table_data,
            "needs_visual_review": needs_visual_review,
            "flagged_reason": flagged_reason,
            "image_path": image_path,
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