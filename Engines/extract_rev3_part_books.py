"""
EVF Rev3 Part Book Extractor (with Red Bounding Boxes)
------------------------------------------------------
Reads page ranges from 'EVF Range Breakouts - Pull1.xlsx' and extracts
corresponding pages from 'Everflow-Master-Catalog-Rev3.pdf' (which already
has red bounding boxes over MFG part numbers) into individual PDFs.

Output: _ EVF Part Book Breakouts with Red Box over Part Number/
        ├── VALVES/
        │   ├── VALVES - BRASS THREADED.pdf
        │   └── ...
        ├── FITTINGS/
        └── ...
"""

import os
import re
import openpyxl
from pypdf import PdfReader, PdfWriter

# --- Configuration ---
EXCEL_PATH = r"c:\EVF WF Joe Sommerville Cross\EVF Range Breakouts - Pull1.xlsx"
PDF_PATH = r"c:\_3 EVF-Bricks\_02 UI for Spec Sheets - Part Number ONLY\Everflow-Master-Catalog-Rev3.pdf"
OUTPUT_DIR = r"c:\_3 EVF-Bricks\_02 UI for Spec Sheets - Part Number ONLY\_ EVF Part Book Breakouts with Red Box over Part Number"

# Category merges (matching what user set up for the other Part Books)
CATEGORY_MERGES = {
    "VALVE": "VALVES",
    "BOXES": "KBIZ",
    "DISHWASHER": "KBIZ",
    "ICE": "KBIZ",
    "WASHING": "KBIZ",
    "TOILET": "KBIZ",
    "WATER HEATER": "SERVICE",
    "GAS": "SERVICE",
}

os.makedirs(OUTPUT_DIR, exist_ok=True)


def parse_page_spec(page_string: str, max_pages: int) -> list[int]:
    """
    Parse a page specification string like '192-197, 301, 198, 200-201'
    into a sorted, deduplicated list of 0-indexed page numbers.
    """
    pages = set()
    if not page_string:
        return []

    cleaned = page_string.strip().rstrip(",").strip()
    if not cleaned:
        return []

    segments = [s.strip() for s in cleaned.split(",") if s.strip()]

    for seg in segments:
        range_match = re.match(r"^(\d+)\s*-\s*(\d+)$", seg)
        if range_match:
            start = int(range_match.group(1))
            end = int(range_match.group(2))
            if start > end:
                start, end = end, start
            for p in range(start, end + 1):
                if 1 <= p <= max_pages:
                    pages.add(p - 1)
                else:
                    print(f"  WARNING: Page {p} out of range (1-{max_pages}), skipping.")
        else:
            try:
                p = int(seg)
                if 1 <= p <= max_pages:
                    pages.add(p - 1)
                else:
                    print(f"  WARNING: Page {p} out of range (1-{max_pages}), skipping.")
            except ValueError:
                print(f"  WARNING: Cannot parse segment '{seg}', skipping.")

    return sorted(pages)


def sanitize_filename(name: str) -> str:
    """Remove characters illegal in Windows filenames."""
    return re.sub(r'[<>:"/\\|?*]', '_', name).strip()


def main():
    # Load the master PDF (Rev3 with red bounding boxes)
    print(f"Loading Rev3 PDF: {PDF_PATH}")
    reader = PdfReader(PDF_PATH)
    total_pages = len(reader.pages)
    print(f"  Total pages: {total_pages}")

    # Load the Excel workbook
    print(f"\nLoading Excel: {EXCEL_PATH}")
    wb = openpyxl.load_workbook(EXCEL_PATH, read_only=True)
    ws = wb.active

    success_count = 0
    skip_count = 0
    error_count = 0
    folder_counts = {}

    for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        rank = row[0]
        category = row[1]
        headline = row[2]
        page_spec = row[3]

        # Skip empty rows
        if rank is None and category is None and headline is None:
            continue

        # Apply category merges
        cat_str = str(category or "UNKNOWN").strip()
        merged_cat = CATEGORY_MERGES.get(cat_str, cat_str)

        head_str = str(headline or "UNKNOWN").strip()
        filename = sanitize_filename(f"{cat_str} - {head_str}.pdf")

        # Parse pages
        if not page_spec:
            print(f"  Row {row_idx}: SKIP - No pages specified for '{headline}'")
            skip_count += 1
            continue

        page_indices = parse_page_spec(str(page_spec), total_pages)
        if not page_indices:
            print(f"  Row {row_idx}: SKIP - No valid pages parsed from '{page_spec}'")
            skip_count += 1
            continue

        # Create category folder
        cat_dir = os.path.join(OUTPUT_DIR, merged_cat)
        os.makedirs(cat_dir, exist_ok=True)

        # Extract pages
        try:
            writer = PdfWriter()
            for pi in page_indices:
                writer.add_page(reader.pages[pi])

            out_path = os.path.join(cat_dir, filename)
            with open(out_path, "wb") as f:
                writer.write(f)

            folder_counts[merged_cat] = folder_counts.get(merged_cat, 0) + 1
            print(f"  Row {row_idx}: OK - {merged_cat}/{filename} ({len(page_indices)} pages)")
            success_count += 1

        except Exception as e:
            print(f"  Row {row_idx}: ERROR - {filename}: {e}")
            error_count += 1

    wb.close()

    print(f"\n{'='*60}")
    print(f"EXTRACTION COMPLETE")
    print(f"  Success: {success_count}")
    print(f"  Skipped: {skip_count}")
    print(f"  Errors:  {error_count}")
    print(f"  Output:  {OUTPUT_DIR}")
    print(f"\n  Folder breakdown:")
    for cat in sorted(folder_counts.keys()):
        print(f"    {cat}: {folder_counts[cat]} PDFs")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
