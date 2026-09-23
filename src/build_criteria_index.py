#!/usr/bin/env python3

import sys
import json
from pathlib import Path
from llm_client import embed

MAX_CHARS = 20000  # conservative guard, well under the embedding model's token limit

def load_pages(ingested_path):
    with open(ingested_path) as f:
        doc = json.load(f)
    return {p["page"]: p["text"] for p in doc["pages"]}, doc["file"]

def section_text(pages_by_local_num, local_start, local_end):
    chunks = []
    for local_page in range(local_start, local_end + 1):
        text = pages_by_local_num.get(local_page, "").strip()
        if text:
            chunks.append(text)
    return "\n\n".join(chunks)

def split_if_too_large(name, manual_start, manual_end, local_start, local_end, pages_by_local_num):
    text = section_text(pages_by_local_num, local_start, local_end)
    if len(text) <= MAX_CHARS or local_start == local_end:
        return [{
            "name": name,
            "manual_page_range": f"{manual_start}-{manual_end}",
            "local_page_range": f"{local_start}-{local_end}",
            "text": text,
        }]
    # too large: split the page range roughly in half and recurse
    mid_local = (local_start + local_end) // 2
    mid_manual = manual_start + (mid_local - local_start)
    first = split_if_too_large(f"{name} (part 1)", manual_start, mid_manual, local_start, mid_local, pages_by_local_num)
    second = split_if_too_large(f"{name} (part 2)", mid_manual + 1, manual_end, mid_local + 1, local_end, pages_by_local_num)
    return first + second

def build_index(boundaries_path):
    with open(boundaries_path) as f:
        config = json.load(f)

    pages_by_local_num, source_file = load_pages(config["source_ingested_file"])
    chapter_start = config["chapter_start_manual_page"]

    all_chunks = []
    for section in config["sections"]:
        local_start = section["manual_start"] - chapter_start + 1
        local_end = section["manual_end"] - chapter_start + 1
        pieces = split_if_too_large(
            section["name"], section["manual_start"], section["manual_end"],
            local_start, local_end, pages_by_local_num
        )
        all_chunks.extend(pieces)

    for chunk in all_chunks:
        print(f"  embedding: {chunk['name']} (manual p.{chunk['manual_page_range']}, {len(chunk['text'])} chars)")
        chunk["embedding"] = embed(chunk["text"])
        chunk["source_file"] = source_file

    out_name = Path(config["source_ingested_file"]).stem + "_section_index.json"
    out_path = Path("data") / out_name
    out_path.write_text(json.dumps(all_chunks, indent=2))
    print(f"\nIndexed {len(all_chunks)} sections")
    print(f"Wrote: {out_path}")

if __name__ == "__main__":
    build_index(sys.argv[1])