import os
import sys
import json
import fitz
import time
import base64
import io
import requests
from dotenv import load_dotenv

VAULT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = r"C:\_0 SH-WF-Global gemini.md\_6 env\FULL.env"
INPUT_FOLDER = os.path.join(VAULT_DIR, "_1 INPUT FOLDER")
OUTPUT_FOLDER = os.path.join(VAULT_DIR, "_2 Output Data")

load_dotenv(ENV_PATH)
API_KEY = os.getenv("GOOGLE_API_KEY")
MODEL = os.getenv("LLM_MODEL", "gemini-2.5-flash")

if not API_KEY:
    print("[FATAL] GOOGLE_API_KEY not found in FULL.env")
    sys.exit(1)


def render_page_to_base64(page, dpi=150):
    """Render a PDF page to a base64-encoded PNG for Gemini Vision."""
    pix = page.get_pixmap(dpi=dpi)
    img_bytes = pix.tobytes("png")
    return base64.b64encode(img_bytes).decode("utf-8")


def query_gemini_vision(prompt_text, image_b64):
    """Send multimodal (text + image) request to Gemini Vision API."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={API_KEY}"
    headers = {"Content-Type": "application/json"}
    data = {
        "contents": [{
            "parts": [
                {"text": prompt_text},
                {"inlineData": {"mimeType": "image/png", "data": image_b64}}
            ]
        }],
        "generationConfig": {"temperature": 0.0, "response_mime_type": "application/json"}
    }

    for attempt in range(5):
        try:
            response = requests.post(url, headers=headers, json=data, timeout=60)
            if response.status_code == 429:
                print(f"  [WARNING] Rate limited. Retrying in 10s... (Attempt {attempt+1}/5)")
                time.sleep(10)
                continue
            response.raise_for_status()
            resp_json = response.json()
            if "candidates" in resp_json and len(resp_json["candidates"]) > 0:
                content = resp_json["candidates"][0]["content"]["parts"][0]["text"]
                return content
            else:
                return "[]"
        except Exception as e:
            print(f"  [ERROR] Gemini Vision API call failed: {e}")
            if "429" in str(e):
                time.sleep(10)
                continue
            return "[]"
    return "[]"


def query_gemini(prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={API_KEY}"
    headers = {"Content-Type": "application/json"}
    data = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.0, "response_mime_type": "application/json"}
    }
    
    for attempt in range(5):
        try:
            response = requests.post(url, headers=headers, json=data, timeout=30)
            if response.status_code == 429:
                print(f"  [WARNING] Rate limited. Retrying in 10s... (Attempt {attempt+1}/5)")
                time.sleep(10)
                continue
            response.raise_for_status()
            resp_json = response.json()
            if "candidates" in resp_json and len(resp_json["candidates"]) > 0:
                content = resp_json["candidates"][0]["content"]["parts"][0]["text"]
                return content
            else:
                return "[]"
        except Exception as e:
            print(f"  [ERROR] Gemini API call failed: {e}")
            if "429" in str(e):
                time.sleep(10)
                continue
            return "[]"
    return "[]"

def extract_truths(target_file=None, pages_arg=None):
    target_pages = []
    if pages_arg:
        target_pages = [int(p.strip()) for p in pages_arg.split(',')]
        
    print("==========================================================")
    print("   SOVEREIGN ENGINE: LLM PROXY POINTER TRUTH EXTRACTOR")
    print("==========================================================\n")

    for fname in os.listdir(INPUT_FOLDER):
        if not fname.lower().endswith('.pdf'):
            continue
        if target_file and fname != target_file:
            continue
        
        doc_id = fname[:-4]
        pdf_path = os.path.join(INPUT_FOLDER, fname)
        out_dir = os.path.join(OUTPUT_FOLDER, doc_id)
        os.makedirs(out_dir, exist_ok=True)
        
        doc = fitz.open(pdf_path)
        print(f"[TRUTH EXTRACTOR] Processing: {fname}")
        
        out_path = os.path.join(out_dir, "expected_truths.json")
        expected_truths = {
            "document_id": doc_id,
            "total_document_count": 0,
            "pages": {}
        }
        if os.path.exists(out_path):
            try:
                with open(out_path, 'r', encoding='utf-8') as f:
                    expected_truths = json.load(f)
            except Exception as e:
                print(f"  [WARNING] Failed to load existing truths: {e}")
        
        for page_num in range(len(doc)):
            if target_pages and (page_num + 1) not in target_pages:
                continue
                
            page = doc[page_num]
            text = page.get_text("text")
            
            # Render page to image for vision extraction
            image_b64 = render_page_to_base64(page, dpi=150)
            
            # Save the rendered page PNG (we're already rendering for vision)
            pages_dir = os.path.join(out_dir, "pages")
            os.makedirs(pages_dir, exist_ok=True)
            png_path = os.path.join(pages_dir, f"{page_num + 1}.png")
            if not os.path.exists(png_path):
                pix = page.get_pixmap(dpi=150)
                pix.save(png_path)
            
            # Skip blank pages (check both text and image content)
            has_text = len(text.strip()) >= 10
            has_images = len(page.get_images(full=True)) > 0
            
            if not has_text and not has_images:
                expected_truths["pages"][str(page_num + 1)] = {
                    "page_count": 0,
                    "part_numbers": [],
                    "extraction_mode": "skipped_blank"
                }
                continue
            
            # DUAL-MODE EXTRACTION: Vision (primary) + Text (fallback)
            vision_prompt = """You are a strict Data Extraction Engine. Look at this PDF spec sheet page image.
Extract ALL unique Product Part Numbers visible anywhere on the page.
CRITICAL RULES:
1. Part numbers are typically alphanumeric codes in table cells under columns like 'PART NO', 'PART NUMBER', 'MFG P/N', 'SKU', 'ITEM', 'CAT. NO.', 'MODEL', 'STOCK CODE'.
2. Ignore headers, footers, section titles, descriptions, sizes, quantities, and prices.
3. Ignore general catalog terms like 'DUTY', 'HEAVY', 'COLOR', 'PACKING'.
4. Include ALL part numbers even if they appear in graphically-rendered tables or images.
5. Return ONLY a JSON object in this exact format:
{
  "page_count": <integer>,
  "part_numbers": ["PN1", "PN2", ...]
}
If none are found, return {"page_count": 0, "part_numbers": []}."""

            text_prompt = f"""You are a strict Data Extraction Engine. Extract all unique Product Part Numbers from the following PDF spec sheet page text.
CRITICAL RULES:
1. Ignore general catalog terms like 'DUTY', 'HEAVY', 'COLOR', 'PACKING', 'SHIELDED', 'CONNECT', 'TRANSITION'.
2. Part numbers are typically alphanumeric strings like 'XHCI', 'CLPL', 'CI14', etc.
3. Explicitly scan text that falls under MFG Part Number identifiers such as: 'Part #', 'Part Num', 'ID', 'SKU', 'MFG PART NUMBER', 'MFG P/N', and 'P/N'.
4. Return ONLY a JSON object in this exact format:
{{
  "page_count": <integer>,
  "part_numbers": ["PN1", "PN2", ...]
}}
If none are found, return {{"page_count": 0, "part_numbers": []}}.

TEXT:
{text}"""

            # Primary: Vision extraction (sees ALL text including graphic-rendered)
            print(f"  [PAGE {page_num+1}] Querying Gemini Vision (image+text)...")
            result = query_gemini_vision(vision_prompt, image_b64)
            extraction_mode = "vision"
            
            # If vision failed, fallback to text-only
            if not result or result.strip() in ("", "[]", "null"):
                print(f"  [PAGE {page_num+1}] Vision failed, falling back to text-only...")
                result = query_gemini(text_prompt)
                extraction_mode = "text_fallback"
            
            try:
                # Clean up markdown code blocks if any
                clean_result = result.strip()
                if clean_result.startswith("```json"):
                    clean_result = clean_result[7:-3].strip()
                elif clean_result.startswith("```"):
                    clean_result = clean_result[3:-3].strip()
                    
                parsed = json.loads(clean_result)
                if isinstance(parsed, list):
                    parts_list = parsed
                    page_count = len(parts_list)
                else:
                    parts_list = parsed.get("part_numbers", [])
                    page_count = parsed.get("page_count", len(parts_list))
            except Exception as e:
                print(f"  [ERROR] Failed to parse JSON: {e}")
                parts_list = []
                page_count = 0
                
            # Filter empty and deduplicate
            parts_list = list(set([str(p).strip() for p in parts_list if str(p).strip()]))
            
            if len(parts_list) != page_count:
                print(f"    [WARNING] LLM count ({page_count}) != actual deduplicated list length ({len(parts_list)})")
                page_count = len(parts_list)
            
            # ── CCO-UPC HALLUCINATION CROSS-REFERENCE ──
            # Compare every LLM-claimed part number against the embedded text layer.
            # If the PDF has an embedded text layer and the LLM returns a part number
            # that does NOT exist verbatim in the text, it may be a hallucination
            # (extra char, swapped char, or entirely fabricated).
            import difflib
            embedded_text_upper = text.upper().replace(" ", "")
            hallucination_report = []
            verified_parts = []
            
            for pn in parts_list:
                pn_norm = pn.replace(" ", "").upper()
                if pn_norm in embedded_text_upper:
                    # Exact match in text layer — VERIFIED
                    verified_parts.append({"part": pn, "status": "verified", "source": "text_layer_exact"})
                else:
                    # Not found verbatim. Check if a close match exists (fuzzy scan)
                    # This catches the "double S" type hallucination
                    best_ratio = 0.0
                    best_candidate = None
                    # Scan all words in the text for a fuzzy match
                    text_words = [w.strip() for w in text.split() if len(w.strip()) >= 3]
                    for word in text_words:
                        word_norm = word.replace(" ", "").upper()
                        ratio = difflib.SequenceMatcher(None, pn_norm, word_norm).ratio()
                        if ratio > best_ratio:
                            best_ratio = ratio
                            best_candidate = word.strip()
                    
                    if best_ratio >= 0.88:
                        # Close match — likely hallucinated an extra/wrong char
                        print(f"    [WARNING] [HALLUCINATION DETECTED] LLM said '{pn}' but PDF has '{best_candidate}' (sim={best_ratio:.2f})")
                        hallucination_report.append({
                            "llm_claimed": pn,
                            "pdf_actual": best_candidate,
                            "similarity": round(best_ratio, 3),
                            "severity": "minor",
                            "diagnosis": "LLM added/swapped character(s)"
                        })
                        verified_parts.append({"part": pn, "status": "hallucination_minor", "pdf_actual": best_candidate})
                    elif best_ratio >= 0.70:
                        # Weak match — suspicious
                        print(f"    [WARNING] [HALLUCINATION SUSPECT] LLM said '{pn}', closest PDF match is '{best_candidate}' (sim={best_ratio:.2f})")
                        hallucination_report.append({
                            "llm_claimed": pn,
                            "pdf_actual": best_candidate,
                            "similarity": round(best_ratio, 3),
                            "severity": "major",
                            "diagnosis": "Significant deviation — possible fabrication"
                        })
                        verified_parts.append({"part": pn, "status": "hallucination_major", "pdf_actual": best_candidate})
                    elif has_images and not has_text:
                        # Page is image-only, no text layer to cross-ref
                        verified_parts.append({"part": pn, "status": "unverifiable", "source": "image_only_page"})
                    else:
                        # Not in text at all — could be graphic-rendered or fully fabricated
                        print(f"    [WARNING] [HALLUCINATION UNKNOWN] LLM said '{pn}' — not found in text layer at all")
                        hallucination_report.append({
                            "llm_claimed": pn,
                            "pdf_actual": None,
                            "similarity": 0,
                            "severity": "unknown",
                            "diagnosis": "Not in text layer — may be graphic-rendered or fabricated"
                        })
                        verified_parts.append({"part": pn, "status": "unverifiable", "source": "not_in_text_layer"})
            
            if hallucination_report:
                print(f"    [HALLUCINATION SUMMARY] {len(hallucination_report)} potential hallucination(s) detected on page {page_num+1}")
                
            expected_truths["pages"][str(page_num + 1)] = {
                "page_count": page_count,
                "part_numbers": parts_list,
                "extraction_mode": extraction_mode,
                "embedded_text_chars": len(text.strip()),
                "hallucination_report": hallucination_report,
                "verification_summary": {
                    "verified": len([v for v in verified_parts if v["status"] == "verified"]),
                    "minor_hallucinations": len([v for v in verified_parts if v["status"] == "hallucination_minor"]),
                    "major_hallucinations": len([v for v in verified_parts if v["status"] == "hallucination_major"]),
                    "unverifiable": len([v for v in verified_parts if v["status"] == "unverifiable"]),
                }
            }
            
            # Recalculate total document count
            total_count = sum(p_data.get("page_count", 0) for p_data in expected_truths["pages"].values())
            expected_truths["total_document_count"] = total_count
            
            print(f"    -> Found {page_count} truth(s): {parts_list[:5]}...")
            
            # Avoid rate limits just in case
            time.sleep(4)
            
        doc.close()
        
        out_path = os.path.join(out_dir, "expected_truths.json")
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(expected_truths, f, indent=2)
            
        print(f"  [SUCCESS] Saved expected truths -> {out_path}\n")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="LLM Truth Extractor")
    parser.add_argument('--file', type=str, default=None, help='Specific PDF filename to process')
    parser.add_argument('--pages', type=str, default=None, help='Comma-separated page numbers (1-indexed)')
    args = parser.parse_args()
    extract_truths(args.file, args.pages)
