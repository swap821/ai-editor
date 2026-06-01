# pdf_util.py
import sys
import os

try:
    import pypdf
except ImportError:
    print("[SYSTEM ERROR] 'pypdf' package is missing. Please execute: pip install pypdf")
    sys.exit(1)

def extract_pdf_to_markdown(pdf_path, output_path):
    if not os.path.exists(pdf_path):
        print(f"[ERROR] Source PDF not found at: {pdf_path}")
        return False

    print(f"Opening binary payload: {pdf_path}...")
    try:
        reader = pypdf.PdfReader(pdf_path)
        markdown_content = []
        total_pages = len(reader.pages)
        
        markdown_content.append(f"# Document Source: {os.path.basename(pdf_path)}\n")
        markdown_content.append(f"Total Pages Extracted: {total_pages}\n\n---\n\n")

        for index, page in enumerate(reader.pages):
            page_num = index + 1
            text = page.extract_text()
            
            markdown_content.append(f"## SECTION_PAGE_{page_num}\n")
            if text:
                markdown_content.append(f"{text.strip()}\n\n---\n\n")
            else:
                markdown_content.append("[Unextractable Binary Context or Image-Scan Page]\n\n---\n\n")
        
        # Enforce strict UTF-8 writing to prevent Windows console encoding crashes
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("".join(markdown_content))
            
        print(f"[SUCCESS] Ingestion complete. Structured text saved to: {output_path}")
        return True
    except Exception as e:
        print(f"[ERROR] Extraction pipeline failed: {str(e)}")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage error. Syntax: python pdf_util.py <source_pdf> <target_md>")
        sys.exit(1)
    
    extract_pdf_to_markdown(sys.argv[1], sys.argv[2])