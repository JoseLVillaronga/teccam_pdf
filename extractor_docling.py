"""
Módulo de extracción de documentos utilizando el servidor Docling remoto.

Docling es una herramienta de IBM que convierte documentos (PDF, HTML, DOCX,
etc.) a Markdown/JSON usando OCR y modelos de estructura de página. La
extracción con Docling es mucho más precisa que la extracción simple con
PyMuPDF, especialmente en documentos escaneados o con tablas complejas.

Este módulo se comunica con un servidor ``docling-serve`` activo en la red
local. Los endpoints estándar son:

- ``POST /v1/convert/file``        : Convierte un archivo (multipart/form-data)
- ``POST /v1/convert/source``      : Convierte una URL o archivo en base64 (JSON)
- ``POST /v1/convert/file/async``  : Convierte un archivo de forma asíncrona
- ``POST /v1/convert/source/async``: Convierte una URL o base64 de forma asíncrona
- ``GET  /v1/status/poll/{task_id}`` : Consulta el estado de un job asíncrono
- ``GET  /v1/result/{task_id}``    : Obtiene el resultado de un job asíncrono

La respuesta de conversión síncrona tiene la forma:

.. code-block:: json

    {
        "document": {
            "filename": "documento.pdf",
            "md_content": "# Texto en Markdown ..."
        },
        "status": "success",
        "processing_time": 12.3,
        "errors": []
    }

El Markdown extraído se encuentra en ``document.md_content``.
"""

import os
import re
import time
import html as html_mod

import requests


def neutralizar_html_malformado(texto):
    """
    Neutraliza fragmentos HTML malformados que Docling puede generar.

    Docling a veces produce secuencias de caracteres ``<`` y ``>`` que forman
    pseudo-tags sin cerrar (por ejemplo ``<<título>>``, ``<span ...>`` sin cierre,
    o bloques donde los signos ``<``/``>`` están desbalanceados). Esos fragmentos
    hacen que ``markdown2`` entre en recursión infinita (RecursionError) al
    renderizar la página.

    Esta función solo actúa si detecta un desbalanceo grave entre aperturas y
    cierres (más de 5 de diferencia por línea), neutralizando los caracteres en
    esas líneas mediante escape HTML. Si el HTML está balanceado (p. ej. tablas
    válidas que Docling sí genera a veces), se deja intacto.

    :param texto: Texto Markdown crudo
    :return: Texto con fragmentos malformados escapados
    """
    if not texto or not texto.strip():
        return texto

    lineas = texto.split('\n')
    lineas_resultado = []

    for linea in lineas:
        # Solo sanear líneas con contenido y con caracteres problemáticos
        if '<' in linea or '>' in linea:
            aperturas = linea.count('<')
            cierres = linea.count('>')

            # Si hay un desbalanceo grave, escapar la línea completa.
            # Esto neutraliza tags sin cerrar sin afectar HTML balanceado.
            if abs(aperturas - cierres) >= 5:
                linea = html_mod.escape(linea, quote=False)

        lineas_resultado.append(linea)

    return '\n'.join(lineas_resultado)


def limpiar_texto_docling(texto):
    """
    Limpia el texto Markdown devuelto por Docling remoto, aplicando las
    mismas reglas de unión de palabras partidas por guión que se usan con
    PyMuPDF, de modo que el resultado sea consistente con el resto del sistema.

    :param texto: Texto Markdown crudo devuelto por Docling
    :return: Texto limpio con párrafos bien formados
    """
    if not texto or not texto.strip():
        return texto

    # Neutralizar HTML malformado que Docling pueda generar y que rompe markdown2
    texto = neutralizar_html_malformado(texto)

    # Separar en líneas y reconstruir párrafos (misma lógica
    # que extractor_pdf.limpiar_texto_pdf)
    lineas = texto.split('\n')
    parrafos = []
    parrafo_actual = []
    linea_pendiente_guion = None

    def finalizar_parrafo():
        nonlocal linea_pendiente_guion
        if linea_pendiente_guion:
            parrafo_actual.append(linea_pendiente_guion)
            linea_pendiente_guion = None
        if parrafo_actual:
            texto_parrafo = '\n'.join(parrafo_actual)
            texto_parrafo = re.sub(r' +', ' ', texto_parrafo)
            texto_parrafo = re.sub(r'\s+([.,;:!?\)\]])', r'\1', texto_parrafo)
            texto_parrafo = re.sub(r'([\(\[])\s+', r'\1', texto_parrafo)
            parrafos.append(texto_parrafo.strip())
            parrafo_actual.clear()

    for linea in lineas:
        linea_stripped = linea.strip()

        if not linea_stripped:
            finalizar_parrafo()
            continue

        # Detectar cambio de página
        if linea_stripped.startswith('\x0c') or linea_stripped.startswith('[PAGE'):
            finalizar_parrafo()
            if linea_stripped and not linea_stripped.startswith('[PAGE'):
                parrafos.append(linea_stripped)
            continue

        # Si la línea previa terminó con guión, unir la siguiente sílaba
        if linea_pendiente_guion is not None:
            partes = linea_stripped.split(None, 1)
            primera_palabra = partes[0]
            resto = partes[1] if len(partes) > 1 else ""

            linea_reconstruida = linea_pendiente_guion + primera_palabra
            parrafo_actual.append(linea_reconstruida)
            linea_pendiente_guion = None

            if not resto:
                continue
            linea_stripped = resto

        # Detectar fin de palabra partida con guión
        if (linea_stripped.endswith('-') or linea_stripped.endswith('—')) and len(linea_stripped) > 1:
            linea_pendiente_guion = linea_stripped.rstrip('-—').rstrip()
        else:
            # Conservar la línea tal cual (Docling ya preserva párrafos)
            parrafo_actual.append(linea_stripped)

    finalizar_parrafo()

    return '\n\n'.join(parrafos)


def _extraer_markdown_de_respuesta(data_json):
    """
    Extrae el contenido Markdown de la respuesta JSON del servidor Docling.

    Formato esperado (síncrono):

    .. code-block:: json

        {
            "document": {
                "md_content": "texto markdown",
                "filename": "..."
            },
            "status": "...",
            ...
        }

    También soporta variantes si la respuesta viene en otro formato.

    :param data_json: Respuesta JSON del servidor Docling
    :return: Texto Markdown extraído o cadena vacía
    """
    if not data_json:
        return ""

    if not isinstance(data_json, dict):
        return ""

    # Formato estándar de docling-serve
    documento = data_json.get('document')
    if isinstance(documento, dict):
        md = documento.get('md_content') or documento.get('markdown')
        if isinstance(md, str) and md.strip():
            return md
        # También puede venir en texto plano
        texto = documento.get('text_content') or documento.get('text')
        if isinstance(texto, str) and texto.strip():
            return texto

    # Formato directo alternativo
    for clave in ['markdown', 'md_content', 'text', 'texto']:
        valor = data_json.get(clave)
        if isinstance(valor, str) and valor.strip():
            return valor

    # Buscar en sub-elementos (si envuelto en 'data', 'result', 'output', etc.)
    for clave in ['data', 'result', 'output', 'response', 'converted']:
        sub = data_json.get(clave)
        if isinstance(sub, dict):
            md = _extraer_markdown_de_respuesta(sub)
            if md:
                return md
        elif isinstance(sub, list):
            for item in sub:
                if isinstance(item, dict):
                    md = _extraer_markdown_de_respuesta(item)
                    if md:
                        return md

    return ""


def _extraer_task_id_de_respuesta(data_json):
    """
    Extrae el ID de tarea de la respuesta de una conversión asíncrona.

    :param data_json: Respuesta JSON del servidor Docling
    :return: ID de tarea o None
    """
    if not isinstance(data_json, dict):
        return None

    for clave in ['task_id', 'taskId', 'id', 'result_id', 'job_id', 'jobId']:
        valor = data_json.get(clave)
        if isinstance(valor, str) and valor:
            return valor
        if isinstance(valor, int):
            return str(valor)

    # Buscar dentro de 'data' o 'result'
    for clave in ['data', 'result', 'job']:
        sub = data_json.get(clave)
        if isinstance(sub, dict):
            task_id = _extraer_task_id_de_respuesta(sub)
            if task_id:
                return task_id

    return None


def _consultar_estado_job(base_url, task_id, timeout_total=1800):
    """
    Consulta periódicamente el estado de un job asíncrono en el servidor
    Docling hasta que finalice, y devuelve el Markdown del resultado.

    Endpoints usados (en orden de preferencia):

    - ``GET /v1/status/poll/{task_id}`` : Estado del job
    - ``GET /v1/result/{task_id}``      : Resultado final

    :param base_url: URL base del servidor Docling (ej. http://192.168.1.47:5020)
    :param task_id: ID de la tarea asíncrona
    :param timeout_total: Tiempo máximo de espera en segundos
    :return: Texto Markdown del resultado o cadena vacía
    """
    url_poll = f"{base_url}/v1/status/poll/{task_id}"
    url_result = f"{base_url}/v1/result/{task_id}"

    tiempo_inicio = time.time()

    while time.time() - tiempo_inicio < timeout_total:
        # Consultar estado
        try:
            respuesta = requests.get(url_poll, timeout=15)
            if respuesta.status_code == 200:
                data = respuesta.json()
                estado = (data.get('status') or data.get('estado') or '').lower()

                if estado in ('failed', 'error', 'cancelled', 'canceled'):
                    error = data.get('error') or data.get('message') or 'desconocido'
                    print(f"Error en job Docling {task_id}: {error}")
                    return ""

                # Si el estado indica que está listo, obtener resultado
                if estado in ('completed', 'success', 'done', 'finished', 'ready'):
                    resultado = _obtener_resultado_job(url_result)
                    if resultado:
                        return resultado
                    # Si no hay resultado aún, seguir esperando
        except requests.exceptions.ConnectionError:
            print(f"No se pudo conectar al servidor Docling al consultar job {task_id}")
        except requests.exceptions.Timeout:
            print(f"Timeout al consultar estado del job Docling {task_id}")
        except Exception as e:
            print(f"Error al consultar estado del job Docling {task_id}: {e}")

        time.sleep(3)

    print(f"Timeout esperando el job Docling {task_id}")
    return ""


def _obtener_resultado_job(url_result):
    """
    Obtiene el resultado final de un job asíncrono.

    :param url_result: URL del resultado (GET /v1/result/{task_id})
    :return: Texto Markdown del resultado o cadena vacía
    """
    try:
        respuesta = requests.get(url_result, timeout=30)
        if respuesta.status_code == 200:
            try:
                data = respuesta.json()
                md = _extraer_markdown_de_respuesta(data)
                if md and md.strip():
                    return md
            except ValueError:
                # La respuesta podría ser texto plano
                if respuesta.text and respuesta.text.strip():
                    return respuesta.text
    except Exception as e:
        print(f"Error al obtener resultado del job Docling: {e}")

    return ""


def _construir_opciones_base(to_formats='md'):
    """
    Construye las opciones de conversión por defecto para el servidor Docling.

    :param to_formats: Formato de salida (md, json, html, etc.)
    :return: Diccionario de opciones
    """
    return {
        'to_formats': [to_formats],
        'do_ocr': True,
        'force_ocr': False,
        'ocr_preset': 'auto',
        'pdf_backend': 'docling_parse',
        'table_mode': 'accurate',
        'do_table_structure': True,
        'include_images': True,
    }


def convertir_pdf_docling(stream_bytes=None, archivo_path=None, url=None):
    """
    Convierte un PDF al servidor Docling remoto y devuelve el texto en Markdown.

    El servidor Docling procesa el documento completo con OCR y reconstrucción
    de estructura, siendo mucho más preciso que la extracción simple de PyMuPDF.

    :param stream_bytes: Contenido del PDF en bytes (para archivo subido)
    :param archivo_path: Ruta del archivo en disco (alternativa a stream_bytes)
    :param url: URL del documento PDF (para PDFs desde URL)
    :return: Diccionario con 'url' o 'archivo' y el texto extraído en Markdown
    """
    docling_ip = os.getenv('DOCLING_IP', '192.168.1.47')
    docling_port = os.getenv('DOCLING_PORT', '5020')
    base_url = f"http://{docling_ip}:{docling_port}"

    opciones = _construir_opciones_base('md')

    # Caso 1: El documento viene por URL
    if url and not stream_bytes and not archivo_path:
        texto = _convertir_url_docling(base_url, url, opciones)
        return {"url": url, "texto": texto}

    # Caso 2: El documento viene como bytes subidos por formulario
    if stream_bytes is not None:
        texto = _convertir_archivo_docling(base_url, stream_bytes, 'documento.pdf', opciones)
        return {"archivo": "documento.pdf", "texto": texto}

    # Caso 3: El documento viene como ruta en disco
    if archivo_path and os.path.exists(archivo_path):
        nombre = os.path.basename(archivo_path)
        with open(archivo_path, 'rb') as f:
            contenido = f.read()
        texto = _convertir_archivo_docling(base_url, contenido, nombre, opciones)
        return {"archivo": nombre, "texto": texto}

    print("Error: No se proporcionó un PDF válido para extraer con Docling")
    return {"url": "", "texto": ""}


def _convertir_archivo_docling(base_url, contenido_bytes, nombre_archivo, opciones):
    """
    Envía un archivo al endpoint ``POST /v1/convert/file``.

    :param base_url: URL base del servidor Docling
    :param contenido_bytes: Contenido del archivo en bytes
    :param nombre_archivo: Nombre del archivo
    :param opciones: Opciones de conversión
    :return: Texto Markdown o cadena vacía
    """
    url_convert = f"{base_url}/v1/convert/file"

    headers = {'Accept': 'application/json'}
    files = {'files': (nombre_archivo, contenido_bytes, 'application/pdf')}

    # Para archivos grandes (ej. libros completos), usar directamente la conversión
    # asíncrona para evitar timeouts en el POST síncrono de solo 600s
    if len(contenido_bytes) > 5 * 1024 * 1024:  # > 5 MB
        print(f"Archivo grande ({len(contenido_bytes)} bytes), usando conversión asíncrona")
        return _convertir_archivo_docling_async(base_url, contenido_bytes, nombre_archivo, opciones)

    try:
        # Timeout amplio (10 min) para libros grandes que pueden tardar en el OCR
        respuesta = requests.post(url_convert, files=files, data=opciones,
                                  headers=headers, timeout=600)
    except requests.exceptions.ConnectionError:
        print(f"No se pudo conectar al servidor Docling en {url_convert}")
        return ""
    except requests.exceptions.Timeout:
        print(f"Timeout al conectar al servidor Docling en {url_convert}")
        return ""
    except Exception as e:
        print(f"Error inesperado al contactar Docling en {url_convert}: {e}")
        return ""

    if respuesta.status_code == 200:
        try:
            data = respuesta.json()
            md = _extraer_markdown_de_respuesta(data)
            if md and md.strip():
                return limpiar_texto_docling(md)
        except ValueError:
            # Puede devolver ZIP si se pidió descarga
            if respuesta.text and respuesta.text.strip():
                return limpiar_texto_docling(respuesta.text)
    elif respuesta.status_code == 202:
        # Conversión asíncrona: obtener task_id y esperar resultado
        try:
            data = respuesta.json()
            task_id = _extraer_task_id_de_respuesta(data)
            if task_id:
                print(f"Conversión asíncrona iniciada, task_id={task_id}")
                return _consultar_estado_job(base_url, task_id)
        except ValueError:
            pass
    else:
        # Fallback: probar versión async
        if respuesta.status_code >= 400:
            md_fallback = _convertir_archivo_docling_async(base_url, contenido_bytes, nombre_archivo, opciones)
            if md_fallback:
                return md_fallback

    print(f"Respuesta no exitosa de Docling en {url_convert}: {respuesta.status_code}")
    return ""


def _convertir_archivo_docling_async(base_url, contenido_bytes, nombre_archivo, opciones):
    """
    Envía un archivo al endpoint asíncrono ``POST /v1/convert/file/async``.

    :param base_url: URL base del servidor Docling
    :param contenido_bytes: Contenido del archivo en bytes
    :param nombre_archivo: Nombre del archivo
    :param opciones: Opciones de conversión
    :return: Texto Markdown o cadena vacía
    """
    url_convert = f"{base_url}/v1/convert/file/async"
    headers = {'Accept': 'application/json'}
    files = {'files': (nombre_archivo, contenido_bytes, 'application/pdf')}

    try:
        respuesta = requests.post(url_convert, files=files, data=opciones,
                                  headers=headers, timeout=60)
    except requests.exceptions.ConnectionError:
        print(f"No se pudo conectar al servidor Docling en {url_convert}")
        return ""
    except requests.exceptions.Timeout:
        print(f"Timeout al conectar al servidor Docling en {url_convert}")
        return ""
    except Exception as e:
        print(f"Error inesperado al contactar Docling en {url_convert}: {e}")
        return ""

    if respuesta.status_code in (200, 201, 202):
        try:
            data = respuesta.json()
            task_id = _extraer_task_id_de_respuesta(data)
            if task_id:
                print(f"Conversión asíncrona iniciada, task_id={task_id}")
                return _consultar_estado_job(base_url, task_id)
        except ValueError:
            pass

    print(f"Respuesta no exitosa de Docling async en {url_convert}: {respuesta.status_code}")
    return ""


def _convertir_url_docling(base_url, url, opciones):
    """
    Envía una URL al endpoint ``POST /v1/convert/source``.

    :param base_url: URL base del servidor Docling
    :param url: URL del documento a procesar (PDF o página web)
    :param opciones: Opciones de conversión
    :return: Texto Markdown o cadena vacía
    """
    url_convert = f"{base_url}/v1/convert/source"
    headers = {'Accept': 'application/json', 'Content-Type': 'application/json'}

    payload = {
        'sources': [
            {
                'kind': 'http',
                'url': url,
                'headers': {}
            }
        ],
        'target': {
            'kind': 'inbody'
        },
        'options': opciones,
        'callbacks': []
    }

    try:
        respuesta = requests.post(url_convert, json=payload, headers=headers, timeout=180)
    except requests.exceptions.ConnectionError:
        print(f"No se pudo conectar al servidor Docling en {url_convert}")
        return ""
    except requests.exceptions.Timeout:
        print(f"Timeout al conectar al servidor Docling en {url_convert}")
        return ""
    except Exception as e:
        print(f"Error inesperado al contactar Docling en {url_convert}: {e}")
        return ""

    if respuesta.status_code == 200:
        try:
            data = respuesta.json()
            md = _extraer_markdown_de_respuesta(data)
            if md and md.strip():
                return limpiar_texto_docling(md)
        except ValueError:
            if respuesta.text and respuesta.text.strip():
                return limpiar_texto_docling(respuesta.text)
    elif respuesta.status_code == 202:
        # Conversión asíncrona
        try:
            data = respuesta.json()
            task_id = _extraer_task_id_de_respuesta(data)
            if task_id:
                print(f"Conversión asíncrona iniciada, task_id={task_id}")
                return _consultar_estado_job(base_url, task_id)
        except ValueError:
            pass
    else:
        # Fallback a versión async
        md_fallback = _convertir_url_docling_async(base_url, url, opciones)
        if md_fallback:
            return md_fallback

    print(f"Respuesta no exitosa de Docling en {url_convert}: {respuesta.status_code}")
    return ""


def _convertir_url_docling_async(base_url, url, opciones):
    """
    Envía una URL al endpoint asíncrono ``POST /v1/convert/source/async``.

    :param base_url: URL base del servidor Docling
    :param url: URL del documento a procesar
    :param opciones: Opciones de conversión
    :return: Texto Markdown o cadena vacía
    """
    url_convert = f"{base_url}/v1/convert/source/async"
    headers = {'Accept': 'application/json', 'Content-Type': 'application/json'}

    payload = {
        'sources': [
            {
                'kind': 'http',
                'url': url,
                'headers': {}
            }
        ],
        'target': {
            'kind': 'inbody'
        },
        'options': opciones,
        'callbacks': []
    }

    try:
        respuesta = requests.post(url_convert, json=payload, headers=headers, timeout=60)
    except requests.exceptions.ConnectionError:
        print(f"No se pudo conectar al servidor Docling en {url_convert}")
        return ""
    except requests.exceptions.Timeout:
        print(f"Timeout al conectar al servidor Docling en {url_convert}")
        return ""
    except Exception as e:
        print(f"Error inesperado al contactar Docling en {url_convert}: {e}")
        return ""

    if respuesta.status_code in (200, 201, 202):
        try:
            data = respuesta.json()
            task_id = _extraer_task_id_de_respuesta(data)
            if task_id:
                print(f"Conversión asíncrona iniciada, task_id={task_id}")
                return _consultar_estado_job(base_url, task_id)
        except ValueError:
            pass

    print(f"Respuesta no exitosa de Docling async en {url_convert}: {respuesta.status_code}")
    return ""


def extraer_html_docling_remoto(url):
    """
    Convierte una página web HTML al servidor Docling remoto.

    :param url: URL de la página web a procesar
    :return: Diccionario con 'url' y el texto extraído en Markdown
    """
    docling_ip = os.getenv('DOCLING_IP', '192.168.1.47')
    docling_port = os.getenv('DOCLING_PORT', '5020')
    base_url = f"http://{docling_ip}:{docling_port}"

    opciones = _construir_opciones_base('md')

    texto = _convertir_url_docling(base_url, url, opciones)
    return {"url": url, "texto": texto}


def extraer_docling_unificado(url=None, stream_bytes=None, archivo_path=None):
    """
    Función unificada para extraer texto de PDF o HTML usando Docling remoto.

    La detección del tipo de documento se hace por el contenido:

    - Si ``url`` termina en ``.pdf`` o se pasa ``stream_bytes``/``archivo_path``,
      se trata como PDF.
    - Si ``url`` es una página web, se envía como URL.

    :param url: URL del documento (PDF o página web)
    :param stream_bytes: Contenido del PDF en bytes
    :param archivo_path: Ruta del archivo en disco
    :return: Texto extraído en formato Markdown
    """
    # Si hay un archivo o bytes, es un PDF (u otro documento a convertir)
    if stream_bytes or archivo_path:
        return convertir_pdf_docling(
            stream_bytes=stream_bytes,
            archivo_path=archivo_path,
            url=None
        )

    # Si llegó URL, puede ser PDF o página web
    if url:
        url_lower = url.lower()
        es_pdf_url = url_lower.endswith('.pdf') or (
            'pdf' in url_lower and 'document' not in url_lower
        )
        if es_pdf_url:
            return convertir_pdf_docling(url=url)
        else:
            return extraer_html_docling_remoto(url)

    print("Error: No se proporcionó ninguna entrada para extraer con Docling")
    return ""


if __name__ == "__main__":
    # Modo interactivo de pruebas
    import sys

    if len(sys.argv) > 1:
        entrada = sys.argv[1]
        if entrada.startswith('http'):
            resultado = extraer_docling_unificado(url=entrada)
            print("\nTexto extraído en formato Markdown:")
            print(resultado[:3000])
        else:
            if os.path.exists(entrada):
                resultado = convertir_pdf_docling(archivo_path=entrada)
                print("\nTexto extraído en formato Markdown:")
                print(resultado[:3000])
            else:
                print(f"El archivo no existe: {entrada}")
    else:
        print("Uso:")
        print("  python extractor_docling.py <url_o_ruta_pdf>")
        print("Ejemplos:")
        print("  python extractor_docling.py https://example.com")
        print("  python extractor_docling.py /ruta/al/documento.pdf")