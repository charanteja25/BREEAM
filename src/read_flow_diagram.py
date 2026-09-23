#!/usr/bin/env python3
"""
Reads a traffic flow diagram (junction layout with turning-movement
arrows and allocation data) and returns structured JSON.

Usage:
    python src/read_flow_diagram.py data/page_images/some_page.png
"""
import sys
import re
import json
import base64
import litellm
from llm_client import CHAT_MODEL

PROMPT = """Read this traffic flow diagram. Return ONLY JSON, no other text:
{
  "diagram_title": "e.g. Master flow diagram",
  "junctions": ["every named junction/road label visible"],
  "site_reference": "the label marking the development site, if shown",
  "movements": [
    {
      "junction": "which junction/road this applies to",
      "direction": "e.g. left turn, right turn, straight ahead — from the arrow",
      "time_period": "e.g. AM peak, PM peak — if distinguishable, else null",
      "value": "the number or percentage shown, copied exactly",
      "unit": "% or vehicles/count or unclear"
    }
  ],
  "unreadable": ["anything you could not read clearly, e.g. small numbers in tables"]
}
Rules: copy every number exactly as printed, do not calculate or round. If a table's numbers are
too small/blurry to read confidently, list them in "unreadable" rather than guessing."""

def read_flow_diagram(image_path):
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()

    response = litellm.completion(
        model=CHAT_MODEL,
        num_retries=5,
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": PROMPT},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
            ],
        }],
    )
    text = response.choices[0].message.content
    text = re.sub(r"^```(json)?|```$", "", text.strip(), flags=re.M).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        sys.exit(f"Model did not return valid JSON:\n{text}")

def to_chunk_text(data):
    movements = "; ".join(
        f"{m.get('junction')}: {m.get('direction')} = {m.get('value')}{m.get('unit') or ''}"
        + (f" ({m['time_period']})" if m.get("time_period") else "")
        for m in data.get("movements", [])
    )
    return (
        f"[Figure: {data.get('diagram_title')}]\n"
        f"Junctions: {', '.join(data.get('junctions', []))}.\n"
        f"Site reference: {data.get('site_reference')}.\n"
        f"Movements: {movements}."
    )

if __name__ == "__main__":
    result = read_flow_diagram(sys.argv[1])
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print("\n--- chunk text ---")
    print(to_chunk_text(result))