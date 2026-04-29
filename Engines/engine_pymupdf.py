"""
Engine 2: PyMuPDF — Extracts embedded text from digital PDFs with bounding boxes.
Uses fitz (PyMuPDF) get_text("dict") for instant text extraction.
Applies column_filter for spatial column filtering + Proxy Pointer RAG validation.
Outputs: _2 Output Data/<doc_id>/engine_pymupdf.json
"""
import fitz
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from column_filter import load_config, filter_spans

INPUT_FOLDER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_1 INPUT FOLDER")
OUTPUT_FOLDER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_2 Output Data")


def extract_text_spans(page):
    """Extract all text spans from a PDF page as standardized dicts."""
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
                        "bbox": tuple(span["bbox"]),  # (x0, y0, x1, y1)
                    })

    return spans


def extract_from_pdf(pdf_path, config, exclusion_terms, whitelist, overrides,
                     target_pages=None):
    """Run PyMuPDF extraction on a PDF."""
    doc = fitz.open(pdf_path)
    doc_id = os.path.basename(pdf_path)[:-4]
    pages_data = []

    for page_num in range(len(doc)):
        if target_pages and (page_num + 1) not in target_pages:
            continue

        page = doc[page_num]
        page_width = page.rect.width

        # Get all text spans
        spans = extract_text_spans(page)

        # Apply column filter + Proxy Pointer RAG validation
        matches, headers, target_ranges = filter_spans(
            spans, page_width, config, exclusion_terms, whitelist, overrides,
            doc_id=doc_id, page_num=page_num + 1
        )

        header_names = [h["name"] for h in (headers or [])]
        print(f"  [PyMuPDF] Page {page_num+1}: {len(matches)} matches "
              f"(columns: {header_names})")

        pages_data.append({
            "page_num": page_num + 1,
            "matches": matches,
            "headers_found": header_names,
        })

    doc.close()
    return pages_data


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Engine 2: PyMuPDF Extractor")
    parser.add_argument('--pages', type=str, default=None,
                        help='Comma-separated page numbers (1-indexed)')
    parser.add_argument('--file', type=str, default=None,
                        help='Specific PDF filename')
    args = parser.parse_args()

    target_pages = None
    if args.pages:
        target_pages = [int(p.strip()) for p in args.pages.split(',')]

    config, exclusion_terms, whitelist, overrides = load_config()

    for fname in os.listdir(INPUT_FOLDER):
        if not fname.lower().endswith('.pdf'):
            continue
        if args.file and fname != args.file:
            continue

        doc_id = fname[:-4]
        pdf_path = os.path.join(INPUT_FOLDER, fname)
        out_dir = os.path.join(OUTPUT_FOLDER, doc_id)
        os.makedirs(out_dir, exist_ok=True)

        print(f"\n[ENGINE:PyMuPDF] Processing: {fname}")
        t0 = time.time()
        pages = extract_from_pdf(pdf_path, config, exclusion_terms, whitelist,
                                 overrides, target_pages)
        elapsed = time.time() - t0

        total = sum(len(p["matches"]) for p in pages)
        result = {
            "engine": "pymupdf",
            "filename": fname,
            "pages": pages,
            "total_matches": total,
            "elapsed_seconds": round(elapsed, 3),
        }

        out_path = os.path.join(out_dir, "engine_pymupdf.json")
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2)

        print(f"[ENGINE:PyMuPDF] {total} part numbers in {elapsed:.2f}s -> {out_path}")


if __name__ == "__main__":
    main()
