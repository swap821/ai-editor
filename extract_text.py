import PyPDF2

def extract_text(pdf_path):
    with open(pdf_path, 'rb') as file:
        reader = PyPDF2.PdfReader(file)
        text = ''
        for page_num in range(len(reader.pages)):
            page = reader.pages[page_num]
            text += page.extract_text()
    return text

pdf_path = 'AI_OS_Blueprint_v3_0_Production_Edition.pdf'
extracted_text = extract_text(pdf_path)

with open('blueprint_text.md', 'w', encoding='utf-8') as file:
    file.write(extracted_text)
