"""
Column-Position Filter — Shared module for all 3 extraction engines.
Identifies table headers, computes column boundaries, and filters
text spans to only target columns (BLACK, GALVANIZED, etc).

Used by: engine_tesseract.py, engine_pymupdf.py
LiteParse (JS) has its own port of this logic.

Reads config from Matrices/parse_request.yaml for target/exclude columns.
Reads Matrices/exclusion_terms.yaml for known false positives.
Reads Matrices/known_parts_whitelist.yaml for pre-approved part numbers.
"""
import os
import re
import yaml
import json

VAULT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MATRICES_DIR = os.path.join(VAULT_DIR, "Matrices")


def load_config():
    """Load parse_request.yaml and evolution files."""
    config_path = os.path.join(MATRICES_DIR, "parse_request.yaml")
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    exclusions_path = os.path.join(MATRICES_DIR, "exclusion_terms.yaml")
    exclusion_terms = set()
    if os.path.exists(exclusions_path):
        with open(exclusions_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}
            exclusion_terms = set(data.get("terms", []))

    whitelist_path = os.path.join(MATRICES_DIR, "known_parts_whitelist.yaml")
    whitelist = set()
    if os.path.exists(whitelist_path):
        with open(whitelist_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}
            whitelist = set(data.get("parts", []))

    overrides_path = os.path.join(MATRICES_DIR, "column_overrides.yaml")
    overrides = {}
    if os.path.exists(overrides_path):
        with open(overrides_path, 'r', encoding='utf-8') as f:
            overrides = yaml.safe_load(f) or {}

    return config, exclusion_terms, whitelist, overrides


def find_headers(text_spans, target_columns, exclude_columns):
    """
    Scan text spans for known column headers and return their positions.

    Args:
        text_spans: list of dicts with 'text' and 'bbox' (x0, y0, x1, y1)
        target_columns: set of header names we WANT
        exclude_columns: set of header names we EXCLUDE

    Returns:
        list of dicts: [{"name": str, "x_center": float, "x0": float,
                         "x1": float, "y": float, "is_target": bool}]
    """
    all_known = target_columns | exclude_columns
    headers = []
    seen = set()

    for span in text_spans:
        text = span["text"].strip().upper()
        bbox = span["bbox"]
        x_center = (bbox[0] + bbox[2]) / 2

        for header in all_known:
            if text == header and header not in seen:
                seen.add(header)
                headers.append({
                    "name": header,
                    "x_center": x_center,
                    "x0": bbox[0],
                    "x1": bbox[2],
                    "y": bbox[1],
                    "is_target": header in target_columns,
                })
                break

    return sorted(headers, key=lambda h: h["x_center"])


def compute_column_ranges(headers, page_width):
    """
    From identified headers, compute x-coordinate ranges for target columns.

    Returns:
        list of dicts: [{"column": str, "x_left": float, "x_right": float,
                         "header_y": float}]
        Returns None if no headers found.
    """
    if not headers:
        return None

    target_ranges = []
    for i, h in enumerate(headers):
        if not h["is_target"]:
            continue

        # Left boundary: midpoint to previous header, or page left edge
        if i > 0:
            x_left = (headers[i - 1]["x_center"] + h["x_center"]) / 2
        else:
            x_left = 0

        # Right boundary: midpoint to next header, or page right edge
        if i < len(headers) - 1:
            x_right = (h["x_center"] + headers[i + 1]["x_center"]) / 2
        else:
            x_right = page_width

        target_ranges.append({
            "column": h["name"],
            "x_left": x_left,
            "x_right": x_right,
            "header_y": h["y"],
        })

    return target_ranges


def is_in_target_column(bbox, target_ranges):
    """
    Check if a text span's bounding box falls within a target column.

    Args:
        bbox: tuple (x0, y0, x1, y1)
        target_ranges: list from compute_column_ranges()

    Returns:
        bool
    """
    if target_ranges is None:
        return True  # No headers found — allow all (regex-only mode)

    x_center = (bbox[0] + bbox[2]) / 2
    y = bbox[1]

    for tr in target_ranges:
        if y > tr["header_y"] and tr["x_left"] <= x_center <= tr["x_right"]:
            return True

    return False


def is_valid_part_number(text, config, exclusion_terms, whitelist):
    """
    Validate text against Proxy Pointer RAG safeguard regex and evolution files.

    Args:
        text: the candidate string
        config: parse_request.yaml contents
        exclusion_terms: set of known false positives
        whitelist: set of pre-approved part numbers

    Returns:
        bool
    """
    text = text.strip()

    # Quick checks
    if len(text) < 3 or len(text) > 20:
        return False

    if text.upper() in exclusion_terms:
        return False

    # Whitelist override — pre-approved parts always pass
    if text in whitelist:
        return True

    # Test against each extraction target's safeguard_regex
    for target in config.get("extraction_targets", []):
        if target.get("field") == "Part Number":
            regex = target.get("safeguard_regex", "")
            if regex and re.match(regex, text):
                return True

    return False


def load_expected_truths(doc_id):
    """Load LLM-first expected truths for the document."""
    if not doc_id:
        return None
    truths_path = os.path.join(VAULT_DIR, "_2 Output Data", doc_id, "expected_truths.json")
    if os.path.exists(truths_path):
        with open(truths_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None


def filter_spans(text_spans, page_width, config=None, exclusion_terms=None,
                 whitelist=None, overrides=None, doc_id=None, page_num=None):
    """
    Full filtering pipeline: NOW USING LLM-FIRST EXPECTED TRUTHS.
    """
    expected_data = load_expected_truths(doc_id)
    expected_truths = []
    if expected_data and str(page_num) in expected_data.get("pages", {}):
        page_data = expected_data["pages"][str(page_num)]
        if isinstance(page_data, dict):
            parts_list = page_data.get("part_numbers", [])
        else:
            parts_list = page_data  # Fallback to old format
        expected_truths = [str(t).strip() for t in parts_list]

    matches = []
    
    # If no truths were found by the LLM, we shouldn't guess with regex.
    if not expected_truths:
        return matches, [], []

    import difflib

    # ── CCO-UPC HALLUCINATION DETECTION PROTOCOL ──
    # Two-tier fuzzy matching system:
    #   TIER 1 (≥88%): Auto-accept. Minor OCR spacing / single-char deviation.
    #   TIER 2 (≥80% & <88%, string ≥6 chars): Flag for VISUAL REVIEW.
    #     This covers ~1 char deviation per 5-6 chars — rare but real LLM hallucinations.
    #     The match is ACCEPTED but tagged with confidence="review_required" so the
    #     UI and downstream consumers can surface it for human confirmation.
    hallucination_flags = []  # Collected for reporting

    for span in text_spans:
        text = span["text"].strip()
        bbox = span["bbox"]  # (x0, y0, x1, y1)

        # EXACT MATCH against LLM Truths
        # We strip all spaces to handle OCR spacing issues (e.g., "1410 N" vs "1410N")
        normalized_text = text.replace(" ", "").upper()
        
        # Check against normalized expected truths
        matched_truth = None
        match_confidence = "high"
        match_llm_original = None
        for t in expected_truths:
            t_norm = t.replace(" ", "").upper()
            if t_norm == normalized_text:
                matched_truth = text
                match_confidence = "high"
                break
            # TIER 1: Auto-accept for very close matches (≥88%, len ≥ 6)
            # 88% on 6+ chars safely catches 1 character addition/deletion (e.g. 10 vs 9 chars = 94%)
            elif len(normalized_text) >= 6 and difflib.SequenceMatcher(None, t_norm, normalized_text).ratio() >= 0.88:
                print(f"    [INFERENCE] Auto-corrected LLM typo: '{t_norm}' -> '{normalized_text}'")
                matched_truth = text
                match_confidence = "high"
                match_llm_original = t
                hallucination_flags.append({
                    "tier": 1,
                    "llm_said": t,
                    "pdf_has": text,
                    "similarity": round(difflib.SequenceMatcher(None, t_norm, normalized_text).ratio(), 3),
                    "action": "auto_corrected"
                })
                break
            # TIER 2: Flag for visual review (≥79%, len ≥ 5)
            # 79% on 5 chars catches exactly 1 swapped character (4/5 match = 80%).
            # We include 5 chars here because part numbers at 5 chars with 1 typo should definitely be flagged for review.
            elif len(normalized_text) >= 5 and difflib.SequenceMatcher(None, t_norm, normalized_text).ratio() >= 0.79:
                print(f"    [REVIEW FLAG] Possible LLM hallucination: '{t_norm}' vs PDF '{normalized_text}' "
                      f"(sim={difflib.SequenceMatcher(None, t_norm, normalized_text).ratio():.2f}) — flagged for visual review")
                matched_truth = text
                match_confidence = "review_required"
                match_llm_original = t
                hallucination_flags.append({
                    "tier": 2,
                    "llm_said": t,
                    "pdf_has": text,
                    "similarity": round(difflib.SequenceMatcher(None, t_norm, normalized_text).ratio(), 3),
                    "action": "flagged_for_review"
                })
                break
                
        if matched_truth:
            match_entry = {
                "field": "Part Number",
                "text": matched_truth,
                "bbox": {
                    "x": round(bbox[0], 2),
                    "y": round(bbox[1], 2),
                    "width": round(bbox[2] - bbox[0], 2),
                    "height": round(bbox[3] - bbox[1], 2),
                },
                "confidence": match_confidence,
            }
            if match_llm_original:
                match_entry["llm_original"] = match_llm_original
            matches.append(match_entry)

    # Report hallucination flags summary
    if hallucination_flags:
        t1 = [f for f in hallucination_flags if f["tier"] == 1]
        t2 = [f for f in hallucination_flags if f["tier"] == 2]
        if t1:
            print(f"    [HALLUCINATION REPORT] Tier-1 auto-corrected: {len(t1)} items")
        if t2:
            print(f"    [HALLUCINATION REPORT] Tier-2 REVIEW REQUIRED: {len(t2)} items")
            for flag in t2:
                print(f"      ⚠ LLM said '{flag['llm_said']}' but PDF has '{flag['pdf_has']}' (sim={flag['similarity']})")

    return matches, [], hallucination_flags
