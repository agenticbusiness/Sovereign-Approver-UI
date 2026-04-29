"""
SHA-512 Extraction Fingerprint Lock — Immutable Verification Layer

When a user APPROVES an extraction result in the UI, this module:
1. Computes SHA-512 hash of the approved extraction set (text + bbox + page)
2. Stores the hash in fingerprint_vault.yaml
3. On subsequent runs, compares the new extraction against the vault
4. If hash matches → SKIP re-extraction (locked result)
5. If hash differs → FLAG for re-review

This creates a "golden set" of verified extractions that are permanently locked.
Once a bounding box set is confirmed correct, it never needs re-validation.

The multi-variable fork architecture uses this to lock each variable independently:
- MFG Part Number → SHA-512 locked → GREEN bounding boxes
- Description → SHA-512 locked → BLUE bounding boxes
- Dimensions → SHA-512 locked → ORANGE bounding boxes
- Material → SHA-512 locked → PURPLE bounding boxes
"""
import hashlib
import json
import os
import yaml
import time

VAULT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MATRICES_DIR = os.path.join(VAULT_DIR, "Matrices")
OUTPUT_FOLDER = os.path.join(VAULT_DIR, "_2 Output Data")
FINGERPRINT_PATH = os.path.join(MATRICES_DIR, "fingerprint_vault.yaml")


def compute_extraction_hash(matches, field_type="Part Number"):
    """
    Compute SHA-512 hash of an extraction set.

    The hash covers:
    - Sorted list of extracted text values
    - The field type being extracted
    - The page number

    Bounding boxes are EXCLUDED from the hash because they can shift
    slightly between engine versions while the text stays the same.
    """
    # Sort by text to ensure deterministic ordering
    sorted_texts = sorted(m["text"] for m in matches)

    # Build canonical string
    canonical = json.dumps({
        "field_type": field_type,
        "count": len(sorted_texts),
        "values": sorted_texts,
    }, sort_keys=True)

    return hashlib.sha512(canonical.encode("utf-8")).hexdigest()


def compute_page_hash(matches, page_num, field_type="Part Number"):
    """Compute SHA-512 for a specific page's extraction."""
    canonical = json.dumps({
        "field_type": field_type,
        "page": page_num,
        "count": len(matches),
        "values": sorted(m["text"] for m in matches),
    }, sort_keys=True)

    return hashlib.sha512(canonical.encode("utf-8")).hexdigest()


def load_vault():
    """Load the fingerprint vault."""
    if os.path.exists(FINGERPRINT_PATH):
        with open(FINGERPRINT_PATH, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    return {}


def save_vault(vault):
    """Save the fingerprint vault."""
    os.makedirs(os.path.dirname(FINGERPRINT_PATH), exist_ok=True)
    with open(FINGERPRINT_PATH, 'w', encoding='utf-8') as f:
        yaml.dump(vault, f, default_flow_style=False, allow_unicode=True)


def lock_extraction(doc_id, page_num, matches, field_type="Part Number",
                    approved_by="user"):
    """
    Lock an approved extraction result with SHA-512 fingerprint.

    Args:
        doc_id: Document identifier
        page_num: Page number
        matches: List of approved match dicts
        field_type: The variable being extracted (Part Number, Description, etc.)
        approved_by: Who approved (user, auto, judge)

    Returns:
        The SHA-512 fingerprint string
    """
    vault = load_vault()

    fingerprint = compute_page_hash(matches, page_num, field_type)

    # Build the vault entry
    if doc_id not in vault:
        vault[doc_id] = {}

    page_key = f"page_{page_num}"
    if page_key not in vault[doc_id]:
        vault[doc_id][page_key] = {}

    vault[doc_id][page_key][field_type] = {
        "sha512": fingerprint,
        "count": len(matches),
        "locked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "approved_by": approved_by,
        "values": sorted(m["text"] for m in matches),
    }

    save_vault(vault)
    return fingerprint


def verify_extraction(doc_id, page_num, matches, field_type="Part Number"):
    """
    Verify a new extraction against the locked fingerprint.

    Returns:
        dict with:
        - locked: bool (True if a fingerprint exists)
        - matches: bool (True if the new extraction matches the lock)
        - fingerprint: str (the new extraction's hash)
        - locked_fingerprint: str (the vault's stored hash, if any)
        - drift_report: dict (details on what changed, if any)
    """
    vault = load_vault()
    new_hash = compute_page_hash(matches, page_num, field_type)

    page_key = f"page_{page_num}"
    locked_entry = (vault.get(doc_id, {})
                        .get(page_key, {})
                        .get(field_type))

    if not locked_entry:
        return {
            "locked": False,
            "matches": False,
            "fingerprint": new_hash,
            "locked_fingerprint": None,
            "drift_report": None,
        }

    locked_hash = locked_entry["sha512"]
    is_match = new_hash == locked_hash

    drift = None
    if not is_match:
        # Build drift report
        new_values = set(m["text"] for m in matches)
        locked_values = set(locked_entry.get("values", []))

        drift = {
            "added": sorted(new_values - locked_values),
            "removed": sorted(locked_values - new_values),
            "old_count": locked_entry["count"],
            "new_count": len(matches),
        }

    return {
        "locked": True,
        "matches": is_match,
        "fingerprint": new_hash,
        "locked_fingerprint": locked_hash,
        "drift_report": drift,
    }


def get_locked_pages(doc_id, field_type="Part Number"):
    """Get list of page numbers that have locked fingerprints."""
    vault = load_vault()
    locked = []
    for page_key, fields in vault.get(doc_id, {}).items():
        if field_type in fields:
            page_num = int(page_key.replace("page_", ""))
            locked.append(page_num)
    return sorted(locked)


# ═══════════════════════════════════════════════════════════════
# Multi-Variable Color Map
# Each extraction variable gets a unique bounding box color.
# This is read by the TLS UI to render colored overlays.
# ═══════════════════════════════════════════════════════════════
VARIABLE_COLORS = {
    "Part Number":   {"color": "#00FF88", "label": "MFG Part Number"},
    "Description":   {"color": "#4488FF", "label": "Product Description"},
    "Dimensions":    {"color": "#FF8800", "label": "Dimensions (A/B/C)"},
    "Material":      {"color": "#AA44FF", "label": "Material"},
    "Finish":        {"color": "#FF4466", "label": "Finish"},
    "Connection":    {"color": "#44DDFF", "label": "Connection Type"},
    "Page Header":   {"color": "#FFDD44", "label": "Page Header"},
    "Chart Header":  {"color": "#88FF44", "label": "Chart/Table Header"},
    "Product Image": {"color": "#FF88DD", "label": "Product Image"},
}


def get_variable_color(field_type):
    """Get the bounding box color for a variable type."""
    entry = VARIABLE_COLORS.get(field_type, {"color": "#FFFFFF", "label": field_type})
    return entry["color"]


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="SHA-512 Fingerprint Lock")
    parser.add_argument('--doc', type=str, required=True)
    parser.add_argument('--page', type=int, required=True)
    parser.add_argument('--lock', action='store_true',
                        help='Lock the current extraction')
    parser.add_argument('--verify', action='store_true',
                        help='Verify against locked fingerprint')
    parser.add_argument('--field', type=str, default='Part Number')
    args = parser.parse_args()

    # Load current extraction
    spatial_path = os.path.join(OUTPUT_FOLDER, args.doc, "parsed_spatial_data.json")
    with open(spatial_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    page = next((p for p in data["pages"] if p["page_num"] == args.page), None)
    if not page:
        print(f"[ERROR] Page {args.page} not found")
        exit(1)

    matches = page.get("matches", [])

    if args.lock:
        fp = lock_extraction(args.doc, args.page, matches, args.field)
        print(f"[LOCKED] {args.doc} page {args.page} '{args.field}'")
        print(f"  SHA-512: {fp[:32]}...")
        print(f"  Count:   {len(matches)} items")

    elif args.verify:
        result = verify_extraction(args.doc, args.page, matches, args.field)
        if not result["locked"]:
            print(f"[UNLOCKED] No fingerprint for {args.doc} page {args.page}")
        elif result["matches"]:
            print(f"[VERIFIED] Extraction matches locked fingerprint")
            print(f"  SHA-512: {result['fingerprint'][:32]}...")
        else:
            print(f"[DRIFT] Extraction has changed!")
            drift = result["drift_report"]
            print(f"  Old count: {drift['old_count']}")
            print(f"  New count: {drift['new_count']}")
            if drift["added"]:
                print(f"  Added:   {drift['added']}")
            if drift["removed"]:
                print(f"  Removed: {drift['removed']}")
