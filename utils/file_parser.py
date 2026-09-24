import io
import PyPDF2
import docx
import pandas as pd

def parse_file(content, ext):
    try:
        if ext == 'pdf':
            return parse_pdf(content)
        elif ext == 'docx':
            return parse_docx(content)
        elif ext == 'txt':
            return parse_txt(content)
        elif ext == 'csv':
            return parse_csv(content)
        else:
            return None
    except Exception as e:
        return f"Ошибка парсинга: {e}"

def parse_pdf(content):
    text = ""
    reader = PyPDF2.PdfReader(io.BytesIO(content))
    for page in reader.pages:
        text += page.extract_text()
    return text[:5000]

def parse_docx(content):
    doc = docx.Document(io.BytesIO(content))
    text = "\n".join([p.text for p in doc.paragraphs])
    return text[:5000]

def parse_txt(content):
    return content.decode('utf-8', errors='ignore')[:5000]

def parse_csv(content):
    df = pd.read_csv(io.BytesIO(content))
    return df.to_string()[:5000]
