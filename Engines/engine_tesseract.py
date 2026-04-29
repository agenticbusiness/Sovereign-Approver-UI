"""
Engine 1: Tesseract OCR — Renders PDF pages to images, runs Tesseract
for word-level bounding boxes with TSV output.
Applies column_filter for spatial column filtering + Proxy Pointer RAG validation.
Outputs: _2 Output Data/<doc_id>/engine_tesseract.json

Requires: tesseract binary in PATH, pytesseract, Pillow, fitz (for rendering)
"""
import json
import os
import sys
import time

try:
    import pytesseract
except ImportError:
    print("[FATAL] pytesseract not installed. Run: pip install pytesseract")
    sys.exit(1)

try:
    import fitz  # PyMuPDF for PDF-to-image rendering
except ImportError:
    print("[FATAL] PyMuPDF not installed. Run: pip install PyMuPDF")
    sys.exit(1)

from PIL import Image
import io

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from column_filter import load_config, filter_spans

# Set Tesseract binary path from config
import yaml
_cfg_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "Matrices", "parse_request.yaml")
with open(_cfg_path, 'r', encoding='utf-8') as _f:
    _cfg = yaml.safe_load(_f)
_tess_cmd = _cfg.get("tesseract_cmd", r"C:\Program Files\Tesseract-OCR\tesseract.exe")
if os.path.exists(_tess_cmd):
    pytesseract.pytesseract.tesseract_cmd = _tess_cmd

INPUT_FOLDER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_1 INPUT FOLDER")
OUTPUT_FOLDER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_2 Output Data")

# DPI for rendering PDF pages to images
RENDER_DPI = 150
# Scale factor: PDF points -> pixels at RENDER_DPI
SCALE = RENDER_DPI / 72


def render_page_to_image(page):
    """Render a PyMuPDF page to a PIL Image."""
    pix = page.get_pixmap(dpi=RENDER_DPI)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    return img, pix.width, pix.height


def tesseract_extract_spans(image):
    """
    Run Tesseract on an image and return word-level text spans with bboxes.

    Uses TSV output (--psm 6 for uniform block assumption).
    Returns spans in PDF-point coordinate space (divided by SCALE).
    """
    # Run Tesseract with TSV output
    tsv_data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)

    spans = []
    n_items = len(tsv_data["text"])

    for i in range(n_items):
        text = tsv_data["text"][i].strip()
        conf = int(tsv_data["conf"][i])

        # Skip empty text or very low confidence
        if not text or conf < 30:
            continue

        # Tesseract gives pixel coordinates — convert back to PDF points
        px_left = tsv_data["left"][i]
        px_top = tsv_data["top"][i]
        px_width = tsv_data["width"][i]
        px_height = tsv_data["height"][i]

        # Convert pixel coords to PDF point coords
        x0 = px_left / SCALE
        y0 = px_top / SCALE
        x1 = (px_left + px_width) / SCALE
        y1 = (px_top + px_height) / SCALE

        spans.append({
            "text": text,
            "bbox": (x0, y0, x1, y1),
            "ocr_confidence": conf,
        })

    return spans


def extract_from_pdf(pdf_path, config, exclusion_terms, whitelist, overrides,
                     target_pages=None):
    """Run Tesseract extraction on a PDF."""
    doc = fitz.open(pdf_path)
    doc_id = os.path.basename(pdf_path)[:-4]
    pages_data = []

    for page_num in range(len(doc)):
        if target_pages and (page_num + 1) not in target_pages:
            continue

        page = doc[page_num]
        page_width = page.rect.width

        # Render page to image
        img, px_w, px_h = render_page_to_image(page)

        # Run Tesseract OCR
        spans = tesseract_extract_spans(img)

        # Apply column filter + Proxy Pointer RAG validation
        matches, headers, target_ranges = filter_spans(
            spans, page_width, config, exclusion_terms, whitelist, overrides,
            doc_id=doc_id, page_num=page_num + 1
        )

        header_names = [h["name"] for h in (headers or [])]
        print(f"  [Tesseract] Page {page_num+1}: {len(matches)} matches "
              f"(columns: {header_names}, OCR spans: {len(spans)})")

        pages_data.append({
            "page_num": page_num + 1,
            "matches": matches,
            "headers_found": header_names,
            "total_ocr_spans": len(spans),
        })

    doc.close()
    return pages_data


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Engine 1: Tesseract Extractor")
    parser.add_argument('--pages', type=str, default=None,
                        help='Comma-separated page numbers (1-indexed)')
    parser.add_argument('--file', type=str, default=None,
                        help='Specific PDF filename')
    args = parser.parse_args()

    # Verify Tesseract is available
    try:
        ver = pytesseract.get_tesseract_version()
        print(f"[ENGINE:Tesseract] Version: {ver}")
    except Exception:
        print("[FATAL] Tesseract binary not found. Install via: choco install tesseract")
        sys.exit(1)

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

        print(f"\n[ENGINE:Tesseract] Processing: {fname}")
        t0 = time.time()
        pages = extract_from_pdf(pdf_path, config, exclusion_terms, whitelist,
                                 overrides, target_pages)
        elapsed = time.time() - t0

        total = sum(len(p["matches"]) for p in pages)
        result = {
            "engine": "tesseract",
            "filename": fname,
            "pages": pages,
            "total_matches": total,
            "elapsed_seconds": round(elapsed, 3),
        }

        out_path = os.path.join(out_dir, "engine_tesseract.json")
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2)

        print(f"[ENGINE:Tesseract] {total} part numbers in {elapsed:.2f}s -> {out_path}")


if __name__ == "__main__":
    main()
