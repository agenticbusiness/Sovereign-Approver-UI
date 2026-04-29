"""
Feedback Manager — Self-evolving system that processes UI approvals/rejections
and updates the evolution files in Matrices/.

Actions:
- Approvals -> known_parts_whitelist.yaml (auto-add confirmed parts)
- Rejections -> exclusion_terms.yaml (auto-add false positives)
- Rejections with column notes -> column_overrides.yaml
- All feedback -> feedback_ledger.json (audit trail)
- Engine scoring -> engine_scores.yaml (track accuracy per engine)
"""
import json
import os
import sys
import yaml
import datetime

VAULT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MATRICES_DIR = os.path.join(VAULT_DIR, "Matrices")
OUTPUT_DIR = os.path.join(VAULT_DIR, "_2 Output Data")
LEDGER_PATH = os.path.join(OUTPUT_DIR, "feedback_ledger.json")


def load_ledger():
    """Load or initialize the feedback ledger."""
    if os.path.exists(LEDGER_PATH):
        with open(LEDGER_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"entries": [], "stats": {"total_approvals": 0, "total_rejections": 0}}


def save_ledger(ledger):
    """Persist the feedback ledger."""
    with open(LEDGER_PATH, 'w', encoding='utf-8') as f:
        json.dump(ledger, f, indent=2)


def load_yaml(filename):
    """Load a YAML file from Matrices/."""
    path = os.path.join(MATRICES_DIR, filename)
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    return {}


def save_yaml(filename, data):
    """Save a YAML file to Matrices/."""
    path = os.path.join(MATRICES_DIR, filename)
    with open(path, 'w', encoding='utf-8') as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)


def record_approval(doc_id, page_num, match_index, match_data, engine_source=None):
    """
    Process an approval:
    1. Add part number to whitelist
    2. Record in feedback ledger
    3. Update engine scores
    """
    text = match_data.get("text", "")
    ledger = load_ledger()

    # 1. Add to whitelist
    whitelist = load_yaml("known_parts_whitelist.yaml")
    parts = set(whitelist.get("parts", []))
    if text and text not in parts:
        parts.add(text)
        whitelist["parts"] = sorted(list(parts))
        save_yaml("known_parts_whitelist.yaml", whitelist)
        print(f"  [FEEDBACK] Added '{text}' to whitelist")

    # 2. Record in ledger
    entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "doc_id": doc_id,
        "page_num": page_num,
        "match_index": match_index,
        "action": "approved",
        "text": text,
        "match_data": match_data,
        "engine_source": engine_source,
    }
    ledger["entries"].append(entry)
    ledger["stats"]["total_approvals"] += 1
    save_ledger(ledger)

    # 3. Update engine scores (if we know which engines found it)
    engines_agreed = match_data.get("engines_agreed", [])
    if engines_agreed:
        scores = load_yaml("engine_scores.yaml")
        for engine in engines_agreed:
            if engine in scores.get("engines", {}):
                scores["engines"][engine]["correct"] += 1
                scores["engines"][engine]["total_matches"] += 1
                total = scores["engines"][engine]["total_matches"]
                correct = scores["engines"][engine]["correct"]
                scores["engines"][engine]["accuracy"] = round(correct / total, 3) if total > 0 else 0
        save_yaml("engine_scores.yaml", scores)

    return entry


def record_rejection(doc_id, page_num, match_index, match_data, notes="",
                     engine_source=None):
    """
    Process a rejection:
    1. Analyze rejection notes for auto-learning
    2. Add to exclusion terms if applicable
    3. Record in feedback ledger
    4. Update engine scores
    """
    text = match_data.get("text", "")
    ledger = load_ledger()

    # 1. Auto-learn from rejection notes
    notes_lower = notes.lower() if notes else ""
    if any(term in notes_lower for term in ["pack", "quantity", "count", "not a part",
                                             "false positive", "wrong"]):
        # Add to exclusion terms
        exclusions = load_yaml("exclusion_terms.yaml")
        terms = set(exclusions.get("terms", []))
        if text and text.upper() not in terms:
            terms.add(text.upper())
            exclusions["terms"] = sorted(list(terms))
            save_yaml("exclusion_terms.yaml", exclusions)
            print(f"  [FEEDBACK] Added '{text}' to exclusion_terms")

    if any(term in notes_lower for term in ["column", "wrong column", "position"]):
        # Flag for column override review
        print(f"  [FEEDBACK] Column override flagged for '{doc_id}' page {page_num}")

    # 2. Record in ledger
    entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "doc_id": doc_id,
        "page_num": page_num,
        "match_index": match_index,
        "action": "rejected",
        "text": text,
        "notes": notes,
        "match_data": match_data,
        "engine_source": engine_source,
    }
    ledger["entries"].append(entry)
    ledger["stats"]["total_rejections"] += 1
    save_ledger(ledger)

    # 3. Update engine scores
    engines_agreed = match_data.get("engines_agreed", [])
    if engines_agreed:
        scores = load_yaml("engine_scores.yaml")
        for engine in engines_agreed:
            if engine in scores.get("engines", {}):
                scores["engines"][engine]["incorrect"] += 1
                scores["engines"][engine]["total_matches"] += 1
                total = scores["engines"][engine]["total_matches"]
                correct = scores["engines"][engine]["correct"]
                scores["engines"][engine]["accuracy"] = round(correct / total, 3) if total > 0 else 0
        save_yaml("engine_scores.yaml", scores)

    return entry


def get_stats():
    """Get current feedback statistics."""
    ledger = load_ledger()
    scores = load_yaml("engine_scores.yaml")
    whitelist = load_yaml("known_parts_whitelist.yaml")
    exclusions = load_yaml("exclusion_terms.yaml")

    return {
        "ledger_stats": ledger.get("stats", {}),
        "total_entries": len(ledger.get("entries", [])),
        "engine_scores": scores.get("engines", {}),
        "whitelist_count": len(whitelist.get("parts", [])),
        "exclusion_count": len(exclusions.get("terms", [])),
    }


if __name__ == "__main__":
    stats = get_stats()
    print(json.dumps(stats, indent=2))
