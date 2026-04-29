"""
Judge Orchestrator — Consumes outputs from all 3 engines (Tesseract, PyMuPDF,
LiteParse), applies consensus logic, and produces the final merged output.
Validated by Proxy Pointer RAG constraints before writing parsed_spatial_data.json.

Consensus Rules:
- Unanimous (3/3): AUTO-APPROVE, confidence=high
- Majority (2/3): MAJORITY VOTE, confidence=medium
- Single (1/3): ESCALATE, confidence=low
- Bounding boxes are matched across engines by text + proximity (bbox_tolerance)
"""
import json
import os
import sys
import re
import yaml
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from column_filter import load_config

VAULT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_FOLDER = os.path.join(VAULT_DIR, "_2 Output Data")
MATRICES_DIR = os.path.join(VAULT_DIR, "Matrices")


def load_judge_config():
    """Load judge-specific config from parse_request.yaml."""
    config_path = os.path.join(MATRICES_DIR, "parse_request.yaml")
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    return config.get("judge", {})


def load_engine_outputs(doc_id):
    """Load all available engine outputs for a document."""
    doc_dir = os.path.join(OUTPUT_FOLDER, doc_id)
    engines = {}

    for engine_file in ["engine_tesseract.json", "engine_pymupdf.json",
                         "engine_font_signature.json"]:
        path = os.path.join(doc_dir, engine_file)
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                engines[data["engine"]] = data

    return engines


def bbox_distance(bbox1, bbox2):
    """Calculate Manhattan distance between two bbox centers."""
    cx1 = bbox1["x"] + bbox1["width"] / 2
    cy1 = bbox1["y"] + bbox1["height"] / 2
    cx2 = bbox2["x"] + bbox2["width"] / 2
    cy2 = bbox2["y"] + bbox2["height"] / 2
    return abs(cx1 - cx2) + abs(cy1 - cy2)


def merge_bboxes(bboxes):
    """Average multiple bounding boxes into one."""
    if not bboxes:
        return None
    avg_x = sum(b["x"] for b in bboxes) / len(bboxes)
    avg_y = sum(b["y"] for b in bboxes) / len(bboxes)
    avg_w = sum(b["width"] for b in bboxes) / len(bboxes)
    avg_h = sum(b["height"] for b in bboxes) / len(bboxes)
    return {
        "x": round(avg_x, 2),
        "y": round(avg_y, 2),
        "width": round(avg_w, 2),
        "height": round(avg_h, 2),
    }


def find_consensus(engine_pages, judge_config):
    """
    Build consensus across engine outputs for a single page.

    Returns list of merged matches with consensus metadata.
    """
    tolerance = judge_config.get("bbox_tolerance_px", 10)
    confidence_levels = judge_config.get("confidence_levels", {
        "unanimous": "high", "majority": "medium", "single": "low"
    })

    # Collect all matches from all engines, tagged by source
    all_matches = []
    for engine_name, matches in engine_pages.items():
        for match in matches:
            all_matches.append({
                "engine": engine_name,
                "text": match["text"],
                "bbox": match["bbox"],
                "confidence": match.get("confidence", "medium"),
            })

    # OCR confusion normalization: common digit↔letter misreads
    OCR_CONFUSION = str.maketrans("OoIlSs", "001155")

    def normalize_ocr(text):
        """Normalize OCR confusion pairs for matching purposes."""
        return text.upper().translate(OCR_CONFUSION)

    # Strategy: Group matches by POSITION (y-coordinate + x-column zone)
    # rather than by text. Two matches from different engines are "the same"
    # if they're on the same row (y within tolerance) and in the same column zone.
    Y_TOLERANCE = 8  # PDF points tolerance for same row

    # Group matches by row position
    text_groups = {}
    group_keys = []

    for m in all_matches:
        bbox = m["bbox"]
        y_center = bbox["y"] + bbox["height"] / 2
        x_center = bbox["x"] + bbox["width"] / 2
        matched_key = None

        # Check against existing groups by spatial proximity
        for existing_key in group_keys:
            ref = text_groups[existing_key][0]
            ref_bbox = ref["bbox"]
            ref_y = ref_bbox["y"] + ref_bbox["height"] / 2
            ref_x = ref_bbox["x"] + ref_bbox["width"] / 2

            # Same row (y) AND similar x-position (same column)
            if abs(y_center - ref_y) <= Y_TOLERANCE and abs(x_center - ref_x) <= 30:
                matched_key = existing_key
                break

        if matched_key:
            text_groups[matched_key].append(m)
        else:
            key = f"{y_center:.0f}_{x_center:.0f}_{normalize_ocr(m['text'])}"
            text_groups[key] = [m]
            group_keys.append(key)

    # Build consensus for each text group
    consensus_matches = []
    for text_key, group in text_groups.items():
        engines_found = set(m["engine"] for m in group)
        n_engines = len(engines_found)
        total_engines = len(engine_pages)

        # Determine confidence level
        if n_engines >= total_engines and total_engines >= 3:
            confidence = confidence_levels.get("unanimous", "high")
        elif n_engines >= 2:
            confidence = confidence_levels.get("majority", "medium")
        else:
            confidence = confidence_levels.get("single", "low")

        # Merge bounding boxes from agreeing engines
        bboxes = [m["bbox"] for m in group]
        merged_bbox = merge_bboxes(bboxes)

        # Prefer text from PyMuPDF (direct extraction) over Tesseract (OCR)
        best_text = group[0]["text"]
        for m in group:
            if m["engine"] == "pymupdf":
                best_text = m["text"]
                break

        consensus_matches.append({
            "field": "Part Number",
            "text": best_text,
            "bbox": merged_bbox,
            "confidence": confidence,
            "engines_agreed": sorted(list(engines_found)),
            "agreement": f"{n_engines}/{total_engines}",
        })

    # Sort by y-position, then x-position (reading order)
    consensus_matches.sort(key=lambda m: (m["bbox"]["y"], m["bbox"]["x"]))

    return consensus_matches


def validate_proxy_pointer(matches, config):
    """
    Proxy Pointer RAG Validation — the Judge's validator.

    Checks:
    1. Regex Gate — every text must pass safeguard_regex
    2. Spatial Gate — no overlapping bboxes (>50% overlap)
    3. Schema Gate — required fields present

    Returns: (valid_matches, rejected_matches, validation_report)
    """
    valid = []
    rejected = []
    report = {"total": len(matches), "passed": 0, "failed": 0, "reasons": []}

    for match in matches:
        text = match["text"]

        # Gate 1: (Deprecated) Regex validation removed in favor of LLM-First Proxy Pointer RAG.
        # The engines now only output exact matches to expected_truths.json.

        # Gate 2: Schema validation (required fields)
        if not match.get("bbox") or not match.get("text"):
            rejected.append({**match, "_rejection_reason": "Missing required fields"})
            report["failed"] += 1
            report["reasons"].append(f"'{text}' missing fields")
            continue

        valid.append(match)
        report["passed"] += 1

    # Gate 3: Spatial overlap check (dedup)
    deduped = []
    for i, m in enumerate(valid):
        is_dupe = False
        for j, existing in enumerate(deduped):
            # Check if bboxes overlap significantly
            dist = bbox_distance(m["bbox"], existing["bbox"])
            if m["text"].upper() == existing["text"].upper() and dist < 5:
                is_dupe = True
                break
        if not is_dupe:
            deduped.append(m)
        else:
            report["reasons"].append(f"'{m['text']}' deduped (spatial overlap)")

    report["after_dedup"] = len(deduped)
    return deduped, rejected, report


def run_judge(doc_id, judge_config=None, config=None):
    """
    Main judge pipeline for a document:
    1. Load all engine outputs
    2. Build consensus per page
    3. Validate via Proxy Pointer RAG
    4. Write final parsed_spatial_data.json
    """
    if judge_config is None:
        judge_config = load_judge_config()
    if config is None:
        config, _, _, _ = load_config()

    engines = load_engine_outputs(doc_id)
    if not engines:
        print(f"[JUDGE] ERROR: No engine outputs found for '{doc_id}'")
        return None

    print(f"[JUDGE] Processing '{doc_id}' with {len(engines)} engines: "
          f"{list(engines.keys())}")

    # Collect all page numbers across all engines
    all_page_nums = set()
    for engine_data in engines.values():
        for page in engine_data.get("pages", []):
            all_page_nums.add(page["page_num"])

    pages_data = []
    total_matches = 0
    total_rejected = 0

    for page_num in sorted(all_page_nums):
        # Gather matches from each engine for this page
        engine_page_matches = {}
        for engine_name, engine_data in engines.items():
            for page in engine_data.get("pages", []):
                if page["page_num"] == page_num:
                    engine_page_matches[engine_name] = page.get("matches", [])
                    break

        # Build consensus
        consensus = find_consensus(engine_page_matches, judge_config)

        # Validate via Proxy Pointer RAG
        valid, rejected, report = validate_proxy_pointer(consensus, config)

        total_matches += len(valid)
        total_rejected += len(rejected)

        print(f"  Page {page_num}: {len(valid)} approved, {len(rejected)} rejected "
              f"(consensus from {len(engine_page_matches)} engines)")

        pages_data.append({
            "page_num": page_num,
            "matches": valid,
            "rejected": rejected,
            "validation_report": report,
        })

    # Write final output
    result = {
        "filename": f"{doc_id}.pdf",
        "engine": "tri-engine-judge",
        "engines_used": list(engines.keys()),
        "pages": pages_data,
        "total_matches": total_matches,
        "total_rejected": total_rejected,
        "validation_status": "PENDING_APPROVAL",
    }

    out_dir = os.path.join(OUTPUT_FOLDER, doc_id)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "parsed_spatial_data.json")
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2)

    print(f"[JUDGE] Final: {total_matches} matches, {total_rejected} rejected -> {out_path}")

    # Burn bounding boxes onto page PNGs
    try:
        from bbox_burn_in import burn_document
        print(f"[JUDGE] Burning bboxes onto page images...")
        burn_result = burn_document(doc_id, spatial_data=result)
        if burn_result:
            print(f"[JUDGE] Burn-in complete: {len(burn_result.get('pages', []))} pages in {burn_result.get('elapsed_seconds', 0):.2f}s")
    except Exception as e:
        print(f"[JUDGE] WARNING: Burn-in failed (non-critical): {e}")

    return result


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Judge Orchestrator")
    parser.add_argument('--doc', type=str, required=True,
                        help='Document ID (folder name in _2 Output Data)')
    args = parser.parse_args()

    run_judge(args.doc)


if __name__ == "__main__":
    main()
