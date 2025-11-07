from flask import Blueprint, request, jsonify
from clasificador.services.clasificador_service import clasificar_archivo, archivo_permitido
from clasificador.prompts.generador_prompt import generar_prompt, generar_resumenes
from werkzeug.utils import secure_filename
from concurrent.futures import ThreadPoolExecutor, as_completed
import traceback
import logging
import requests
import os
import time

clasificador_bp = Blueprint('clasificador', __name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

@clasificador_bp.route('/', methods=['POST'])
def clasificar():

    try:
        #  Recibir múltiples archivos
        archivos = request.files.getlist('archivos')
        url_cliente = request.form.get('url') or (request.json.get('url') if request.is_json else None)


        funcion = 'clasificar'
        notificar_dispersion(url_cliente, funcion)

        if not archivos or len(archivos) == 0:
            return jsonify({'error': 'No se recibieron archivos'}), 400
        else:
            logger.info(f"Recibidos {len(archivos)} archivos del cliente: {url_cliente}") 

        if not url_cliente:
            return jsonify({'error': 'URL del cliente no recibida'}), 400

        #Extraccion del texto

        def procesar_archivo(archivo):
            
            nombre_archivo = secure_filename(archivo.filename)
            inicio = time.time() #Inicio de medicion individual
            try:
                # Ejecuta el clasificador de servicio
                resultado = clasificar_archivo(archivo)

                #Validar estructura del resultado
                if not isinstance(resultado, dict):
                    raise ValueError("La funcion clasificar_archivo no devolvio un diccionario válido")
                
                #Validar archivo permitido
                if not archivo_permitido(archivo.filename, archivo.mimetype):
                    logger.warning(f"Archivo no permitido o con tipo inválido: {archivo.filename}")
                
                if not resultado.get("exito"):
                    logger.warning(f"⚠️ {nombre_archivo}: {resultado.get('mensaje', 'Sin mensaje')}")
                    return None, None

                texto_extraido = resultado.get("texto", "")

                if not texto_extraido or len(texto_extraido.strip()) == 0:
                    logger.warning(f"⚠️ {nombre_archivo}: Texto vacío o ilegible.")

                duracion = round(time.time() - inicio, 2)
                logger.info(f"✅ Texto extraído correctamente de {nombre_archivo} en {duracion}s")
                return nombre_archivo, texto_extraido

            except ValueError as ve:
                logger.warning(f"⚠️ {archivo.filename}: {ve}")    
            except Exception as e:
                logger.error(f"❌ Error extrayendo texto de {archivo.filename}: {e}")
            finally:
                fin = time.time()
                logger.info(f"⏱️ Tiempo total {nombre_archivo}: {round(fin - inicio, 2)}s")
            
            return None, None
        
        documentos ={}

        # 🧠 Ejecutar extracción en paralelo
        with ThreadPoolExecutor(max_workers= min(4, os.cpu_count() * 2)) as executor:
            futures = {executor.submit(procesar_archivo, archivo): archivo for archivo in archivos}
            for future in as_completed(futures):
                nombre, texto = future.result()
                if nombre and texto:
                    documentos[nombre] = texto
                    


        if not documentos:
            return jsonify({'error': 'No se pudo procesar ningún archivo válido'}),400

        #Llamada a GEMINI (1 o mas archivos)

        try:        

            if len(documentos) == 1:
                # Solo un archivo → análisis directo
                nombre, texto = list(documentos.items())[0]
                logger.info(f"📄 Análisis directo para: {nombre}")
                resultado_final = generar_prompt([{
                    "documento": nombre,
                    "resumen": texto,
                    "tipo_documento": "Desconocido",
                    "indicadores_clave": {}
                }])
            else:
                # Varios archivos → flujo normal (resúmenes + análisis final)
                logger.info(f"📚 Analizando {len(documentos)} documentos del mismo proceso")
                resumenes = generar_resumenes(documentos)
                resultado_final = generar_prompt(resumenes)
            
        except requests.exceptions.RequestException as re:
            logger.error(f"🌐 Error de red al llamar a la API de Gemini: {re}")
            return jsonify({
                "error": "Error de conexión con el modelo de IA",
                "detalle": str(re)                
            }), 503 # Servicio no disponible
        
        except Exception as e:
            logger.error(f"❌ Error en la llamada al modelo Gemini: {e}")
            return jsonify({
                "error": "Error al generar la respuesta con Gemini",
                "detalle": str(e)                
            }), 502 #Bad Gateway (error del modelo)
        
        # Validacion y parseo de respuesta

        if not resultado_final:
            return jsonify({
                "error": "Respuesta vacía del modelo de IA",
            }), 502
        
        if isinstance(resultado_final,dict) and "error" in resultado_final:
            #Error interno desde generador_prompt.py
            logger.error(f"⚠️ Error en la respuesta del modelo: {resultado_final['error']}")
            return jsonify({
                "error": "Ocurrió un problema al interpretar la respuesta de modelo",
                "detalle": resultado_final["error"]
            }), 502
        
        #Respuesta exitosa

        logger.info("✅ Proceso completado exitosamente")
        return jsonify (resultado_final), 200
    
    except MemoryError:
        logger.critical("💥 Error de memoria: el archivo o el texto son demasiado grandes.")
        return jsonify({
            "error": "El servidor no tiene suficiente memoria para procesar este archivo."
        }), 413 #Request Entity Too Large
        
    except Exception as e:
        logger.critical("❌ ERROR INTERNO DEL SERVIDOR ❌")
        traceback.print_exc()

        return jsonify({
            "error": "Error interno del servidor",
            "detalle": str(e)
        }), 500

def notificar_dispersion(url_cliente, funcion):
    data = {
        "url": url_cliente,
        "funcion": funcion
    }

    response = requests.post(
        "https://dispersion-718759852530.us-central1.run.app/dispersion",
        json=data
    )

    if response.status_code == 200:
        print("Registro en dispersión exitoso")
    else:
        print(f"Error en dispersión: {response.status_code} - {response.text}")