"""
Pre-Scan Orchestrator — Generates document_intelligence.yaml BEFORE extraction.

Runs 4 analysis passes over the PDF:
  1. Page Classification (cover/table/image/mixed/blank)
  2. Headline Detection (large/bold text = section headers)
  3. Table Detection (column headers + x-ranges)
  4. Font Profiling (catalogs font signatures per data type)

Outputs: _2 Output Data/<doc_id>/document_intelligence.yaml
All extraction engines load this file to skip non-data pages and use
pre-computed column ranges instead of scanning for headers at runtime.
"""
import fitz
import json
import os
import sys
import yaml
import time
import re
from collections import Counter

VAULT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_FOLDER = os.path.join(VAULT_DIR, "_1 INPUT FOLDER")
OUTPUT_FOLDER = os.path.join(VAULT_DIR, "_2 Output Data")
MATRICES_DIR = os.path.join(VAULT_DIR, "Matrices")

# Load parse_request.yaml for column config
with open(os.path.join(MATRICES_DIR, "parse_request.yaml"), 'r', encoding='utf-8') as f:
    PARSE_CONFIG = yaml.safe_load(f)

TARGET_COLS = set(PARSE_CONFIG.get("target_columns", []))
EXCLUDE_COLS = set(PARSE_CONFIG.get("exclude_columns", []))
ALL_KNOWN_HEADERS = TARGET_COLS | EXCLUDE_COLS

# Part number regex for detection
PN_REGEX = None
for t in PARSE_CONFIG.get("extraction_targets", []):
    if t.get("field") == "Part Number":
        PN_REGEX = re.compile(t.get("safeguard_regex", ""))
        break


def extract_rich_spans(page):
    """Extract all text spans WITH font metadata from a PDF page."""
    blocks = page.get_text("dict")["blocks"]
    spans = []

    for block in blocks:
        if "lines" not in block:
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                text = span["text"].strip()
                if text:
                    spans.append({
                        "text": text,
                        "bbox": list(span["bbox"]),  # [x0, y0, x1, y1]
                        "font": span.get("font", ""),
                        "size": round(span.get("size", 0), 1),
                        "flags": span.get("flags", 0),
                        # flags: bit 0=superscript, 1=italic, 4=bold, 5=monospace
                    })

    return spans


def is_bold(flags):
    """Check if font flags indicate bold."""
    return bool(flags & (1 << 4))


def classify_page(spans, page):
    """Classify page type based on content analysis."""
    if not spans:
        return "blank"

    # Count characteristics
    total_spans = len(spans)
    large_text = [s for s in spans if s["size"] >= 14]
    bold_text = [s for s in spans if is_bold(s["flags"])]
    table_headers_found = [s for s in spans if s["text"].upper() in ALL_KNOWN_HEADERS]
    pn_candidates = [s for s in spans if PN_REGEX and PN_REGEX.match(s["text"])]

    # Check for images
    image_list = page.get_images(full=True)
    has_images = len(image_list) > 0

    # Decision tree
    if len(table_headers_found) >= 2 and len(pn_candidates) >= 5:
        return "table"
    elif len(large_text) >= 3 and total_spans < 50:
        return "cover"
    elif has_images and total_spans < 20:
        return "image"
    elif len(table_headers_found) >= 2:
        return "table"  # Has headers but few matches — might still have data
    elif has_images and len(pn_candidates) > 0:
        return "mixed"
    elif total_spans < 5:
        return "blank"
    else:
        return "mixed"


def detect_headlines(spans):
    """Find headline/section header text (large or bold text)."""
    headlines = []
    for s in spans:
        # Headlines are typically >= 12pt and bold
        if s["size"] >= 12 and is_bold(s["flags"]):
            headlines.append({
                "text": s["text"],
                "bbox": {"x": s["bbox"][0], "y": s["bbox"][1],
                         "w": s["bbox"][2] - s["bbox"][0],
                         "h": s["bbox"][3] - s["bbox"][1]},
                "font": {"name": s["font"], "size": s["size"],
                         "bold": True},
            })
        # Or just very large text
        elif s["size"] >= 16:
            headlines.append({
                "text": s["text"],
                "bbox": {"x": s["bbox"][0], "y": s["bbox"][1],
                         "w": s["bbox"][2] - s["bbox"][0],
                         "h": s["bbox"][3] - s["bbox"][1]},
                "font": {"name": s["font"], "size": s["size"],
                         "bold": is_bold(s["flags"])},
            })

    return headlines


def detect_tables(spans, page_width):
    """Detect table structures by finding column headers and computing x-ranges."""
    tables = []

    # Find all known column headers
    headers = []
    for s in spans:
        text_upper = s["text"].upper()
        if text_upper in ALL_KNOWN_HEADERS:
            x_center = (s["bbox"][0] + s["bbox"][2]) / 2
            headers.append({
                "name": text_upper,
                "x_center": x_center,
                "x0": s["bbox"][0],
                "x1": s["bbox"][2],
                "y": s["bbox"][1],
                "is_target": text_upper in TARGET_COLS,
            })

    if not headers:
        return tables

    # Sort headers by y then x to group into table rows
    headers.sort(key=lambda h: (round(h["y"] / 20) * 20, h["x_center"]))

    # Group headers by y-proximity (same header row)
    header_rows = []
    current_row = [headers[0]]
    for h in headers[1:]:
        if abs(h["y"] - current_row[0]["y"]) < 15:
            current_row.append(h)
        else:
            header_rows.append(current_row)
            current_row = [h]
    header_rows.append(current_row)

    # Build table definition for each header row
    for row_idx, header_row in enumerate(header_rows):
        header_row.sort(key=lambda h: h["x_center"])
        columns = []
        for i, h in enumerate(header_row):
            # Compute x-range boundaries
            if i > 0:
                x_left = (header_row[i-1]["x_center"] + h["x_center"]) / 2
            else:
                x_left = 0
            if i < len(header_row) - 1:
                x_right = (h["x_center"] + header_row[i+1]["x_center"]) / 2
            else:
                x_right = page_width

            columns.append({
                "name": h["name"],
                "x_range": [round(x_left, 1), round(x_right, 1)],
                "data_type": "part_number" if h["is_target"] else "other",
                "extract": h["is_target"],
            })

        # Estimate table bbox from header positions + content below
        header_y = min(h["y"] for h in header_row)
        header_x0 = min(h["x0"] for h in header_row)
        header_x1 = max(h["x1"] for h in header_row)

        # Find the lowest data span in this table's column range
        max_y = header_y + 200  # default
        for s in spans:
            sx = (s["bbox"][0] + s["bbox"][2]) / 2
            sy = s["bbox"][1]
            if sy > header_y + 10 and header_x0 - 20 <= sx <= header_x1 + 20:
                max_y = max(max_y, s["bbox"][3])

        # Count expected rows by counting spans in the first target column
        expected_rows = 0
        for col in columns:
            if col["extract"]:
                for s in spans:
                    sx = (s["bbox"][0] + s["bbox"][2]) / 2
                    if (col["x_range"][0] <= sx <= col["x_range"][1]
                            and s["bbox"][1] > header_y + 5):
                        if PN_REGEX and PN_REGEX.match(s["text"]):
                            expected_rows += 1
                break  # Only count from first target column

        tables.append({
            "type": "data_table",
            "table_index": row_idx,
            "bbox": {"x": round(header_x0 - 10, 1), "y": round(header_y - 5, 1),
                     "w": round(header_x1 - header_x0 + 20, 1),
                     "h": round(max_y - header_y + 10, 1)},
            "columns": columns,
            "expected_rows": expected_rows,
        })

    return tables


def profile_fonts(spans):
    """Catalog font signatures per data type."""
    pn_fonts = []
    other_fonts = []

    for s in spans:
        if PN_REGEX and PN_REGEX.match(s["text"]):
            pn_fonts.append({
                "name": s["font"],
                "size": s["size"],
                "bold": is_bold(s["flags"]),
            })
        else:
            other_fonts.append({
                "name": s["font"],
                "size": s["size"],
                "bold": is_bold(s["flags"]),
            })

    # Find most common font signature for part numbers
    pn_profile = None
    if pn_fonts:
        # Count (font, size, bold) combos
        combos = Counter((f["name"], f["size"], f["bold"]) for f in pn_fonts)
        top = combos.most_common(1)[0][0]
        pn_profile = {"name": top[0], "size": top[1], "bold": top[2]}

    return {"part_number": pn_profile}


def detect_images(page):
    """Detect product images and dimension diagrams."""
    components = []
    images = page.get_images(full=True)
    for img_idx, img in enumerate(images):
        # Get image position via page.get_image_rects
        rects = page.get_image_rects(img[0])
        for rect in rects:
            components.append({
                "type": "product_image",
                "bbox": {"x": round(rect.x0, 1), "y": round(rect.y0, 1),
                         "w": round(rect.width, 1), "h": round(rect.height, 1)},
                "description": f"Image {img_idx + 1}",
            })

    return components


def scan_document(pdf_path, target_pages=None):
    """Run full pre-scan on a PDF document."""
    doc = fitz.open(pdf_path)
    doc_id = os.path.basename(pdf_path)[:-4]

    intelligence = {
        "document_id": doc_id,
        "total_pages": len(doc),
        "scan_timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "pages": [],
    }

    for page_num in range(len(doc)):
        if target_pages and (page_num + 1) not in target_pages:
            continue

        page = doc[page_num]
        page_width = page.rect.width

        # Extract rich spans with font metadata
        spans = extract_rich_spans(page)

        # 1. Classify page
        page_type = classify_page(spans, page)

        # 2. Detect headlines
        headlines = detect_headlines(spans)

        # 3. Detect tables
        tables = detect_tables(spans, page_width)

        # 4. Detect images
        images = detect_images(page)

        # 5. Profile fonts
        font_profile = profile_fonts(spans)

        # Determine if extraction should run
        has_part_numbers = page_type in ("table", "mixed")
        skip_extraction = page_type in ("cover", "blank", "image")

        # Build components list
        components = tables + images

        page_data = {
            "page_num": page_num + 1,
            "page_type": page_type,
            "has_part_numbers": has_part_numbers,
            "skip_extraction": skip_extraction,
            "total_spans": len(spans),
            "headlines": headlines,
            "components": components,
            "font_profile": font_profile,
        }

        print(f"  [PRE-SCAN] Page {page_num+1}: {page_type} | "
              f"{len(headlines)} headlines | {len(tables)} tables | "
              f"{len(images)} images | skip={skip_extraction}")

        intelligence["pages"].append(page_data)

    doc.close()
    return intelligence


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Document Intelligence Pre-Scan")
    parser.add_argument('--file', type=str, default=None)
    parser.add_argument('--pages', type=str, default=None)
    args = parser.parse_args()

    target_pages = None
    if args.pages:
        target_pages = [int(p.strip()) for p in args.pages.split(',')]

    for fname in os.listdir(INPUT_FOLDER):
        if not fname.lower().endswith('.pdf'):
            continue
        if args.file and fname != args.file:
            continue

        doc_id = fname[:-4]
        pdf_path = os.path.join(INPUT_FOLDER, fname)
        out_dir = os.path.join(OUTPUT_FOLDER, doc_id)
        os.makedirs(out_dir, exist_ok=True)

        print(f"\n[PRE-SCAN] Analyzing: {fname}")
        t0 = time.time()
        intelligence = scan_document(pdf_path, target_pages)
        elapsed = time.time() - t0

        out_path = os.path.join(out_dir, "document_intelligence.yaml")
        with open(out_path, 'w', encoding='utf-8') as f:
            yaml.dump(intelligence, f, default_flow_style=False,
                      allow_unicode=True, width=120)

        print(f"[PRE-SCAN] Complete in {elapsed:.2f}s -> {out_path}")


if __name__ == "__main__":
    main()
