import fitz
import json
import os
import sys

VAULT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_FOLDER = os.path.join(VAULT_DIR, "_1 INPUT FOLDER")
OUTPUT_FOLDER = os.path.join(VAULT_DIR, "_2 Output Data")

def locate_images():
    print("==========================================================")
    print("   SOVEREIGN ENGINE: PRODUCT IMAGE LOCATOR")
    print("==========================================================\n")

    for fname in os.listdir(INPUT_FOLDER):
        if not fname.lower().endswith('.pdf'):
            continue
        
        doc_id = fname[:-4]
        pdf_path = os.path.join(INPUT_FOLDER, fname)
        out_dir = os.path.join(OUTPUT_FOLDER, doc_id)
        os.makedirs(out_dir, exist_ok=True)
        
        doc = fitz.open(pdf_path)
        print(f"[IMAGE LOCATOR] Processing: {fname}")
        
        spatial_data = {
            "filename": fname,
            "engine": "image_locator",
            "pages": []
        }
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            
            page_data = {
                "page_num": page_num + 1,
                "matches": [],
                "rejected": []
            }
            
            # get_image_info returns actual rendered dimensions and locations
            img_info = page.get_image_info(xrefs=True)
            for img_idx, img in enumerate(img_info):
                bbox = img["bbox"]
                width = bbox[2] - bbox[0]
                height = bbox[3] - bbox[1]
                
                # Filter out tiny logos/artifacts (< 25x25 pts) and extreme aspect ratios
                if width > 25 and height > 25:
                    if 0.2 < (width / height) < 5.0:
                        # Filter out extreme top/bottom margins (headers/footers)
                        if bbox[1] > 40 and bbox[3] < 760:
                            b_dict = {
                                "x": round(bbox[0], 2),
                                "y": round(bbox[1], 2),
                                "width": round(width, 2),
                                "height": round(height, 2)
                            }
                            page_data["matches"].append({
                                "field": "Product Image",
                                "text": f"Image_{img_idx+1}",
                                "bbox": b_dict,
                                "confidence": "high",
                                "engines_agreed": ["image_locator"],
                                "agreement": "1/1"
                            })
                        
            spatial_data["pages"].append(page_data)
            
        doc.close()
        
        out_path = os.path.join(out_dir, "image_spatial_data.json")
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(spatial_data, f, indent=2)
            
        print(f"  [SUCCESS] Saved image spatial data -> {out_path}")

if __name__ == "__main__":
    locate_images()
