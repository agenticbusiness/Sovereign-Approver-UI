import pdfplumber
import json

def main():
    pdf_path = 'Everflow-Master-Catalog.pdf'
    page_idx = 126  # Physical page 127
    
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[page_idx]
        words = page.extract_words()
        tables = page.extract_tables()
        
    output = {
        "tables": tables,
        "words_sample": [w['text'] for w in words[:100]] # First 100 words
    }
    
    with open('page_127_dump.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2)
        
if __name__ == "__main__":
    main()
