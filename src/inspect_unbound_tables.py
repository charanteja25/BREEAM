import sys
import re
import pymupdf

# chapter file -> table numbers whose caption has no detected table
TARGETS = {
    "14_Health_and_Wellbeing.pdf": ["5.4"],
    "15_Energy.pdf": ["6.7"],
    "16_Transport.pdf": ["7.1"],
    "18_Materials.pdf": ["9.13", "9.14"],
    "19_Waste.pdf": ["10.6"],
}
SECTIONS = sys.argv[1]   # folder with the chapter PDFs

for fname, nums in TARGETS.items():
    doc = pymupdf.open(f"{SECTIONS}/{fname}")
    for page in doc:
        blocks = page.get_text("blocks", sort=True)
        for i, b in enumerate(blocks):
            for num in nums:
                if re.match(rf'^Table\s+{re.escape(num)}\s', b[4]):
                    print(f"\n===== {fname}  Table {num}  (PDF page {page.number + 1})")
                    for x0, y0, x1, y1, text, *_ in blocks[i:i + 6]:
                        print(f"  y={y0:.0f}-{y1:.0f} x={x0:.0f} | {text.strip()[:150]!r}")
