#!/usr/bin/env python3
"""
Compares every evidence page against every manual section using cosine
similarity, and prints the top matches per section.

Usage:
    python src/match.py <evidence_index.json>
"""
import sys
import json
import numpy as np

def load_index(path):
    with open(path) as f:
        return json.load(f)

def cosine_sim(a, b):
    a, b = np.array(a), np.array(b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

def main(evidence_path):
    manual = load_index("data/16_Transport_section_index.json")
    evidence = load_index(evidence_path)

    for section in manual:
        scores = [
            (cosine_sim(section["embedding"], page["embedding"]), page["page"])
            for page in evidence
        ]
        scores.sort(reverse=True)
        print(f"\n=== {section['name']} (manual p.{section['manual_page_range']}) ===")
        for score, page_num in scores[:5]:
            print(f"  evidence page {page_num}: similarity {score:.3f}")

if __name__ == "__main__":
    main(sys.argv[1])