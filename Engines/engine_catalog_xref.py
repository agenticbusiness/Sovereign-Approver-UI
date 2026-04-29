"""
Engine 5: Master Catalog Cross-Reference — Validates extracted text against
the known Everflow SKU list (Everflow_Master_Parsed.csv).

100% precision by design: only text that exact-matches a known SKU passes.
Trade-off: cannot discover NEW part numbers not yet in the catalog.

Loads the CSV into a hash set for O(1) lookup per span.
Also provides pre-computed bounding boxes from the catalog as a secondary signal.

Outputs: _2 Output Data/<doc_id>/engine_catalog_xref.json
"""
import csv
import fitz
import json
import os
import sys
import time

VAULT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_FOLDER = os.path.join(VAULT_DIR, "_1 INPUT FOLDER")
OUTPUT_FOLDER = os.path.join(VAULT_DIR, "_2 Output Data")
CATALOG_PATH = os.path.join(VAULT_DIR, "Everflow_Master_Parsed.csv")

# Cache the catalog in memory
_CATALOG_CACHE = None


def load_catalog():
    """Load the master catalog CSV into a lookup dict.
    Returns: {part_number: [{page, x0, y0, x1, y1}, ...]}
    """
    global _CATALOG_CACHE
    if _CATALOG_CACHE is not None:
        return _CATALOG_CACHE

    if not os.path.exists(CATALOG_PATH):
        print(f"[WARN] Master catalog not found: {CATALOG_PATH}")
        _CATALOG_CACHE = {}
        return _CATALOG_CACHE

    catalog = {}
    with open(CATALOG_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            pn = row.get("Part Number", "").strip()
            if not pn:
                continue
            if pn not in catalog:
                catalog[pn] = []
            try:
                catalog[pn].append({
                    "page": int(row.get("Physical Page", 0)),
                    "x0": float(row.get("x0", 0)),
                    "y0": float(row.get("y0", 0)),
                    "x1": float(row.get("x1", 0)),
                    "y1": float(row.get("y1", 0)),
                })
            except (ValueError, TypeError):
                pass

    _CATALOG_CACHE = catalog
    return catalog


def extract_by_catalog(page, page_num_1idx, catalog):
    """
    Extract text from a page, keeping only spans that match known SKUs.

    Args:
        page: PyMuPDF page object
        page_num_1idx: 1-indexed page number
        catalog: dict from load_catalog()

    Returns:
        list of match dicts
    """
    blocks = page.get_text("dict")["blocks"]
    matches = []
    seen = set()  # Dedup by text + y position

    # Build quick lookup set for O(1)
    sku_set = set(catalog.keys())

    for block in blocks:
        if "lines" not in block:
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                text = span["text"].strip()
                if not text or text in seen:
                    continue

                # Exact match against master catalog
                if text in sku_set:
                    bbox = span["bbox"]
                    dedup_key = f"{text}_{bbox[1]:.0f}"
                    if dedup_key in seen:
                        continue
                    seen.add(dedup_key)

                    # Check if the catalog has a page-specific entry
                    catalog_entries = catalog.get(text, [])
                    on_expected_page = any(e["page"] == page_num_1idx
                                           for e in catalog_entries)

                    matches.append({
                        "field": "Part Number",
                        "text": text,
                        "bbox": {
                            "x": bbox[0],
                            "y": bbox[1],
                            "width": bbox[2] - bbox[0],
                            "height": bbox[3] - bbox[1],
                        },
                        "confidence": "high",
                        "catalog_verified": True,
                        "on_expected_page": on_expected_page,
                    })

    return matches


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Engine 5: Master Catalog Cross-Reference")
    parser.add_argument('--pages', type=str, default=None)
    parser.add_argument('--file', type=str, default=None)
    args = parser.parse_args()

    target_pages = None
    if args.pages:
        target_pages = [int(p.strip()) for p in args.pages.split(',')]

    catalog = load_catalog()
    print(f"[ENGINE:CatalogXRef] Loaded {len(catalog)} unique SKUs from master catalog")

    for fname in os.listdir(INPUT_FOLDER):
        if not fname.lower().endswith('.pdf'):
            continue
        if args.file and fname != args.file:
            continue

        doc_id = fname[:-4]
        pdf_path = os.path.join(INPUT_FOLDER, fname)
        out_dir = os.path.join(OUTPUT_FOLDER, doc_id)
        os.makedirs(out_dir, exist_ok=True)

        doc = fitz.open(pdf_path)
        pages_data = []

        print(f"\n[ENGINE:CatalogXRef] Processing: {fname}")
        t0 = time.time()

        for page_num in range(len(doc)):
            if target_pages and (page_num + 1) not in target_pages:
                continue

            page = doc[page_num]
            matches = extract_by_catalog(page, page_num + 1, catalog)

            on_page = sum(1 for m in matches if m.get("on_expected_page"))
            print(f"  [CatalogXRef] Page {page_num+1}: {len(matches)} matches "
                  f"({on_page} on expected page)")

            pages_data.append({
                "page_num": page_num + 1,
                "matches": matches,
            })

        doc.close()
        elapsed = time.time() - t0

        total = sum(len(p["matches"]) for p in pages_data)
        result = {
            "engine": "catalog_xref",
            "filename": fname,
            "pages": pages_data,
            "total_matches": total,
            "elapsed_seconds": round(elapsed, 3),
            "catalog_size": len(catalog),
        }

        out_path = os.path.join(out_dir, "engine_catalog_xref.json")
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2)

        print(f"[ENGINE:CatalogXRef] {total} verified parts in {elapsed:.2f}s -> {out_path}")


if __name__ == "__main__":
    main()
