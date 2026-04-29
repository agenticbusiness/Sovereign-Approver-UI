import pdfplumber
import fitz
import yaml
import os
import pandas as pd
import re

VAULT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF_PATH = os.path.join(VAULT_DIR, "Everflow-Master-Catalog.pdf")
REV2_PDF_PATH = os.path.join(VAULT_DIR, "Everflow-Master-Catalog-Rev2.pdf")
EXCEL_PATH = os.path.join(VAULT_DIR, "Everflow_Rev2_Parsed.xlsx")
YML_PATH = os.path.join(VAULT_DIR, "Matrices", "custom_needs_inference.yaml")

def load_config():
    with open(YML_PATH, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def extract_rev2():
    config = load_config()
    anchors = config['header_anchors']
    tols = config['spatial_tolerances']
    x_margin = tols['x_expansion_margin']
    y_max_gap = tols['y_max_gap']
    h_offset = tols['header_height_offset']
    
    part_pattern = re.compile(config['validation_regex']['strict_part'])
    min_len = config['validation_regex']['minimum_length']
    
    print("[SYSTEM] Starting Rev2 Proxy Point Raycast across full catalog...")
    
    all_parts = []
    
    # We will just process the entire catalog, but to give fast feedback to the user,
    # we'll log every 50 pages.
    with pdfplumber.open(PDF_PATH) as pdf:
        total_pages = len(pdf.pages)
        for p_idx, page in enumerate(pdf.pages):
            if p_idx % 50 == 0:
                print(f"  -> Raycasting page {p_idx}/{total_pages}")
                
            words = page.extract_words()
            if not words:
                continue
                
            # 1. Find all anchors on this page
            active_columns = []
            
            # Simple heuristic: look for exact matches or merged words like "PART #"
            for i, w in enumerate(words):
                # Try single word
                if w['text'] in anchors:
                    active_columns.append({
                        'x0': w['x0'] - x_margin,
                        'x1': w['x1'] + x_margin,
                        'y_start': w['bottom'] + h_offset,
                        'last_y': w['bottom'] + h_offset
                    })
                # Try two words combined (e.g. "PART", "#")
                elif i < len(words) - 1:
                    combo = f"{w['text']} {words[i+1]['text']}"
                    if combo in anchors or w['text']+words[i+1]['text'] in anchors:
                        active_columns.append({
                            'x0': w['x0'] - x_margin,
                            'x1': words[i+1]['x1'] + x_margin,
                            'y_start': max(w['bottom'], words[i+1]['bottom']) + h_offset,
                            'last_y': max(w['bottom'], words[i+1]['bottom']) + h_offset
                        })
            
            if not active_columns:
                continue
                
            # 2. Raycast down each column
            for col in active_columns:
                # Find all words that fall inside this column's x-bounds and are below y_start
                col_words = [
                    cw for cw in words 
                    if cw['top'] >= col['y_start'] 
                    and cw['x0'] >= col['x0'] - 10 # Allow slight left drift
                    and cw['x1'] <= col['x1'] + 30 # Allow right drift (part numbers can be wider than header)
                ]
                
                # Sort top to bottom
                col_words.sort(key=lambda x: x['top'])
                
                for cw in col_words:
                    # Check gap
                    if cw['top'] - col['last_y'] > y_max_gap:
                        break # End of table
                        
                    # Validate
                    text = cw['text'].strip()
                    if len(text) >= min_len and part_pattern.match(text):
                        all_parts.append({
                            'Part Number': text,
                            'Physical Page': p_idx + 1,
                            'x0': cw['x0'],
                            'y0': cw['top'],
                            'x1': cw['x1'],
                            'y1': cw['bottom']
                        })
                        col['last_y'] = cw['bottom'] # Update gap tracker
    
    print(f"[SYSTEM] Raycast complete. Captured {len(all_parts)} validated part numbers.")
    
    # Write Excel
    if not all_parts:
        print("[WARN] No parts found.")
        return
        
    df = pd.DataFrame(all_parts)
    df['Red Box Pixel Location (x0, y0, x1, y1)'] = df.apply(
        lambda row: f"{row['x0']:.2f}, {row['y0']:.2f}, {row['x1']:.2f}, {row['y1']:.2f}", axis=1
    )
    df.to_excel(EXCEL_PATH, index=False)
    print(f"[SUCCESS] Wrote to {EXCEL_PATH}")
    
    # Mark PDF
    print("[SYSTEM] Annotating Rev2 PDF...")
    doc = fitz.open(PDF_PATH)
    
    page_map = {}
    for p in all_parts:
        pidx = p['Physical Page'] - 1
        if pidx not in page_map:
            page_map[pidx] = []
        page_map[pidx].append(p)
        
    for pidx, boxes in page_map.items():
        page = doc[pidx]
        for box in boxes:
            rect = fitz.Rect(box['x0'], box['y0'], box['x1'], box['y1'])
            annot = page.add_rect_annot(rect)
            annot.set_colors(stroke=(1, 0, 0))
            annot.set_border(width=1.5)
            annot.update()
            
    doc.save(REV2_PDF_PATH)
    doc.close()
    print(f"[SUCCESS] Wrote Rev2 PDF to {REV2_PDF_PATH}")

if __name__ == "__main__":
    extract_rev2()
