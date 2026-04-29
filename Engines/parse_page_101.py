import pdfplumber
import pandas as pd
import re
import fitz

def main():
    pdf_path = 'Everflow-Master-Catalog.pdf'
    marked_path = 'Everflow-Master-Catalog-Marked.pdf'
    excel_path = 'Page_101_Part_Numbers.xlsx'
    page_idx = 100
    
    parts = []
    
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[page_idx]
        words = page.extract_words()
        
        # We need to find words that look like part numbers.
        # From context, they are like BGL-G10C, BAR-K10C
        part_pattern = re.compile(r'^[A-Z]{3}-[A-Z0-9]{4}$')
        
        # Let's also look for adjacent 'PART #' to be safe, or just trust the regex.
        for w in words:
            text = w['text']
            if part_pattern.match(text):
                parts.append({
                    'Part Number': text,
                    'x0': w['x0'],
                    'y0': w['top'],
                    'x1': w['x1'],
                    'y1': w['bottom']
                })
                
    if not parts:
        print("No parts found. Regex might be too strict.")
        return
        
    df = pd.DataFrame(parts)
    
    # Create the pixel location column as a string
    df['Red Box Pixel Location (x0, y0, x1, y1)'] = df.apply(
        lambda row: f"{row['x0']:.2f}, {row['y0']:.2f}, {row['x1']:.2f}, {row['y1']:.2f}", axis=1
    )
    
    df.to_excel(excel_path, index=False)
    print(f"Saved {len(df)} part numbers to {excel_path}")
    
    # Now explicitly draw them on the Marked PDF so the user sees them
    try:
        doc = fitz.open(marked_path)
        m_page = doc[page_idx]
        
        for p in parts:
            rect = fitz.Rect(p['x0'], p['y0'], p['x1'], p['y1'])
            annot = m_page.add_rect_annot(rect)
            annot.set_colors(stroke=(1, 0, 0))
            annot.set_border(width=1.5)
            annot.update()
            
        doc.saveIncr()
        doc.close()
        print("Updated marked PDF with these new boxes.")
    except Exception as e:
        print(f"Error updating marked PDF: {e}")

if __name__ == "__main__":
    main()
