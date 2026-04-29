import fitz
import pandas as pd
import os

VAULT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF_PATH = os.path.join(VAULT_DIR, "Everflow-Master-Catalog.pdf")
MASTER_CSV_PATH = os.path.join(VAULT_DIR, "Everflow_Master_Parsed.csv")
REV3_PDF_PATH = os.path.join(VAULT_DIR, "Everflow-Master-Catalog-Rev3.pdf")
EXCEL_PATH = os.path.join(VAULT_DIR, "Everflow_Rev3_Audited.xlsx")

def run_auditor():
    print("[SYSTEM] Booting Rev3 Geometric Auditor Engine...")
    
    # 1. Load the Master Harvester Data (Source of Truth)
    try:
        df = pd.read_csv(MASTER_CSV_PATH)
    except Exception as e:
        print(f"[ERROR] Could not load master CSV: {e}")
        return
        
    print(f"[SYSTEM] Loaded {len(df)} MFG parts from Master CSV. Preparing native physical verification...")
    
    # 2. Open Original PDF
    doc = fitz.open(PDF_PATH)
    
    # We will build a new list with the Auditor-verified data
    audited_parts = []
    
    # Keep track of pages that need annotations to batch them
    page_annotations = {}
    
    total = len(df)
    missing_count = 0
    
    # For performance, group queries by page to avoid jumping around
    df_grouped = df.groupby('Physical Page')
    
    for physical_page, group in df_grouped:
        p_idx = int(physical_page) - 1
        if p_idx < 0 or p_idx >= len(doc):
            continue
            
        page = doc[p_idx]
        if p_idx not in page_annotations:
            page_annotations[p_idx] = []
            
        for _, row in group.iterrows():
            part_number = str(row['Part Number']).strip()
            
            # The Auditor natively searches the page layout for this exact string
            # PyMuPDF search_for returns a list of Rect objects
            rects = page.search_for(part_number)
            
            if rects:
                # We take the first match if multiple exist
                rect = rects[0]
                audited_parts.append({
                    'Part Number': part_number,
                    'Physical Page': physical_page,
                    'Category': row.get('Category', ''),
                    'Subcategory': row.get('Subcategory', ''),
                    'Chart Header': row.get('Chart Header', ''),
                    'Description': row.get('Description', ''),
                    'Red Box Pixel Location (x0, y0, x1, y1)': f"{rect.x0:.2f}, {rect.y0:.2f}, {rect.x1:.2f}, {rect.y1:.2f}"
                })
                
                # Queue for annotation
                page_annotations[p_idx].append(rect)
            else:
                # Flag as missing if the string doesn't exist on the expected physical page
                audited_parts.append({
                    'Part Number': part_number,
                    'Physical Page': physical_page,
                    'Category': row.get('Category', ''),
                    'Subcategory': row.get('Subcategory', ''),
                    'Chart Header': row.get('Chart Header', ''),
                    'Description': row.get('Description', ''),
                    'Red Box Pixel Location (x0, y0, x1, y1)': "MISSING_FROM_PAGE"
                })
                missing_count += 1
                
        if p_idx % 50 == 0:
            print(f"  -> Audited up to page {p_idx+1}/{len(doc)}")
            
    print(f"[SYSTEM] Audit complete. Processed {total} parts. {total - missing_count} found and locked. {missing_count} missing.")
    
    # 3. Write out the Audited Excel
    out_df = pd.DataFrame(audited_parts)
    out_df.to_excel(EXCEL_PATH, index=False)
    print(f"[SUCCESS] Independent pixel mapping saved to {EXCEL_PATH}")
    
    # 4. Draw Annotations for Rev3 PDF
    print("[SYSTEM] Injecting top-layer geometric annotations for Rev3 PDF...")
    for p_idx, rects in page_annotations.items():
        page = doc[p_idx]
        for rect in rects:
            annot = page.add_rect_annot(rect)
            annot.set_colors(stroke=(1, 0, 0))
            annot.set_border(width=1.5)
            annot.update()
            
    doc.save(REV3_PDF_PATH)
    doc.close()
    print(f"[SUCCESS] Rev3 marked catalog successfully generated: {REV3_PDF_PATH}")

if __name__ == "__main__":
    run_auditor()
