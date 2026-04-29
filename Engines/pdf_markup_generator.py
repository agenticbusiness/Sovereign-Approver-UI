import os
import csv
import sys
try:
    import fitz  # PyMuPDF
except ImportError:
    print("[FATAL] PyMuPDF (fitz) is not installed. Please install it using `pip install PyMuPDF`.")
    sys.exit(1)

VAULT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF_PATH = os.path.join(VAULT_DIR, "Everflow-Master-Catalog.pdf")
CSV_PATH = os.path.join(VAULT_DIR, "Everflow_Master_Parsed.csv")
OUTPUT_PDF = os.path.join(VAULT_DIR, "Everflow-Master-Catalog-Marked.pdf")

def main():
    print("==========================================================")
    print("   SOVEREIGN ENGINE: PDF MARKUP GENERATOR")
    print("==========================================================\n")
    
    if not os.path.exists(PDF_PATH):
        print(f"[FATAL] PDF not found: {PDF_PATH}")
        sys.exit(1)
        
    if not os.path.exists(CSV_PATH):
        print(f"[FATAL] CSV not found: {CSV_PATH}")
        sys.exit(1)
        
    print(f"[SYSTEM] Opening PDF: {PDF_PATH}")
    doc = fitz.open(PDF_PATH)
    
    print(f"[SYSTEM] Loading coordinates from: {CSV_PATH}")
    records = []
    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            records.append(row)
            
    print(f"[SYSTEM] Loaded {len(records)} records. Drawing bounding boxes...")
    
    # Group by physical page
    page_map = {}
    for r in records:
        phys_page_str = r.get('Physical Page')
        if not phys_page_str:
            continue
        try:
            # headless_harvester sets physical_page as 1-indexed (p_idx + 1)
            p_idx = int(phys_page_str) - 1
            if p_idx not in page_map:
                page_map[p_idx] = []
            page_map[p_idx].append(r)
        except ValueError:
            pass
            
    # Draw boxes
    for p_idx, boxes in page_map.items():
        if p_idx < 0 or p_idx >= len(doc):
            continue
        page = doc[p_idx]
        for box in boxes:
            try:
                x0 = float(box['x0'])
                y0 = float(box['y0'])
                x1 = float(box['x1'])
                y1 = float(box['y1'])
                rect = fitz.Rect(x0, y0, x1, y1)
                
                annot = page.add_rect_annot(rect)
                annot.set_colors(stroke=(1, 0, 0))
                annot.set_border(width=1.5)
                annot.update()
            except Exception as e:
                print(f"Error drawing box on page {p_idx}: {e}")
                
    print(f"[SYSTEM] Saving marked-up PDF to: {OUTPUT_PDF}")
    doc.save(OUTPUT_PDF)
    doc.close()
    
    print(f"[SUCCESS] Marked-up PDF generated successfully.")

if __name__ == "__main__":
    main()
