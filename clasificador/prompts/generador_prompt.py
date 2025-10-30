from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
import os
import json
import re
import logging

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise EnvironmentError("No se encontró GEMINI_API_KEY en el entorno.")

#Prompt que resume cada documento para alimentar el prompt final

def resumen_parcial_prompt(nombre_doc: str, texto: str) -> str:
    if not GEMINI_API_KEY:
        return {"error": "API key no configurada"}

    return f"""
Eres un asistente jurídico colombiano. Resume brevemente el siguiente documento judicial
sin perder la información jurídica esencial.  

ENTRADA:
<documento nombre="{nombre_doc}">
{texto[:20000]}  # límite seguro para Gemini (~15-20k tokens)
</documento>

Tu salida debe ser un JSON con esta estructura exacta:

{{
  "documento": "{nombre_doc}",
  "tipo_documento": "",
  "resumen": "",
  "indicadores_clave": {{
    "partes": "",
    "pretensiones": "",
    "hechos": "",
    "fundamentos": "",
    "autoridad": ""
  }}
}}

Reglas:
- No inventes información.
- Resume en máximo 5 oraciones por campo.
- Si no se identifica algo, escribe "No se menciona en el texto.".
- Devuelve solo JSON.
"""

def procesar_documento(nombre: str, texto: str):
    prompt = resumen_parcial_prompt(nombre, texto)

    response = requests.post(
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent",
        params={"key": GEMINI_API_KEY},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig":{
            "temperature":0.2,       # Controla la “creatividad” (0 = literal, 1 = más libre)
            "max_output_tokens":2048
            }
        },
    )
    try:
        result = response.json()
        text_result = result.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        text_result = re.sub(r"```json|```", "", text_result).strip()
        return json.loads(text_result)
    except Exception as e:
        print(f"⚠️ Error procesando {nombre}: {e}")
        return {"documento": nombre, "error": "No se pudo generar resumen"}
    
def generar_resumenes(documentos: dict):
    """
    documentos: dict con {nombre_archivo: texto_extraido}
    Procesa los documentos en paralelo para obtener sus resúmenes parciales.
    """
    resultados = []
    logger = logging.getLogger(__name__)

    with ThreadPoolExecutor(max_workers=min(4, os.cpu_count() * 2)) as executor:
        futures = {
            executor.submit(procesar_documento, nombre, texto): nombre
            for nombre, texto in documentos.items()
        }

        for future in as_completed(futures):
            nombre = futures[future]
            try:
                resumen = future.result()
                resultados.append(resumen)
                logger.info(f"✅ Resumen generado para {nombre}")
            except Exception as e:
                logger.error(f"❌ Error generando resumen de {nombre}: {e}")

    return resultados

#Definimos el prompt final (respuesta completa)

def generar_prompt(resumenes_json):
    if not GEMINI_API_KEY:
        return {"error": "API key no configurada"}

    # 🔹 Convertir los resúmenes a formato legible con delimitadores semánticos
    documentos_texto = ""
    for r in resumenes_json:
        nombre = r.get("documento", "Sin nombre")
        tipo = r.get("tipo_documento", "Desconocido")
        resumen = r.get("resumen", "")
        ind = r.get("indicadores_clave", {})

        documentos_texto += f"""
    <documento nombre="{nombre}">
    Tipo: {tipo}
    Resumen: {resumen}
    Indicadores clave:
    - Partes: {ind.get('partes', 'No se menciona.')}
    - Pretensiones: {ind.get('pretensiones', 'No se menciona.')}
    - Hechos: {ind.get('hechos', 'No se menciona.')}
    - Fundamentos: {ind.get('fundamentos', 'No se menciona.')}
    - Autoridad: {ind.get('autoridad', 'No se menciona.')}
    </documento>
    """


    prompt = f"""
Eres un experto en derecho colombiano y en análisis de documentos judiciales.
Tu tarea es analizar uno o varios documentos que pertenecen a un mismo proceso judicial
y devolver la información estructurada de acuerdo con los campos definidos.

INSTRUCCIONES ESTRICTAS:
- Responde únicamente con un JSON válido, sin texto adicional ni explicaciones.
- No repitas el rol ni el contexto.
- No uses comentarios ni texto fuera del JSON.
- Escapa todas las comillas dobles internas con \\".
- Si un campo no aparece en el texto, escribe "No se menciona en el texto.".
- No inventes información ni completes datos implícitos.
- Utiliza redacción formal, precisa y concisa, en español jurídico colombiano.

ANÁLISIS DOCUMENTAL:
- Algunos documentos pueden corresponder a escritos de demanda, autos admisorios, contestaciones, tutelas o providencias.
- El documento que contenga expresiones como "Acción de Tutela", "Demanda", "Pretensiones", "Hechos" o "Solicitud" debe considerarse el documento principal del proceso.
- Los documentos con expresiones como "Auto", "Admite", "Providencia", "Juzgado", "Fallo" o "Resolución" deben considerarse documentos complementarios.
- Usa la información del documento principal para extraer las pretensiones, hechos, partes y tipo de proceso.
- Usa los documentos complementarios solo para completar datos procesales como juzgado, ciudad, número y fecha de radicación.
- Todos los documentos pertenecen al mismo proceso judicial.

OBJETIVO:
1. Determina el tipo de documento principal (por ejemplo: Demanda, Auto, Tutela, Providencia, Contestación, etc.).
2. Si se trata de una demanda, identifica la clasificación (civil, laboral, administrativa, penal, constitucional, etc.).
3. Determina el tipo de demanda (por ejemplo: contractual, de nulidad, ejecutiva, de reparación directa, acción de tutela, etc.).
4. Extrae y consolida la información correspondiente a los siguientes campos, sin duplicados ni repeticiones.

EJEMPLOS DE INDICADORES SEMÁNTICOS (para inferir secciones):
- "El demandante es..." o "La parte demandante..." → sección PARTES
- "Pretende que se declare..." o "Solicita..." → sección PRETENSIONES
- "Los hechos son..." o "Hechos relevantes..." → sección HECHOS
- "Con fundamento en..." o "De conformidad con..." → sección FUNDAMENTOS DE DERECHO
- "Por lo anterior..." o "En mérito de lo expuesto..." → cierre del documento
- "Radicado No." o "Expediente No." → número de radicado
- "Juzgado" o "Tribunal" → juzgado o autoridad judicial
- "En la ciudad de..." o "Bogotá D.C." → ciudad de radicación

SALIDA (formato exacto, solo JSON):
{{
  "tipo_documento": "",
  "clasificacion": "",
  "tipo_demanda": "",
  "campos": {{
    "tipo_proceso": "",
    "partes_involucradas": "",
    "pretensiones": "",
    "hechos_relevantes": "",
    "normas_citadas": "",
    "juzgado_o_autoridad": "",
    "fecha_radicacion": "",
    "numero_radicado": "",
    "apoderados": "",
    "ciudad": ""
  }}
}}

REGLAS DE CONSISTENCIA:
- Si hay varios documentos, analiza todo el contenido como un solo proceso.
- Si hay contradicciones, prioriza el documento que contenga la demanda o tutela principal.
- Si un dato aparece en un documento complementario y no en el principal, inclúyelo.
- Mantén los nombres de los campos exactamente como en el formato JSON.
- Todos los valores deben ser texto plano, sin listas ni saltos de línea innecesarios.
- No incluyas texto fuera del JSON.

--- DOCUMENTOS A ANALIZAR ---
Cada documento está delimitado así:
<documento nombre="...">
[contenido]
</documento>

CONTENIDO:
{documentos_texto}
"""
    try:
    # ✅ Aquí ya no retornamos, sino que llamamos al endpoint
        response = requests.post(
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent",
            params={"key": GEMINI_API_KEY},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig":{
                "temperature":0.2,       # Controla la “creatividad” (0 = literal, 1 = más libre)
                "max_output_tokens":8192
                }
            },
            timeout= 300
        )
        response.raise_for_status()
    except requests.exceptions.Timeout:
        return {"error": "Tiempo de espera agotado al comunicarse con la API de Gemini"}
    except requests.exceptions.RequestException as e:
        return {"error": f"Error en la conexión con Gemini: {str(e)}"}

    if response.status_code != 200:
        return {"error": response.text}
    try:
        result = response.json()
        text_result = (
            result.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
        )    
        if not text_result.strip():
            raise ValueError("Respuesta vacía del modelo de IA.")
    except ValueError as ve:
        return {"error":str(ve)}
    except Exception as e:
        return{"error": f"No se pudo interpretar la respuesta de Gemini: {str(e)}"}    

    # Limpieza del texto antes de parsear
    text_result = re.sub(r"```json|```", "", str(text_result)).strip()
    text_result = re.sub(r'(:\s*")([^"]*?)"([^"]*?")', r'\1\2\\\"\3', text_result)

    try:
        json_result = json.loads(text_result)

        # Si "contenido" es lista de diccionarios → unificar
        if isinstance(json_result.get("contenido"), list):
            contenido_unido = {}
            for item in json_result["contenido"]:
                if isinstance(item, dict):
                    contenido_unido.update(item)
            json_result["contenido"] = contenido_unido

        # 🔹 Limpieza final de barras invertidas sobrantes
        def limpiar_valores(data):
            if isinstance(data, dict):
                return {k: limpiar_valores(v) for k, v in data.items()}
            elif isinstance(data, list):
                return [limpiar_valores(v) for v in data]
            elif isinstance(data, str):
                return re.sub(r'\\+$', '', data).strip()
            return data

        json_result = limpiar_valores(json_result)
        return json_result

    except Exception as e:
        return {
            "error": f"No se pudo parsear la respuesta de Gemini: {e}",
            "respuesta_original": text_result
        }