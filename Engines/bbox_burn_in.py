"""
BBox Burn-In Engine — Burns verified bounding boxes directly onto page PNGs.
Takes parsed_spatial_data.json and the original PDF, renders each page with
colored rectangles drawn on the image.

Outputs:
  _2 Output Data/<doc_id>/pages/<page_num>_marked.png  (annotated)
  _2 Output Data/<doc_id>/pages/<page_num>.png         (clean, unchanged)

Color coding:
  Green  = auto-approved (preflight_score >= 90)
  Yellow = flagged (50-89)
  Red    = red-flagged (<50)
  Cyan   = pending (no score yet)
"""
import fitz
import json
import os
import sys
import time

VAULT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_FOLDER = os.path.join(VAULT_DIR, "_1 INPUT FOLDER")
OUTPUT_FOLDER = os.path.join(VAULT_DIR, "_2 Output Data")

# DPI for rendering (must match engine_tesseract.py)
RENDER_DPI = 150
SCALE = RENDER_DPI / 72  # PDF points to pixels


def score_to_color(score):
    """Map preflight score to an RGB color."""
    if score is None:
        return (0, 0.8, 0.8)     # Cyan — no score
    if score >= 90:
        return (0, 0.8, 0.2)     # Green — auto-approved
    elif score >= 50:
        return (0.9, 0.7, 0)     # Yellow — flagged
    else:
        return (0.9, 0.1, 0.1)   # Red — red-flagged


def burn_boxes_on_page(page, matches, dpi=RENDER_DPI):
    """
    Render a PDF page to a pixmap and draw bounding box rectangles.
    Returns the annotated pixmap.

    Matches are in PDF-point coordinates. We draw on the rendered image
    by scaling to pixel coordinates.
    """
    pix = page.get_pixmap(dpi=dpi)

    # We can't draw directly on a pixmap easily, so we use
    # PyMuPDF's page annotation approach: draw on a copy of the page,
    # then render the annotated page.
    # Create a temporary annotation layer
    for match in matches:
        bbox = match.get("bbox", {})
        score = match.get("_preflight_score")
        color = score_to_color(score)

        x0 = bbox.get("x", 0)
        y0 = bbox.get("y", 0)
        w = bbox.get("width", 0)
        h = bbox.get("height", 0)

        rect = fitz.Rect(x0, y0, x0 + w, y0 + h)

        # Draw rectangle annotation
        annot = page.add_rect_annot(rect)
        annot.set_colors(stroke=color)
        annot.set_border(width=1.5)
        annot.set_opacity(0.7)
        annot.update()

    # Re-render with annotations burned in
    marked_pix = page.get_pixmap(dpi=dpi)

    # Remove annotations so we don't pollute the original PDF
    for annot in page.annots():
        page.delete_annot(annot)

    return marked_pix


def burn_document(doc_id, spatial_data=None):
    """
    Burn bounding boxes onto all pages of a document.

    Args:
        doc_id: Document identifier (PDF filename without extension)
        spatial_data: Optional pre-loaded parsed_spatial_data.json dict.
                      If None, loads from disk.

    Returns:
        dict with page counts and paths
    """
    pdf_path = os.path.join(INPUT_FOLDER, f"{doc_id}.pdf")
    if not os.path.exists(pdf_path):
        print(f"[BURN-IN] ERROR: PDF not found: {pdf_path}")
        return None

    # Load spatial data
    if spatial_data is None:
        json_path = os.path.join(OUTPUT_FOLDER, doc_id, "parsed_spatial_data.json")
        if not os.path.exists(json_path):
            print(f"[BURN-IN] ERROR: No spatial data: {json_path}")
            return None
        with open(json_path, 'r', encoding='utf-8') as f:
            spatial_data = json.load(f)

    doc = fitz.open(pdf_path)
    pages_dir = os.path.join(OUTPUT_FOLDER, doc_id, "pages")
    os.makedirs(pages_dir, exist_ok=True)

    results = {"doc_id": doc_id, "pages": []}
    t0 = time.time()

    for page_data in spatial_data.get("pages", []):
        page_num = page_data.get("page_num", 1)
        matches = page_data.get("matches", [])

        if page_num < 1 or page_num > len(doc):
            continue

        page = doc[page_num - 1]

        # Save clean PNG if it doesn't exist
        clean_path = os.path.join(pages_dir, f"{page_num}.png")
        if not os.path.exists(clean_path):
            clean_pix = page.get_pixmap(dpi=RENDER_DPI)
            clean_pix.save(clean_path)

        # Burn boxes onto image
        if matches:
            marked_pix = burn_boxes_on_page(page, matches)
            marked_path = os.path.join(pages_dir, f"{page_num}_marked.png")
            marked_pix.save(marked_path)
            print(f"  [BURN-IN] Page {page_num}: {len(matches)} boxes -> {marked_path}")
        else:
            marked_path = clean_path  # No boxes to draw
            print(f"  [BURN-IN] Page {page_num}: No matches (clean PNG only)")

        results["pages"].append({
            "page_num": page_num,
            "match_count": len(matches),
            "clean_png": clean_path,
            "marked_png": marked_path,
        })

    doc.close()
    elapsed = time.time() - t0
    results["elapsed_seconds"] = round(elapsed, 3)
    print(f"[BURN-IN] Complete: {len(results['pages'])} pages in {elapsed:.2f}s")

    return results


def main():
    import argparse
    parser = argparse.ArgumentParser(description="BBox Burn-In Engine")
    parser.add_argument('--doc', type=str, required=True,
                        help='Document ID (folder name in _2 Output Data)')
    args = parser.parse_args()

    burn_document(args.doc)


if __name__ == "__main__":
    main()
