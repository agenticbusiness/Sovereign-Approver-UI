"""
Surya OCR Benchmark v2 — Page 2 of FITTINGS - 150LB MALLEABLE CAST IRON - BLK.pdf
Uses Surya 0.17.x API: FoundationPredictor -> RecognitionPredictor + TableRecPredictor
"""
import time
import json
import os
import re
import fitz  # PyMuPDF for PDF-to-image conversion
from PIL import Image

# Paths
PDF_PATH = r"c:\_3 EVF-Bricks\_02 UI for Spec Sheets - Part Number ONLY\_1 INPUT FOLDER\FITTINGS - 150LB MALLEABLE CAST IRON - BLK.pdf"
OUTPUT_DIR = r"c:\_3 EVF-Bricks\_02 UI for Spec Sheets - Part Number ONLY\_2 Output Data"
PAGE_INDEX = 1  # 0-indexed, page 2

# Part number regex (Everflow format: 4-8 alphanumeric, starting with letter combo)
PART_REGEX = re.compile(r'^[A-Z]{2,4}[A-Z0-9]{2,6}$')

def render_page_to_image(pdf_path, page_idx, dpi=150):
    """Render a single PDF page to a PIL Image."""
    doc = fitz.open(pdf_path)
    page = doc[page_idx]
    pix = page.get_pixmap(dpi=dpi)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    page_width = page.rect.width   # PDF points
    page_height = page.rect.height # PDF points
    doc.close()
    return img, pix.width, pix.height, page_width, page_height

def main():
    print("=" * 60)
    print("  SURYA OCR BENCHMARK v2 — Page 2 Extraction")
    print("=" * 60)

    # Step 1: Render PDF page to image
    t0 = time.time()
    img, px_w, px_h, pdf_w, pdf_h = render_page_to_image(PDF_PATH, PAGE_INDEX)
    t_render = time.time() - t0
    print(f"\n[1] PDF Render: {t_render:.2f}s ({px_w}x{px_h} px, {pdf_w}x{pdf_h} pts)")

    # Step 2: Load Foundation model (shared backbone)
    print("\n[2] Loading Surya FoundationPredictor (shared backbone)...")
    t0 = time.time()
    from surya.foundation import FoundationPredictor
    foundation = FoundationPredictor()
    t_load_foundation = time.time() - t0
    print(f"    Foundation load: {t_load_foundation:.2f}s")

    # Step 3: Run Detection
    print("\n[3] Loading DetectionPredictor...")
    t0 = time.time()
    from surya.detection import DetectionPredictor
    det_predictor = DetectionPredictor()
    t_load_det = time.time() - t0
    print(f"    Det model load: {t_load_det:.2f}s")

    t0 = time.time()
    det_results = det_predictor([img])
    t_detect = time.time() - t0
    det_page = det_results[0]
    print(f"    Detection: {t_detect:.2f}s — Found {len(det_page.bboxes)} text regions")

    # Step 4: Run Recognition using Foundation model
    print("\n[4] Loading RecognitionPredictor (via Foundation)...")
    t0 = time.time()
    from surya.recognition import RecognitionPredictor
    rec_predictor = RecognitionPredictor(foundation)
    t_load_rec = time.time() - t0
    print(f"    Rec model load: {t_load_rec:.2f}s")

    # Extract bboxes as list of [x0,y0,x1,y1] from detection results
    det_bboxes = [bbox.bbox for bbox in det_page.bboxes]

    t0 = time.time()
    rec_results = rec_predictor([img], det_predictor=det_predictor, bboxes=[det_bboxes])
    t_recognize = time.time() - t0
    rec_page = rec_results[0]
    print(f"    Recognition: {t_recognize:.2f}s — Recognized {len(rec_page.text_lines)} text lines")

    # Step 5: Print ALL text lines
    print("\n[5] ALL Extracted Text Lines:")
    print("-" * 80)
    all_lines = []
    for line in rec_page.text_lines:
        bbox = line.bbox  # [x0, y0, x1, y1] in pixel coords
        text = line.text.strip()
        if text:
            all_lines.append({"text": text, "bbox": bbox})
            print(f"  [{bbox[0]:6.1f}, {bbox[1]:6.1f}, {bbox[2]:6.1f}, {bbox[3]:6.1f}] => {text}")

    # Step 6: Filter for part numbers only
    print("\n[6] PART NUMBERS ONLY (regex filtered):")
    print("-" * 80)
    part_numbers = []
    for item in all_lines:
        # Check each word in the line
        for word in item["text"].split():
            word = word.strip()
            if PART_REGEX.match(word):
                part_numbers.append({"text": word, "bbox": item["bbox"]})
                print(f"  {word:20s}  bbox={item['bbox']}")

    # Step 7: Try table detection
    print("\n[7] Table Detection...")
    t_table = 0
    t_load_table = 0
    table_info = None
    try:
        from surya.table_rec import TableRecPredictor
        t0 = time.time()
        table_predictor = TableRecPredictor()
        t_load_table = time.time() - t0
        print(f"    Table model load: {t_load_table:.2f}s")

        # TableRecPredictor needs bboxes from detection
        t0 = time.time()
        table_results = table_predictor([img], [det_page.bboxes])
        t_table = time.time() - t0
        table_page = table_results[0]
        print(f"    Table detection: {t_table:.2f}s")

        # Dump table structure
        if hasattr(table_page, 'cells'):
            print(f"    Cells found: {len(table_page.cells)}")
            for ci, cell in enumerate(table_page.cells[:10]):
                attrs = {a: getattr(cell, a, None) for a in ['bbox', 'row_id', 'col_id', 'text', 'label']}
                print(f"      Cell {ci}: {attrs}")
            if len(table_page.cells) > 10:
                print(f"      ... and {len(table_page.cells) - 10} more cells")
            table_info = {"cells": len(table_page.cells)}
        elif hasattr(table_page, 'tables'):
            print(f"    Tables found: {len(table_page.tables)}")
            table_info = {"tables": len(table_page.tables)}
        else:
            print(f"    Result attributes: {[a for a in dir(table_page) if not a.startswith('_')]}")
    except Exception as e:
        print(f"    Table detection failed: {e}")
        import traceback; traceback.print_exc()

    # Step 8: Summary
    total_time = t_render + t_load_foundation + t_load_det + t_detect + t_load_rec + t_recognize + t_load_table + t_table
    print("\n" + "=" * 60)
    print("  BENCHMARK SUMMARY")
    print("=" * 60)
    print(f"  PDF Render:          {t_render:.2f}s")
    print(f"  Foundation Load:     {t_load_foundation:.2f}s")
    print(f"  Det Model Load:      {t_load_det:.2f}s")
    print(f"  Detection:           {t_detect:.2f}s")
    print(f"  Rec Model Load:      {t_load_rec:.2f}s")
    print(f"  Recognition:         {t_recognize:.2f}s")
    print(f"  Table Model Load:    {t_load_table:.2f}s")
    print(f"  Table Detection:     {t_table:.2f}s")
    print(f"  TOTAL:               {total_time:.2f}s")
    print(f"  Text regions:        {len(det_page.bboxes)}")
    print(f"  Text lines:          {len(rec_page.text_lines)}")
    print(f"  Part numbers found:  {len(part_numbers)}")
    print(f"  Expected (ground truth): 30")
    print(f"  Accuracy:            {'PASS' if len(part_numbers) == 30 else 'NEEDS TUNING'}")

    # Save
    out_path = os.path.join(OUTPUT_DIR, "surya_benchmark_page2.json")
    with open(out_path, 'w') as f:
        json.dump({
            "timing": {
                "render": round(t_render, 2),
                "foundation_load": round(t_load_foundation, 2),
                "detection_model_load": round(t_load_det, 2),
                "detection": round(t_detect, 2),
                "recognition_model_load": round(t_load_rec, 2),
                "recognition": round(t_recognize, 2),
                "table_model_load": round(t_load_table, 2),
                "table_detection": round(t_table, 2),
                "total": round(total_time, 2)
            },
            "counts": {
                "text_regions": len(det_page.bboxes),
                "text_lines": len(rec_page.text_lines),
                "part_numbers": len(part_numbers)
            },
            "part_numbers": part_numbers,
            "all_text_lines": all_lines,
            "table_info": table_info
        }, f, indent=2)
    print(f"\n  Saved: {out_path}")

if __name__ == "__main__":
    main()
