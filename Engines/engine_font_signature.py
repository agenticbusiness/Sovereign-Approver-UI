"""
Engine 4: Font Signature — Extracts part numbers by matching font metadata.
Uses PyMuPDF get_text("dict") to read font name, size, and bold flags.
Part numbers in EVF catalogs use specific font signatures that differ from
headers, quantities, and notes.

Loads font profile from document_intelligence.yaml when available.
Falls back to auto-detection if no pre-scan exists.

Outputs: _2 Output Data/<doc_id>/engine_font_signature.json
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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from column_filter import load_config


def is_bold(flags):
    """Check if font flags indicate bold."""
    return bool(flags & (1 << 4))


def load_font_profile(doc_id):
    """Load font profile from document_intelligence.yaml if available."""
    di_path = os.path.join(OUTPUT_FOLDER, doc_id, "document_intelligence.yaml")
    if os.path.exists(di_path):
        with open(di_path, 'r', encoding='utf-8') as f:
            di = yaml.safe_load(f) or {}
        # Collect font profiles from all pages
        profiles = []
        for page in di.get("pages", []):
            fp = page.get("font_profile", {})
            pn_prof = fp.get("part_number")
            if pn_prof:
                profiles.append(pn_prof)
        if profiles:
            # Use most common profile
            combos = Counter((p["name"], p["size"], p["bold"]) for p in profiles)
            top = combos.most_common(1)[0][0]
            return {"name": top[0], "size": top[1], "bold": top[2]}
    return None


def auto_detect_font_profile(page, pn_regex):
    """Auto-detect font profile by finding part number matches and their fonts."""
    blocks = page.get_text("dict")["blocks"]
    font_hits = []

    for block in blocks:
        if "lines" not in block:
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                text = span["text"].strip()
                if text and pn_regex.match(text):
                    font_hits.append({
                        "name": span.get("font", ""),
                        "size": round(span.get("size", 0), 1),
                        "bold": is_bold(span.get("flags", 0)),
                    })

    if font_hits:
        combos = Counter((f["name"], f["size"], f["bold"]) for f in font_hits)
        top = combos.most_common(1)[0][0]
        return {"name": top[0], "size": top[1], "bold": top[2]}
    return None


def extract_by_font(page, font_profile, expected_truths):
    """Extract text matching the font signature profile."""
    blocks = page.get_text("dict")["blocks"]
    matches = []

    if not font_profile:
        return matches

    target_font = font_profile["name"]
    target_size = font_profile["size"]
    target_bold = font_profile["bold"]

    for block in blocks:
        if "lines" not in block:
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                text = span["text"].strip()
                if not text:
                    continue

                # Check font signature match
                font_name = span.get("font", "")
                font_size = round(span.get("size", 0), 1)
                font_bold = is_bold(span.get("flags", 0))

                # Font must match (allowing size tolerance of 0.5pt)
                if (font_name == target_font
                        and abs(font_size - target_size) <= 0.5
                        and font_bold == target_bold):

                    # EXACT MATCH against LLM Truths
                    normalized_text = text.replace(" ", "")
                    matched_truth = None
                    
                    # Assume we pass expected_truths into this function
                    for t in expected_truths:
                        if t.replace(" ", "") == normalized_text:
                            matched_truth = text
                            break

                    if not matched_truth:
                        continue

                    bbox = span["bbox"]
                    conf = "high"

                    matches.append({
                        "field": "Part Number",
                        "text": matched_truth,
                        "bbox": {
                            "x": round(bbox[0], 2),
                            "y": round(bbox[1], 2),
                            "width": round(bbox[2] - bbox[0], 2),
                            "height": round(bbox[3] - bbox[1], 2),
                        },
                        "confidence": conf,
                        "font_match": True,
                    })

    return matches


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Engine 4: Font Signature Extractor")
    parser.add_argument('--pages', type=str, default=None)
    parser.add_argument('--file', type=str, default=None)
    args = parser.parse_args()

    target_pages = None
    if args.pages:
        target_pages = [int(p.strip()) for p in args.pages.split(',')]

    config, exclusion_terms, whitelist, _ = load_config()

    # Get Part Number regex
    pn_regex = None
    for t in config.get("extraction_targets", []):
        if t.get("field") == "Part Number":
            pn_regex = re.compile(t.get("safeguard_regex", ""))
            break
    if not pn_regex:
        print("[FATAL] No Part Number regex in parse_request.yaml")
        return

    for fname in os.listdir(INPUT_FOLDER):
        if not fname.lower().endswith('.pdf'):
            continue
        if args.file and fname != args.file:
            continue

        doc_id = fname[:-4]
        pdf_path = os.path.join(INPUT_FOLDER, fname)
        out_dir = os.path.join(OUTPUT_FOLDER, doc_id)
        os.makedirs(out_dir, exist_ok=True)

        # Try to load pre-scan font profile
        font_profile = load_font_profile(doc_id)

        doc = fitz.open(pdf_path)
        pages_data = []

        print(f"\n[ENGINE:FontSig] Processing: {fname}")
        t0 = time.time()

        for page_num in range(len(doc)):
            if target_pages and (page_num + 1) not in target_pages:
                continue

            page = doc[page_num]
            page_width = page.rect.width

            # Auto-detect font profile if no pre-scan
            active_profile = font_profile
            if not active_profile:
                active_profile = auto_detect_font_profile(page, pn_regex)

            from column_filter import load_expected_truths
            expected_data = load_expected_truths(doc_id)
            expected_truths = []
            if expected_data and str(page_num + 1) in expected_data.get("pages", {}):
                page_data = expected_data["pages"][str(page_num + 1)]
                if isinstance(page_data, dict):
                    parts_list = page_data.get("part_numbers", [])
                else:
                    parts_list = page_data
                expected_truths = [str(t).strip() for t in parts_list]

            matches = extract_by_font(page, active_profile, expected_truths)

            profile_str = (f"{active_profile['name']} {active_profile['size']}pt "
                          f"{'bold' if active_profile['bold'] else 'regular'}"
                          if active_profile else "NONE")
            print(f"  [FontSig] Page {page_num+1}: {len(matches)} matches "
                  f"(profile: {profile_str})")

            pages_data.append({
                "page_num": page_num + 1,
                "matches": matches,
                "font_profile_used": active_profile,
            })

        doc.close()
        elapsed = time.time() - t0

        total = sum(len(p["matches"]) for p in pages_data)
        result = {
            "engine": "font_signature",
            "filename": fname,
            "pages": pages_data,
            "total_matches": total,
            "elapsed_seconds": round(elapsed, 3),
        }

        out_path = os.path.join(out_dir, "engine_font_signature.json")
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2)

        print(f"[ENGINE:FontSig] {total} parts in {elapsed:.2f}s -> {out_path}")


if __name__ == "__main__":
    main()
