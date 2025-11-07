from pathlib import Path
from clasificador.utils.conversor_texto import extraer_texto_auto

EXTENSIONES_SOPORTADAS = ['.pdf', '.jpg', '.jpeg', '.png', '.doc', '.docx', '.xls', '.xlsx']
MIMES_SOPORTADAS = [
    'application/pdf',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/msword',
    'application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'image/png',
    'image/jpeg'
]

def archivo_permitido(filename: str, mimetype: str) -> bool:
    """Valida extension y tipo MIME del archivo."""
    ext = Path(filename).suffix.lower()
    return ext in EXTENSIONES_SOPORTADAS and mimetype in MIMES_SOPORTADAS

def clasificar_archivo(archivo) -> dict:

    """
    Procesa un archivo adjunto, detecta el tipo y extrae su texto.
    Devuelve un dict con el resultado estructurado.
    """

    try:
        nombre_archivo = Path(archivo.filename).name
        contenido = archivo.read()
        extension = Path(archivo.filename).suffix.lower()

        if extension not in EXTENSIONES_SOPORTADAS:
            return {
                "nombre": nombre_archivo,
                "exito": False,
                "mensaje": f"Tipo de archivo no soportado: {extension}",
                "texto": ""
            }
        
        #Extracción automática optimizada

        texto = extraer_texto_auto(nombre_archivo, contenido)

        if not texto.strip():
            return{
                "nombre": nombre_archivo,
                "exito": False,
                "mensaje": "No se pudo extraer texto del archivo.",
                "texto": ""
            }
        return{
            "nombre": nombre_archivo,
            "exito": True,
            "mensaje": "Texto extraido correctamente.",
            "texto": texto
        }

    except Exception as e:
        return{
            "nombre": archivo.filename,
            "exito": False,
            "mensaje": f"Error procesando el archivo: {str(e)}",
            "texto": ""
        }