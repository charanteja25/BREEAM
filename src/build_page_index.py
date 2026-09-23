#!/usr/bin/env python3
"""
One entry per page. Use for evidence documents (no known section
structure). For the BREEAM manual, use build_criteria_index.py instead.

Usage:
    python src/build_page_index.py data/ingested/<file>.json
"""
import sys
import json
from pathlib import Path
from llm_client import embed

def build_index(ingested_path):
    with open(ingested_path) as f:
        doc = json.load(f)

    entries = []
    for page in doc["pages"]:
        text = page["text"].strip()
        if not text:
            continue
        entries.append({
            "source_file": doc["file"], "page": page["page"],
            "text": text, "embedding": embed(text),
        })
        print(f"  embedded page {page['page']}")

    out_path = Path("data") / (Path(ingested_path).stem + "_index.json")
    out_path.write_text(json.dumps(entries, indent=2))
    print(f"Indexed {len(entries)} pages")
    print(f"Wrote: {out_path}")

if __name__ == "__main__":
    build_index(sys.argv[1])