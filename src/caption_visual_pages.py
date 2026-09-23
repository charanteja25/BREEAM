#!/usr/bin/env python3
"""
Dispatches each flagged page to the right reader based on why it was
flagged: route maps get structured map reading, flow diagrams get
structured diagram reading, everything else gets a general description.
Appends to existing page text rather than overwriting. Skips pages
already processed, so a rate-limit failure partway through never
costs you the work already done.

Usage:
    python src/caption_visual_pages.py data/ingested/<file>.json
"""
import sys
import json
import time
import base64
from pathlib import Path
import litellm
from llm_client import CHAT_MODEL
from read_map import read_map, to_chunk_text as map_chunk_text
from read_flow_diagram import read_flow_diagram, to_chunk_text as flow_chunk_text

CAPTION_PROMPT = """This is a page from a BREEAM evidence document. Cover all that apply:

1. DESCRIPTION: What kind of visual is this (site plan, map, screenshot, diagram, photo, chart)?

2. HIGHLIGHTED OR SHADED AREAS: If any region is highlighted, shaded, circled, or boundary-marked
   (e.g. a radius, a zone, a coverage area), describe: what the highlighted area represents, its
   approximate extent or boundary (distance, radius, named streets/landmarks if visible), what is
   inside it, and any legend or color-key explaining what the shading means.

3. ANNOTATIONS AND TEXT (verbatim): Transcribe EVERY piece of text visible on the image exactly as
   written — handwritten notes, callout boxes, comment bubbles, revision clouds, labels, captions,
   legends, numbers, dates, or text in any table/form shown. Quote exactly, do not paraphrase.
   If none, say "No visible text annotations."

Be factual only. Do not infer meaning beyond what is literally shown or written. If a section
doesn't apply to this image, say so briefly rather than omitting it."""

def general_caption(image_path):
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    response = litellm.completion(
        model=CHAT_MODEL,
        num_retries=5,
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": CAPTION_PROMPT},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
            ],
        }],
    )
    return response.choices[0].message.content

def process(ingested_path):
    with open(ingested_path) as f:
        doc = json.load(f)

    updated = 0
    skipped = 0
    for page in doc["pages"]:
        if not (page.get("needs_visual_review") and page.get("image_path")):
            continue

        if page.get("visual_processed"):
            skipped += 1
            continue

        reason = page.get("flagged_reason")
        print(f"  page {page['page']} ({page['image_path']}) — reason: {reason}")

        if reason == "has_images":
            structured = read_map(page["image_path"])
            caption = map_chunk_text(structured)
            page["map_data"] = structured
        elif reason == "complex_drawing":
            structured = read_flow_diagram(page["image_path"])
            caption = flow_chunk_text(structured)
            page["flow_diagram_data"] = structured
        else:
            caption = general_caption(page["image_path"])

        existing_text = page["text"].strip()
        if existing_text:
            page["text"] = existing_text + "\n\n--- VISUAL CONTENT ON THIS PAGE ---\n" + caption
        else:
            page["text"] = caption

        page["visual_processed"] = True
        updated += 1

        # save after every page, so progress survives a crash/interrupt
        Path(ingested_path).write_text(json.dumps(doc, indent=2))
        time.sleep(1)

    print(f"Processed {updated} visual page(s), skipped {skipped} already done. Updated: {ingested_path}")

if __name__ == "__main__":
    process(sys.argv[1])