"""
Sovereign Pre-Flight Bounding Box Verifier
Runs 8 automated tests on parsed_spatial_data.json and injects
_preflight_score and _preflight_flags into each match.
Auto-approves matches scoring 90+.
"""
import os
import re
import json
import yaml
import statistics


def load_inference_regexes(inference_folder):
    """Load safeguard regexes from all inference YAML files."""
    regexes = {}
    if not os.path.exists(inference_folder):
        return regexes
    for f in os.listdir(inference_folder):
        if not f.endswith('.yaml'):
            continue
        try:
            with open(os.path.join(inference_folder, f), 'r', encoding='utf-8') as fh:
                data = yaml.safe_load(fh.read())
            for target in data.get('extraction_targets', []):
                field = target.get('field', '')
                regex = target.get('safeguard_regex', '')
                if field and regex:
                    regexes[field] = re.compile(regex)
        except Exception:
            pass
    return regexes


def test_regex_safeguard(match, regexes):
    """Test 1: Does extracted text match the inference regex?"""
    field = match.get('field', '')
    text = match.get('text', '')
    if field in regexes:
        if regexes[field].match(text):
            return 25, []
        else:
            return 0, [f"REGEX_FAIL: '{text}' doesn't match {field} pattern"]
    # No regex for this field — give partial credit
    return 15, []


def test_engine_consensus(match):
    """Test 2: How many engines agreed?"""
    engines = match.get('engines_agreed', [])
    confidence = match.get('confidence', 'low')
    if confidence == 'high' or len(engines) >= 3:
        return 30, []
    elif confidence == 'medium' or len(engines) == 2:
        return 20, ["CONSENSUS_MEDIUM: 2/3 engines agreed"]
    else:
        return 5, ["CONSENSUS_LOW: Only 1 engine found this match"]


def test_spatial_alignment(match, column_clusters):
    """Test 3: Is the bbox X-coordinate in a known column cluster?"""
    bbox = match.get('bbox')
    if not bbox or not column_clusters:
        return 10, []  # Can't test, give partial credit

    x = bbox['x']
    tolerance = 15  # px
    for cluster_x in column_clusters:
        if abs(x - cluster_x) <= tolerance:
            return 15, []
    return 0, [f"SPATIAL_OUTLIER: x={x:.1f} not in any column cluster"]


def test_bbox_dimensions(match, height_mean, height_std):
    """Test 4: Is bbox height consistent with page average?"""
    bbox = match.get('bbox')
    if not bbox or height_std == 0:
        return 7, []

    h = bbox['height']
    z_score = abs(h - height_mean) / max(height_std, 0.1)
    if z_score <= 1.5:
        return 10, []
    elif z_score <= 3.0:
        return 5, [f"BBOX_HEIGHT_WARN: h={h:.1f} (z={z_score:.1f})"]
    else:
        return 0, [f"BBOX_HEIGHT_OUTLIER: h={h:.1f} (z={z_score:.1f})"]


def test_duplicates(match, text_counts):
    """Test 5: Is this text unique on the page?"""
    text = match.get('text', '')
    count = text_counts.get(text, 1)
    if count == 1:
        return 5, []
    elif count == 2:
        return 3, [f"DUPLICATE_WARN: '{text}' appears {count}x on page"]
    else:
        return 0, [f"DUPLICATE_MULTI: '{text}' appears {count}x on page"]


def test_page_count_parity(page_match_count, doc_mean, doc_std):
    """Test 6: Does this page have a normal number of matches?"""
    if doc_std == 0:
        return 5, []
    z_score = abs(page_match_count - doc_mean) / max(doc_std, 0.1)
    if z_score <= 1.5:
        return 5, []
    elif z_score <= 3.0:
        return 3, [f"PAGE_COUNT_WARN: {page_match_count} matches (z={z_score:.1f})"]
    else:
        return 0, [f"PAGE_COUNT_OUTLIER: {page_match_count} matches (z={z_score:.1f})"]


def test_bbox_overlap(match, all_bboxes_on_page, match_index):
    """Test 7: Does this bbox overlap significantly with another?"""
    bbox = match.get('bbox')
    if not bbox:
        return 3, []

    x1, y1 = bbox['x'], bbox['y']
    w1, h1 = bbox['width'], bbox['height']
    area1 = w1 * h1

    for i, other_bbox in enumerate(all_bboxes_on_page):
        if i == match_index or not other_bbox:
            continue
        x2, y2 = other_bbox['x'], other_bbox['y']
        w2, h2 = other_bbox['width'], other_bbox['height']

        # Calculate intersection
        ix = max(0, min(x1 + w1, x2 + w2) - max(x1, x2))
        iy = max(0, min(y1 + h1, y2 + h2) - max(y1, y2))
        intersection = ix * iy

        if area1 > 0 and intersection / area1 > 0.5:
            return 0, [f"BBOX_OVERLAP: >50% overlap with match {i}"]

    return 5, []


def test_text_length(match):
    """Test 8: Is the text a plausible length?"""
    text = match.get('text', '')
    length = len(text)
    if 3 <= length <= 30:
        return 5, []
    elif 1 <= length <= 2:
        return 2, [f"TEXT_SHORT: '{text}' is only {length} chars"]
    elif length > 30:
        return 2, [f"TEXT_LONG: '{text}' is {length} chars"]
    else:
        return 0, [f"TEXT_EMPTY: no text extracted"]


def test_truth_count_parity(page_match_count, expected_truth_count):
    """Test 9: Does the judge's match count equal the LLM truth count?
    This is the strongest signal — if the LLM saw N part numbers
    and we found N bounding boxes, we're likely correct."""
    if expected_truth_count is None or expected_truth_count == 0:
        return 0, ["TRUTH_MISSING: No expected truths for this page"]
    
    if page_match_count == expected_truth_count:
        return 10, []  # Perfect parity
    
    delta = abs(page_match_count - expected_truth_count)
    pct = delta / expected_truth_count * 100
    
    if pct <= 10:
        return 7, [f"TRUTH_CLOSE: {page_match_count}/{expected_truth_count} ({pct:.0f}% delta)"]
    elif pct <= 25:
        return 3, [f"TRUTH_DRIFT: {page_match_count}/{expected_truth_count} ({pct:.0f}% delta)"]
    else:
        return 0, [f"TRUTH_MISMATCH: {page_match_count}/{expected_truth_count} ({pct:.0f}% delta)"]


def test_graphic_text_detection(match, is_tesseract_only):
    """Test 10: Was this match found ONLY by Tesseract (OCR)?
    If so, it's likely graphic-rendered text — still valid, but flagged
    for awareness. Not a penalty, just metadata."""
    if is_tesseract_only:
        return 5, ["GRAPHIC_TEXT: Found by OCR only (likely vector-rendered)"]
    return 5, []


def load_expected_truths_for_doc(doc_data):
    """Load expected truths if path is available in doc_data or on disk."""
    doc_id = doc_data.get('filename', '').replace('.pdf', '')
    if not doc_id:
        return {}
    vault_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    truths_path = os.path.join(vault_dir, "_2 Output Data", doc_id, "expected_truths.json")
    if os.path.exists(truths_path):
        with open(truths_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def compute_column_clusters(matches, tolerance=15):
    """Cluster X-coordinates to identify table columns."""
    x_vals = []
    for m in matches:
        bbox = m.get('bbox')
        if bbox:
            x_vals.append(bbox['x'])

    if not x_vals:
        return []

    x_vals.sort()
    clusters = []
    current_cluster = [x_vals[0]]

    for x in x_vals[1:]:
        if x - current_cluster[-1] <= tolerance:
            current_cluster.append(x)
        else:
            clusters.append(statistics.mean(current_cluster))
            current_cluster = [x]
    clusters.append(statistics.mean(current_cluster))
    return clusters


def verify_document(doc_data, inference_folder):
    """
    Run all 10 pre-flight tests on a document's parsed_spatial_data.
    Mutates the data in-place, adding _preflight_score and _preflight_flags.
    Returns summary statistics.
    """
    regexes = load_inference_regexes(inference_folder)
    pages = doc_data.get('pages', [])

    # Load expected truths for count parity
    expected_truths = load_expected_truths_for_doc(doc_data)
    truth_pages = expected_truths.get('pages', {})

    # Document-level stats for page count parity
    page_counts = [len(p.get('matches', [])) for p in pages]
    pages_with_data = [c for c in page_counts if c > 0]
    doc_mean = statistics.mean(pages_with_data) if pages_with_data else 0
    doc_std = statistics.stdev(pages_with_data) if len(pages_with_data) > 1 else 0

    total_matches = 0
    auto_approved = 0
    flagged = 0
    red_flagged = 0
    graphic_text_count = 0

    for page in pages:
        matches = page.get('matches', [])
        if not matches:
            continue

        page_num = page.get('page_num', 0)

        # Get expected truth count for this page
        page_truth = truth_pages.get(str(page_num), {})
        expected_count = page_truth.get('page_count') if isinstance(page_truth, dict) else None

        # Page-level stats
        heights = [m['bbox']['height'] for m in matches if m.get('bbox')]
        height_mean = statistics.mean(heights) if heights else 0
        height_std = statistics.stdev(heights) if len(heights) > 1 else 0

        text_counts = {}
        for m in matches:
            t = m.get('text', '')
            text_counts[t] = text_counts.get(t, 0) + 1

        column_clusters = compute_column_clusters(matches)
        all_bboxes = [m.get('bbox') for m in matches]

        for i, match in enumerate(matches):
            total_matches += 1
            score = 0
            flags = []

            # Run all 10 tests
            s, f = test_regex_safeguard(match, regexes)
            score += s; flags.extend(f)

            s, f = test_engine_consensus(match)
            score += s; flags.extend(f)

            s, f = test_spatial_alignment(match, column_clusters)
            score += s; flags.extend(f)

            s, f = test_bbox_dimensions(match, height_mean, height_std)
            score += s; flags.extend(f)

            s, f = test_duplicates(match, text_counts)
            score += s; flags.extend(f)

            s, f = test_page_count_parity(len(matches), doc_mean, doc_std)
            score += s; flags.extend(f)

            s, f = test_bbox_overlap(match, all_bboxes, i)
            score += s; flags.extend(f)

            s, f = test_text_length(match)
            score += s; flags.extend(f)

            # Test 9: Truth count parity (page-level, applied to each match)
            s, f = test_truth_count_parity(len(matches), expected_count)
            score += s; flags.extend(f)

            # Test 10: Graphic text detection
            engines = match.get('engines_agreed', [])
            is_tesseract_only = engines == ['tesseract']
            s, f = test_graphic_text_detection(match, is_tesseract_only)
            score += s; flags.extend(f)
            if is_tesseract_only:
                graphic_text_count += 1

            # Inject into match data
            match['_preflight_score'] = score
            match['_preflight_flags'] = flags

            # Auto-approve threshold (now max score is 110)
            if score >= 95:
                match['_status'] = 'approved'
                auto_approved += 1
            elif score < 55:
                red_flagged += 1
            else:
                flagged += 1

    summary = {
        'total_matches': total_matches,
        'auto_approved': auto_approved,
        'flagged': flagged,
        'red_flagged': red_flagged,
        'graphic_text_detected': graphic_text_count,
        'auto_approve_rate': round(auto_approved / max(total_matches, 1) * 100, 1),
        'pages_analyzed': len([p for p in pages if len(p.get('matches', [])) > 0]),
    }
    return summary


if __name__ == "__main__":
    import sys
    # CLI usage: python preflight_verifier.py <parsed_spatial_data.json>
    if len(sys.argv) < 2:
        print("Usage: python preflight_verifier.py <parsed_spatial_data.json>")
        sys.exit(1)

    json_path = sys.argv[1]
    workspace = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    inference_folder = os.path.join(workspace, "_1.1 INFERENCE FILES")

    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    summary = verify_document(data, inference_folder)

    print(f"\n=== PRE-FLIGHT VERIFICATION SUMMARY ===")
    print(f"  Total matches:      {summary['total_matches']}")
    print(f"  Auto-approved (90+): {summary['auto_approved']} ({summary['auto_approve_rate']}%)")
    print(f"  Flagged (50-89):    {summary['flagged']}")
    print(f"  Red-flagged (<50):  {summary['red_flagged']}")
    print(f"  Pages analyzed:     {summary['pages_analyzed']}")

    # Write verified data back
    out_path = json_path.replace('.json', '_verified.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    print(f"\n  Verified data -> {out_path}")
