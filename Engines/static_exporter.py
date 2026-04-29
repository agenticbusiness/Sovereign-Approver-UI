"""
TLS Static Exporter - Pre-renders PDF pages as PNGs for GitHub Pages.
Run after part_number_extractor.py to generate static assets.
"""
import fitz
import json
import os

INPUT_FOLDER = r"c:\_3 EVF-Bricks\_02 UI for Spec Sheets - Part Number ONLY\_1 INPUT FOLDER"
OUTPUT_FOLDER = r"c:\_3 EVF-Bricks\_02 UI for Spec Sheets - Part Number ONLY\_2 Output Data"

def export_pages(target_file=None, pages_arg=None):
    target_pages = []
    if pages_arg:
        target_pages = [int(p.strip()) for p in pages_arg.split(',')]
        
    for fname in os.listdir(INPUT_FOLDER):
        if not fname.lower().endswith('.pdf'):
            continue
        if target_file and fname != target_file:
            continue
        doc_id = fname[:-4]
        pdf_path = os.path.join(INPUT_FOLDER, fname)
        out_dir = os.path.join(OUTPUT_FOLDER, doc_id, "pages")
        os.makedirs(out_dir, exist_ok=True)

        doc = fitz.open(pdf_path)
        print(f"[EXPORT] {fname}: {len(doc)} pages")

        # Update manifest with page count
        manifest_path = os.path.join(OUTPUT_FOLDER, "manifest.json")
        manifest = []
        if os.path.exists(manifest_path):
            with open(manifest_path, 'r') as f:
                manifest = json.load(f)

        entry = next((m for m in manifest if m['id'] == doc_id), None)
        if not entry:
            entry = {"id": doc_id, "path": f"_2 Output Data/{doc_id}/parsed_spatial_data.json"}
            manifest.append(entry)
        entry["pages"] = len(doc)

        # Load parsed_spatial_data.json if it exists
        json_path = os.path.join(OUTPUT_FOLDER, doc_id, "parsed_spatial_data.json")
        spatial_data = {}
        if os.path.exists(json_path):
            with open(json_path, 'r', encoding='utf-8') as f:
                spatial_data = json.load(f)
                
        # Load image_spatial_data.json if it exists
        img_json_path = os.path.join(OUTPUT_FOLDER, doc_id, "image_spatial_data.json")
        image_data = {}
        if os.path.exists(img_json_path):
            with open(img_json_path, 'r', encoding='utf-8') as f:
                image_data = json.load(f)

        for i in range(len(doc)):
            page_num = i + 1
            if target_pages and page_num not in target_pages:
                continue
                
            page = doc.load_page(i)
            
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            img_path = os.path.join(out_dir, f"{i+1}.png")
            pix.save(img_path)
            print(f"  Page {i+1} -> {img_path}")

        doc.close()

        with open(manifest_path, 'w') as f:
            json.dump(manifest, f, indent=2)

    print("[EXPORT] Done.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Static PNG Exporter")
    parser.add_argument('--file', type=str, default=None)
    parser.add_argument('--pages', type=str, default=None)
    args = parser.parse_args()
    export_pages(args.file, args.pages)
