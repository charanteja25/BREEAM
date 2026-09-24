#!/usr/bin/env python3
"""
Sanity-checks every structured JSON in data/manual/ for the problems
we've already hit once: empty criteria lists, gaps in criteria numbering,
unbound table captions, leftover boilerplate, and marker/table mismatches.

Usage:
    uv run python src/sanity_check.py
"""
import json
import re
from pathlib import Path

# Only flags the header/footer when it appears as its OWN line (the running
# header/footer), not as a substring of a real sentence (e.g. '...within
# BREEAM UK New Construction.' is legitimate credit text).
BOILERPLATE_LINE_RE = re.compile(
    r'^(BREEAM UK New Construction|Technical Manual - .+ - SD\d+)$'
)


def check_file(path):
    issues = []
    data = json.loads(path.read_text())

    for credit in data:
        code = credit.get("code") or credit.get("title") or "?"

        # 1. Boilerplate leftover
        for line in credit["raw_text"].split("\n"):
            if BOILERPLATE_LINE_RE.match(line.strip()):
                issues.append(f"{code}: boilerplate leftover ({line.strip()!r})")

        # 2. Table markers match the tables list exactly, in order
        markers = re.findall(r"\[TABLE ([^\]]+)\]", credit["raw_text"])
        table_ids = [t["id"] for t in credit["tables"]]
        if markers != table_ids:
            issues.append(f"{code}: markers {markers} != tables {table_ids}")

        # 3. Every table has rows
        for t in credit["tables"]:
            if not t["rows"]:
                issues.append(f"{code}: table {t['id']} has no rows")

        ac = next((s for s in credit["subsections"] if s["heading"] == "Assessment criteria"), None)
        if ac is None:
            continue

        # 4. Assessment criteria section exists but produced no criteria,
        #    even though the raw text clearly has numbered items in it
        if not ac["criteria"] and re.search(r"(?m)^\d+[\s.]", ac["text"]):
            issues.append(f"{code}: Assessment criteria has text but 0 parsed criteria")

        # 5. Every "Table X.Y" caption mentioned in this credit's text is
        #    actually bound to one of its tables
        mentioned = set(re.findall(r"Table\s+(\d+\.\d+)", credit["raw_text"]))
        bound = set()
        for t in credit["tables"]:
            if t["caption"]:
                m = re.search(r"Table\s+(\d+\.\d+)", t["caption"])
                if m:
                    bound.add(m.group(1))
        unbound = mentioned - bound
        if unbound:
            issues.append(f"{code}: tables mentioned but not bound: {sorted(unbound)}")

        # 6. Criteria numbering has no gaps (e.g. 1, 2, 4 -- missing 3)
        ids = [c["id"] for c in ac["criteria"]]
        top_level = [int(i.split(".")[0]) for i in ids if "." not in i]
        for a, b in zip(top_level, top_level[1:]):
            if b != a + 1:
                issues.append(f"{code}: top-level criteria jump {a} -> {b}")

    return issues


def main():
    manual_dir = Path("data/manual")
    files = sorted(manual_dir.glob("*_structured.json"))
    if not files:
        print("No *_structured.json files found in data/manual/")
        return

    total_issues = 0
    for path in files:
        issues = check_file(path)
        status = "OK" if not issues else f"{len(issues)} issue(s)"
        print(f"\n{path.name}: {status}")
        for issue in issues:
            print(f"  - {issue}")
        total_issues += len(issues)

    print(f"\n{'='*50}")
    print(f"{len(files)} files checked, {total_issues} total issues")


if __name__ == "__main__":
    main()
