import io
import pytesseract
import pandas as pd
from PIL import Image
from docx import Document
from pdf2image import convert_from_bytes
from PyPDF2 import PdfReader

# 🧩 Configuración global OCR
# Evita recargar idioma y modelos en cada llamada
pytesseract.pytesseract.tesseract_cmd = "/usr/bin/tesseract"
OCR_CONFIG = "--oem 3 --psm 6"  # Equilibrio entre precisión y velocidad

# 🔹 PDF no escaneado (texto seleccionable)

def extraer_texto_pdf(file_bytes: bytes) -> str:
    # Intentar extracción por texto (PDF no escaneado)
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
        texto = "".join([page.extract_text() or "" for page in reader.pages])
        # Limpieza básica
        texto = texto.replace("\n", " ").replace("\r", " ").strip()
        return texto
    except Exception as e:
        return ""

# 🔹 PDF escaneado (OCR)

def extraer_texto_pdf_ocr(file_bytes:bytes) -> str:
    # OCR de PDF escaneado
    try:
        pages = convert_from_bytes(file_bytes, dpi=150) # bajar resolucion mejora velocidad
        texto_total = []
        for page in pages:
            # Reducción de tamaño (mitad) para acelerar OCR sin perder legibilidad
            page = page.resize((page.width // 2, page.height // 2))
            texto_total.append(pytesseract.image_to_string(page, lang="spa", config=OCR_CONFIG)) 
        return " ".join(texto_total).replace("\n", " ").strip()
    except Exception as e:
        return f"Error en OCR: {e}"

# 🔹 Imagen (JPG, PNG)

def extraer_texto_imagen(file_bytes: bytes) -> str:
    """Extrae texto de una imagen usando OCR."""
    try:
        image = Image.open(io.BytesIO(file_bytes))
        #Reducir resolucion si es muy grande la imagen
        if image.width > 2000:
            image = image.resize((image.width // 2, image.height // 2))
        texto = pytesseract.image_to_string(image, lang="spa", config=OCR_CONFIG)
        return texto.replace("\n", " ").strip()
    except Exception as e:
        return f"Error leyendo imagen: {e}"
    
# 🔹 Word (.docx)    

def extraer_texto_word(file_bytes: bytes) -> str:
    """Extrae texto de un archivo Word (.docx) dado como bytes."""
    try:    
        doc = Document(io.BytesIO(file_bytes))
        texto = " ".join(p.text.strip() for p in doc.paragraphs if p.text.strip())
        return texto
    except Exception as e:
        return f"Error leyendo Word: {e}"
    
# 🔹 Excel (.xls, .xlsx)

def extraer_texto_excel(file_bytes):
    """Extrae texto de un archivo Excel (.xls, .xlsx) dado como bytes."""
    try:
        xls = pd.read_excel(io.BytesIO(file_bytes), sheet_name=None)
        contenido = []
        for nombre, hoja in xls.items():
            contenido.append(f"--- Hoja: {nombre} ---")
            contenido.append(hoja.to_string(index=False))
        return " ".join(contenido).replace("\n", " ").strip()
    except Exception as e:
        return f"Error leyendo Excel: {e}"

def extraer_texto_auto(nombre_archivo: str, file_bytes: bytes) -> str:
    """
    Detecta el tipo de archivo y aplica el extractor adecuado.
    """
    nombre_archivo = nombre_archivo.lower()
    if nombre_archivo.endswith(".pdf"):
        texto = extraer_texto_pdf(file_bytes)
        if len(texto.strip()) < 50: #fallback a OCR si poco texto
            texto = extraer_texto_pdf_ocr(file_bytes)
        return texto
    
    elif nombre_archivo.endswith((".jpg", ".jpeg", ".png")):
        return extraer_texto_imagen(file_bytes)
    
    elif nombre_archivo.endswith(".docx"):
        return extraer_texto_word(file_bytes)
    
    elif nombre_archivo.endswith((".xls", ".xlsx")):
        return extraer_texto_excel(file_bytes)
    
    return "Formato no soportado o archivo vacio"