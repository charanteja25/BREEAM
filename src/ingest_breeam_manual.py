#!/usr/bin/env python3
"""
Reads one BREEAM manual chapter PDF and writes a structured JSON:
credits -> subsections -> numbered criteria, with tables pulled out
(and stitched across pages), cross-references, and a normalized copy
of the text for matching.

Usage:
    uv run python src/ingest_breeam_manual.py ../BREEAM/breeam_sections/16_Transport.pdf
Output:
    data/manual/<chapter>_structured.json
"""
import sys
import re
import json
from pathlib import Path
import pymupdf

# ---------------------------------------------------------------- page layout
HEADER_BOTTOM = 55      # running header sits above this y (pt)
FOOTER_TOP = 775        # footer ("Technical Manual ...", "Page N of 421") below this y
TABLE_INDENT = 112      # body text starts at x≈107; table content is indented to x≥116

CREDIT_RE = re.compile(r'^((?:Tra|Man|Hea|Ene|Wat|Mat|Wst|LE|Pol|Inn)\s?\d{2})\s+(.+)$')
PAGE_NO_RE = re.compile(r'Page\s+(\d+)\s+of\s+\d+')

KNOWN_HEADINGS = [
    "Aim", "Value", "Context", "Assessment scope", "Specific notes",
    "Assessment criteria", "Methodology", "Evidence", "Definitions",
    "Additional information",
]


def read_page(page, page_index):
    """Returns the page's manual page number, credit label, tables, and
    body blocks (header/footer removed, table text replaced by a marker)."""
    header_lines, footer_text, body_blocks = [], "", []
    for x0, y0, x1, y1, text, *_ in page.get_text("blocks", sort=True):
        if y1 <= HEADER_BOTTOM:
            header_lines += [l.strip() for l in text.splitlines() if l.strip()]
        elif y0 >= FOOTER_TOP:
            footer_text += text
        else:
            body_blocks.append((x0, y0, x1, y1, text))

    m = PAGE_NO_RE.search(footer_text)
    manual_page = int(m.group(1)) if m else None

    # Running header = "BREEAM UK New Construction" + credit title (or category name)
    label = next((l for l in header_lines if l != "BREEAM UK New Construction"), None)

    tables = []
    for j, t in enumerate(page.find_tables().tables):
        tables.append({
            "id": f"L{page_index + 1}_T{j + 1}",
            "manual_page": manual_page,
            "bbox": tuple(round(v, 1) for v in t.bbox),
            "col_count": t.col_count,
            "rows": t.extract(),
            "caption": None,
        })

    # Captioned tables that find_tables() missed (e.g. Table 7.1): everything
    # indented under a "Table X.Y" caption, up to the first block back at the
    # body-text margin, becomes a table with one row per line.
    free = [b for b in body_blocks if not any(inside(b[:4], t["bbox"]) for t in tables)]
    for k, cap in enumerate(free):
        if not re.match(r'^Table\s+\d+\.\d+\s', cap[4].strip()):
            continue
        if any(0 <= t["bbox"][1] - cap[3] < 20 for t in tables):
            continue                      # a real table already sits under this caption
        body = []
        for b in free[k + 1:]:
            if b[0] < TABLE_INDENT:       # back at the body-text margin -> table ended
                break
            body.append(b)
        if not body:
            continue                      # a sentence starting "Table X.Y ...", not a caption
        tables.append({
            "id": f"L{page_index + 1}_T{len(tables) + 1}",
            "manual_page": manual_page,
            "bbox": (round(min(b[0] for b in body), 1), round(min(b[1] for b in body), 1),
                     round(max(b[2] for b in body), 1), round(max(b[3] for b in body), 1)),
            "col_count": 1,
            "rows": [[l.strip()] for b in body for l in b[4].splitlines() if l.strip()],
            "caption": None,
            "source": "list",
        })
    tables.sort(key=lambda t: t["bbox"][1])   # keep top-to-bottom order for stitching

    # Drop body blocks that sit inside a table; put one marker per table instead
    items = []
    for x0, y0, x1, y1, text in body_blocks:
        if any(inside((x0, y0, x1, y1), t["bbox"]) for t in tables):
            continue
        items.append((y0, x0, text.strip()))
    for t in tables:
        items.append((t["bbox"][1], t["bbox"][0], f"[TABLE {t['id']}]"))
    items.sort(key=lambda it: (it[0], it[1]))
    lines = [it[2] for it in items if it[2]]

    # Caption = a "Table X.Y ..." line immediately before the marker
    for t in tables:
        k = lines.index(f"[TABLE {t['id']}]")
        if k > 0 and re.match(r'^Table\s+\d+\.\d+\s', lines[k - 1]):
            t["caption"] = " ".join(lines[k - 1].split())

    return {"manual_page": manual_page, "label": label, "tables": tables, "lines": lines}


def inside(block, table_bbox, min_overlap=0.5):
    """True if at least half of the block's area lies within the table."""
    bx0, by0, bx1, by1 = block
    tx0, ty0, tx1, ty1 = table_bbox
    ix = max(0, min(bx1, tx1) - max(bx0, tx0))
    iy = max(0, min(by1, ty1) - max(by0, ty0))
    area = max((bx1 - bx0) * (by1 - by0), 1e-6)
    return ix * iy / area >= min_overlap


# ---------------------------------------------------- continuation tables
TOP_MAX = 100        # a continuation starts right under the running header
BOTTOM_GAP = 110     # the table it continues ends within this many pt of the page bottom


def stitch_continuations(tables, page_height):
    """Merges tables that run onto the next page into the table they continue.
    Returns (stitched_tables, alias) where alias maps each absorbed table id
    to the id of the table it was merged into."""
    stitched = []
    alias = {}
    for t in tables:
        prev = stitched[-1] if stitched else None
        is_continuation = (
            prev is not None
            and t["manual_page"] == prev["last_page"] + 1
            and prev["last_bbox"][3] >= page_height - BOTTOM_GAP
            and t["bbox"][1] <= TOP_MAX
            and t["col_count"] == prev["col_count"]
            and t is first_on_page(tables, t)
        )
        if is_continuation:
            rows = t["rows"]
            if rows and rows[0] == prev["rows"][0]:   # repeated header row
                rows = rows[1:]
            if rows and is_split_row(rows[0]):        # row broken by the page break
                merge_into(prev["rows"][-1], rows[0])
                prev["split_rows_merged"] = prev.get("split_rows_merged", 0) + 1
                rows = rows[1:]
            prev["rows"].extend(rows)
            prev["pages"].append(t["manual_page"])
            prev["last_page"] = t["manual_page"]
            prev["last_bbox"] = t["bbox"]
            alias[t["id"]] = prev["id"]
        else:
            new = dict(t, rows=list(t["rows"]), pages=[t["manual_page"]],
                       last_page=t["manual_page"], last_bbox=t["bbox"])
            stitched.append(new)
    for s in stitched:
        s.pop("last_page")
        s.pop("last_bbox")
        s.pop("manual_page")
    return stitched, alias


def is_split_row(row):
    """A row whose first cell is empty but which still has text elsewhere is
    the tail of the previous page's last row."""
    return not (row[0] or "").strip() and any((c or "").strip() for c in row[1:])


def merge_into(target, tail):
    """Appends each tail cell's text to the same column of the target row."""
    for i, cell in enumerate(tail):
        cell = (cell or "").strip()
        if cell:
            target[i] = f"{target[i]}\n{cell}" if (target[i] or "").strip() else cell


def first_on_page(tables, t):
    return next(x for x in tables if x["manual_page"] == t["manual_page"])


# ------------------------------------------------------------ credit grouping
def group_into_credits(pages):
    """Consecutive pages with the same running-header label form one credit."""
    credits = []
    for p in pages:
        if credits and credits[-1]["label"] == p["label"]:
            credits[-1]["pages"].append(p)
        else:
            credits.append({"label": p["label"], "pages": [p]})
    return credits


# ---------------------------------------------------------- section parsing
CRIT_NUM_RE = re.compile(r'^(\d+)(?:\.([a-z]))?$')
GROUP_RE = re.compile(r'^(Prerequisite|(?:One|Two|Three|Four|Five|Six|\d+) credits?\b.*)$')


def split_subsections(lines):
    """Splits a credit's lines at the known headings."""
    subsections, current = [], {"heading": None, "lines": []}
    for line in lines:
        if line in KNOWN_HEADINGS:
            if current["heading"] or current["lines"]:
                subsections.append(current)
            current = {"heading": line, "lines": []}
        else:
            current["lines"].append(line)
    subsections.append(current)
    return subsections


def next_expected(prev):
    """Criterion ids allowed to follow `prev` (e.g. after '2' -> '2.a' or '3')."""
    if prev is None:
        return {"1"}
    num, letter = (prev.split(".") + [None])[:2]
    allowed = {str(int(num) + 1)}
    allowed.add(f"{num}.{chr(ord(letter) + 1)}" if letter else f"{num}.a")
    return allowed


def split_criteria(lines):
    """Splits Assessment criteria into numbered criteria. A bare number line
    only starts a new criterion if it is the next one in sequence, so stray
    numbers (table cells, points) are not mistaken for criteria."""
    criteria, current, group, last_id = [], None, None, None
    for line in lines:
        first = line.split("\n", 1)
        m = CRIT_NUM_RE.match(first[0].strip())
        if m and first[0].strip() in next_expected(last_id):
            last_id = first[0].strip()
            current = {"id": last_id, "group": group, "lines": []}
            criteria.append(current)
            if len(first) > 1:
                current["lines"].append(first[1])
            continue
        if GROUP_RE.match(line.split("\n")[0]):
            group_line, *rest = line.split("\n")
            group = group_line.strip()
            if rest:                      # group label and criterion number in one block
                for c in split_criteria_block(rest, group, last_id):
                    last_id = c["id"]
                    criteria.append(c)
                    current = c
            continue
        if current:
            current["lines"].append(line)
    for c in criteria:
        c["text"] = "\n".join(c.pop("lines")).strip()
    return criteria


def split_criteria_block(rest, group, last_id):
    """Handles a block like 'Two credits – ...\\n1\\nNo later than ...'."""
    out = []
    head = rest[0].strip()
    if head in next_expected(last_id):
        out.append({"id": head, "group": group, "lines": ["\n".join(rest[1:])]})
    return out


def parse_credit(credit, alias):
    label = credit["label"] or ""
    m = CREDIT_RE.match(label)
    code, title = (m.group(1).replace(" ", ""), m.group(2)) if m else (None, label)

    lines = []
    for p in credit["pages"]:
        for line in p["lines"]:
            if line == label:                         # credit/category title repeated in body
                continue
            mk = re.match(r'^\[TABLE (L\d+_T\d+)\]$', line)
            if mk and mk.group(1) in alias:           # continuation marker -> dropped
                continue
            lines.append(line)

    subsections = []
    for s in split_subsections(lines):
        entry = {"heading": s["heading"], "text": "\n".join(s["lines"]).strip(), "criteria": []}
        if s["heading"] == "Assessment criteria":
            entry["criteria"] = split_criteria(s["lines"])
        subsections.append(entry)

    raw_text = "\n".join(lines)
    pages = [p["manual_page"] for p in credit["pages"]]
    return {
        "code": code,
        "title": title,
        "manual_pages": [min(pages), max(pages)],
        "raw_text": raw_text,
        "normalized_text": normalize_for_matching(raw_text),
        "subsections": subsections,
        "tables": [],
        "xrefs": resolve_xrefs(raw_text),
    }


# ------------------------------------------------ cross-refs & normalizing
XREF_PATTERNS = [
    re.compile(r'(?:see\s+)?Table\s+\d+\.\d+', re.IGNORECASE),
    re.compile(r'see\s+Methodology[^.\n]*', re.IGNORECASE),
    re.compile(r'see\s+Definitions[^.\n]*', re.IGNORECASE),
    re.compile(r'(?:Tra|Man|Hea|Ene|Wat|Mat|Wst|LE|Pol)\s?\d{2}\s+[A-Za-z][^.\n]{0,60}'),
    re.compile(r'option\s+\d+', re.IGNORECASE),
    re.compile(r'on\s+page\s+\d+', re.IGNORECASE),
]


def resolve_xrefs(text):
    text = text.replace("\xa0", " ")
    seen, unique = set(), []
    for pattern in XREF_PATTERNS:
        for m in pattern.finditer(text):
            f = m.group(0).strip()
            if f.lower() not in seen:
                seen.add(f.lower())
                unique.append(f)
    return unique


KNOWN_DEHYPHENATION_FIXES = {
    "nonmotorised": "non-motorised",
    "constructionrelated": "construction-related",
    "sitewide": "site-wide",
}


def normalize_for_matching(text):
    """Separate cleaned copy for embedding/matching; raw_text stays the source of truth."""
    n = text.replace("\xa0", " ")
    n = re.sub(r'\bm2\b', "m\u00b2", n)
    n = n.replace("\uf0a7", "\u2022")
    for wrong, right in KNOWN_DEHYPHENATION_FIXES.items():
        n = re.sub(wrong, right, n, flags=re.IGNORECASE)
    n = re.sub(r'[ \t]+', ' ', n)
    return n


# ---------------------------------------------------------------------- main
def build(pdf_path):
    pdf_path = Path(pdf_path)
    doc = pymupdf.open(pdf_path)
    pages = [read_page(page, i) for i, page in enumerate(doc)]

    all_tables = [t for p in pages for t in p["tables"]]
    tables, alias = stitch_continuations(all_tables, doc[0].rect.height)

    results = []
    for credit in group_into_credits(pages):
        print(f"  processing: {credit['label']}")
        results.append(parse_credit(credit, alias))

    # Each (stitched) table belongs to the credit whose page range holds its first page
    for t in tables:
        for r in results:
            if r["manual_pages"][0] <= t["pages"][0] <= r["manual_pages"][1]:
                r["tables"].append(t)
                break

    out_dir = Path("data/manual")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{pdf_path.stem}_structured.json"
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"Wrote: {out_path}")
    return results


if __name__ == "__main__":
    build(sys.argv[1])