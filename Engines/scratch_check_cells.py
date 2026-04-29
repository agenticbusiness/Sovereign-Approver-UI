import pdfplumber

pdf_path = r"c:\_3 EVF-Bricks\_02 UI for Spec Sheets - Part Number ONLY\Everflow-Master-Catalog.pdf"

with pdfplumber.open(pdf_path) as pdf:
    page = pdf.pages[199]
    tables = page.find_tables()
    for i, t in enumerate(tables):
        extracted = t.extract()
        print(f"Table {i} rows extracted: {len(extracted)}")
        if t.cells:
            print(f"Table {i} len(t.cells): {len(t.cells)}")
            print(f"Table {i} t.cells[0]: {t.cells[0]}")
        else:
            print(f"Table {i} has no cells.")
