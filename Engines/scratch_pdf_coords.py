import pdfplumber
import json

pdf_path = r"c:\_3 EVF-Bricks\_02 UI for Spec Sheets - Part Number ONLY\Everflow-Master-Catalog.pdf"

with pdfplumber.open(pdf_path) as pdf:
    page = pdf.pages[199] # Page 200
    
    # Extract words to see where the part numbers are
    words = page.extract_words()
    part_words = [w for w in words if "4512" in w['text'] or "4534" in w['text'] or "4501" in w['text']]
    
    for pw in part_words:
        print(f"Part: {pw['text']} - Box: x0={pw['x0']:.2f}, y0={pw['top']:.2f}, x1={pw['x1']:.2f}, y1={pw['bottom']:.2f}")
    
    # Also get table bounding boxes
    tables = page.find_tables()
    for i, t in enumerate(tables):
        print(f"Table {i} bbox: {t.bbox}")
        
    print("--- HEADERS ---")
    headers = [w for w in words if "PART" in w['text'] or "SIZE" in w['text']]
    for h in headers:
        print(f"Header: {h['text']} - Box: x0={h['x0']:.2f}, y0={h['top']:.2f}, x1={h['x1']:.2f}, y1={h['bottom']:.2f}")

