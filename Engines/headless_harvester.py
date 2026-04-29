import os
import sys
import yaml
import csv
import json
import jsonschema
from jsonschema.exceptions import ValidationError
try:
    import pdfplumber
except ImportError:
    print("[FATAL] pdfplumber is not installed.")
    sys.exit(1)

VAULT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MATRIX_PATH = os.path.join(VAULT_DIR, "Matrices", "evf_geometry_matrix.yaml")
SCHEMA_PATH = os.path.join(VAULT_DIR, "Matrices", "schema_validation.json")
PDF_PATH = os.path.join(VAULT_DIR, "Everflow-Master-Catalog.pdf")
OUTPUT_CSV = os.path.join(VAULT_DIR, "Everflow_Master_Parsed.csv")

def main(max_pages=None):
    print("==========================================================")
    print("   SOVEREIGN CCO-UPC ENGINE: HEADLESS HARVESTER")
    print("==========================================================\n")
    
    if not os.path.exists(MATRIX_PATH):
        print(f"[FATAL] Missing Matrix Configuration at: {MATRIX_PATH}")
        sys.exit(1)
        
    with open(MATRIX_PATH, 'r', encoding='utf-8') as f:
        matrix = yaml.safe_load(f)
        
    with open(SCHEMA_PATH, 'r', encoding='utf-8') as f:
        db_schema = json.load(f)
        
    print(f"[JUDGE] Matrix Loaded. Target PDF: {PDF_PATH}")
    
    req_headers = matrix.get('geometry_locks', {}).get('table_rules', {}).get('require_headers', [])
    mfg = matrix.get('output_schema', {}).get('manufacturer', 'Unknown')
    
    results = []
    
    with pdfplumber.open(PDF_PATH) as pdf:
        total_pages = len(pdf.pages)
        pages_to_process = min(max_pages, total_pages) if max_pages else total_pages
        print(f"[ENGINE] Processing {pages_to_process} pages...")
        
        for p_idx in range(pages_to_process):
            page = pdf.pages[p_idx]
            physical_page = p_idx + 1 # Simple 1-indexed fallback if no 'Page N' match
            
            tables = page.find_tables()
            for table in tables:
                extracted = table.extract()
                if not extracted: continue
                
                # Check headers
                header_row = extracted[0]
                if not header_row: continue
                
                part_col_idx = -1
                for c_idx, cell_val in enumerate(header_row):
                    if cell_val and any(req in cell_val for req in req_headers):
                        part_col_idx = c_idx
                        break
                        
                if part_col_idx == -1:
                    continue # Not a valid table based on matrix
                    
                # Extract rows
                for r_idx in range(1, len(extracted)):
                    row_data = extracted[r_idx]
                    if part_col_idx >= len(row_data): continue
                    
                    part_num = row_data[part_col_idx]
                    if not part_num: continue
                    part_num = part_num.strip().replace('\n', '')
                    
                    # Ignore forbidden terms or empty
                    if not part_num or "PART" in part_num or part_num in matrix.get('forbidden_terms', []):
                        continue
                        
                    # Get exact bounding box from flat list of table cells
                    num_columns = len(row_data)
                    flat_index = r_idx * num_columns + part_col_idx
                    if flat_index < len(table.cells):
                        cell_bbox = table.cells[flat_index]
                    else:
                        cell_bbox = None
                    
                    if not cell_bbox: continue
                    
                    x0, y0, x1, y1 = cell_bbox
                    
                    part_obj = {
                        "Part Number": part_num,
                        "Manufacturer": mfg,
                        "Physical Page": str(physical_page),
                        "x0": round(x0, 2),
                        "y0": round(y0, 2),
                        "x1": round(x1, 2),
                        "y1": round(y1, 2)
                    }
                    results.append(part_obj)
                    
            if (p_idx + 1) % 50 == 0:
                print(f"  -> Scanned {p_idx + 1} / {pages_to_process}")

    # Validate against schema
    print("\n[SECOPS] Validating extraction against SVBL schema...")
    try:
        jsonschema.validate(instance=results, schema=db_schema)
        print("  [OK] Schema Validation Passed.")
    except ValidationError as e:
        print(f"[FATAL] Schema Validation Failed: {e.message}")
        sys.exit(1)
        
    print(f"\n[SYSTEM] Validation successful. Writing {len(results)} records to CSV...")
    
    fields = ['Part Number', 'Manufacturer', 'Physical Page', 'x0', 'y0', 'x1', 'y1']
    with open(OUTPUT_CSV, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fields)
        writer.writeheader()
        for part in results:
            writer.writerow(part)
            
    print(f"[SUCCESS] Dumb Reader Engine completed. File: {OUTPUT_CSV}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--pages', type=int, help='Limit number of pages for testing')
    args = parser.parse_args()
    
    main(max_pages=args.pages)
