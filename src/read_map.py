#!/usr/bin/env python3
"""
Reads a page that may contain MULTIPLE route-map screenshots (e.g. one
per commuter). Returns each map as a separate, individually identifiable
entry, along with its associated post code / mode / junction data table
where one is shown alongside it.

Usage:
    python src/read_map.py data/page_images/some_page.png
"""
import sys
import re
import json
import base64
import litellm
from llm_client import CHAT_MODEL

PROMPT = """This page may contain ONE OR MORE separate map screenshots. Identify each one
individually — do not merge them. Return ONLY JSON, no other text:
{
  "maps": [
    {
      "position_on_page": "e.g. top-left, 2nd from top",
      "map_type": "e.g. Google Maps satellite",
      "location": "city/area, and how you know (labels, postcode)",
      "origin": "start point (hollow circle / first marker)",
      "destination": "end point (red pin)",
      "travel_mode": "from the route icons (car, bike, walk, transit)",
      "routes": [{"distance": "", "time": "", "selected": true, "via": "roads/areas it follows"}],
      "landmarks": ["every readable place label"],
      "associated_data": {
        "post_code": "if a data row/table is shown next to this specific map",
        "mode": "",
        "user_type": "e.g. student, staff",
        "entering_junction_from": ""
      },
      "unreadable": ["anything you could not read for this specific map"]
    }
  ]
}
Rules: one entry per distinct map image, even if they look similar. The darker/bolder route line
in each map is its selected route. Copy numbers exactly as printed. Never guess — put uncertain
items in "unreadable". If a page has only one map, still return it inside the "maps" array."""

def read_map(image_path):
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
        data = json.loads(text)
    except json.JSONDecodeError:
        sys.exit(f"Model did not return valid JSON:\n{text}")

    if "maps" not in data:
        sys.exit(f"Model response missing 'maps' key:\n{json.dumps(data, indent=2)}")
    return data

def to_chunk_text(data):
    blocks = []
    for i, m in enumerate(data.get("maps", []), start=1):
        routes = "; ".join(
            f"{r.get('distance')} / {r.get('time')}"
            + (" (selected)" if r.get("selected") else "")
            + (f" via {r['via']}" if r.get("via") else "")
            for r in m.get("routes", [])
        )
        assoc = m.get("associated_data") or {}
        blocks.append(
            f"[Map {i} of {len(data.get('maps', []))} — {m.get('position_on_page')}]\n"
            f"{m.get('map_type')} - {m.get('location')}\n"
            f"From {m.get('origin')} to {m.get('destination')} by {m.get('travel_mode')}.\n"
            f"Routes: {routes}.\n"
            f"Post code: {assoc.get('post_code')}, mode: {assoc.get('mode')}, "
            f"user type: {assoc.get('user_type')}, entering from: {assoc.get('entering_junction_from')}.\n"
            f"Landmarks: {', '.join(m.get('landmarks', []))}."
        )
    return "\n\n".join(blocks)

if __name__ == "__main__":
    result = read_map(sys.argv[1])
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print("\n--- chunk text ---")
    print(to_chunk_text(result))