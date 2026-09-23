#!/usr/bin/env python3
"""
Usage:
    python src/filter_toc_pages.py <page_index.json>
"""
import sys
import re
import json
from pathlib import Path

DOT_LEADER_PATTERN = re.compile(r'\.{4,}\s*\d+')
MIN_MATCHES_TO_FLAG = 5

def filter_toc(index_path):
    with open(index_path) as f:
        entries = json.load(f)

    kept, removed = [], []
    for entry in entries:
        matches = len(DOT_LEADER_PATTERN.findall(entry["text"]))
        if matches >= MIN_MATCHES_TO_FLAG:
            removed.append((entry.get("page", "?"), matches))
        else:
            kept.append(entry)

    print(f"Removed {len(removed)} likely ToC/list page(s):")
    for page, matches in removed:
        print(f"  page {page}: {matches} dot-leader matches")
    print(f"Kept {len(kept)} of {len(entries)} pages")

    out_path = Path(index_path).with_name(Path(index_path).stem + "_filtered.json")
    out_path.write_text(json.dumps(kept, indent=2))
    print(f"Wrote: {out_path}")

if __name__ == "__main__":
    filter_toc(sys.argv[1])