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
from urllib.parse import urlparse

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


def extraer_imagenes_pdf_pymupdf(stream_bytes, doc_id=None, imagenes_dir=None, url_base_imagenes=None, min_width=100, min_height=100):
    """
    Extrae las imágenes de un PDF usando PyMuPDF y las guarda en el directorio
    local ``imagenes_dir``, devolviendo una lista con las referencias Markdown
    en el orden en que aparecen en el documento.

    Esta función se usa para complementar la extracción de Docling: Docling
    coloca ``<!-- image -->`` como placeholder en el Markdown, pero no guarda
    las imágenes. Con este helper extraemos las imágenes reales del PDF y las
    asociamos a los placeholders de Docling.

    :param stream_bytes: Contenido del PDF en bytes
    :param doc_id: ID del documento (para la ruta de imágenes)
    :param imagenes_dir: Directorio local donde guardar las imágenes
    :param url_base_imagenes: URL base para referenciar las imágenes en Markdown
    :param min_width: Ancho mínimo en px para considerar una imagen relevante
    :param min_height: Alto mínimo en px para considerar una imagen relevante
    :return: Lista de cadenas Markdown ``![Figura X](url)`` en orden de aparición
    """
    import fitz  # PyMuPDF (import local para no acoplar el módulo)

    if not stream_bytes:
        return []

    if imagenes_dir:
        os.makedirs(imagenes_dir, exist_ok=True)

    referencias_markdown = []
    try:
        doc = fitz.open(stream=stream_bytes, filetype="pdf")
        xrefs_procesados = set()
        contador_img = 0

        for num_pagina in range(len(doc)):
            pagina = doc[num_pagina]
            try:
                image_list = pagina.get_images(full=True)
                for img_info in image_list:
                    xref = img_info[0]
                    if xref in xrefs_procesados:
                        continue

                    base_image = doc.extract_image(xref)
                    if not base_image:
                        continue

                    w = base_image.get("width", 0)
                    h = base_image.get("height", 0)

                    # Filtrar imágenes diminutas (iconos, separadores, logos pequeños)
                    if w < min_width or h < min_height:
                        continue

                    image_bytes = base_image.get("image")
                    image_ext = base_image.get("ext", "png")

                    if not image_bytes:
                        continue

                    contador_img += 1
                    img_filename = f"pag_{num_pagina + 1}_img_{contador_img}.{image_ext}"
                    if imagenes_dir:
                        img_filepath = os.path.join(imagenes_dir, img_filename)
                        with open(img_filepath, "wb") as f:
                            f.write(image_bytes)

                    xrefs_procesados.add(xref)

                    if url_base_imagenes:
                        img_url = f"{url_base_imagenes.rstrip('/')}/{img_filename}"
                        referencias_markdown.append(f"![Figura {contador_img} (Pág. {num_pagina + 1})]({img_url})")
            except Exception as img_err:
                print(f"Advertencia al extraer imágenes de página {num_pagina + 1}: {img_err}")

        doc.close()
    except Exception as e:
        print(f"Error al extraer imágenes con PyMuPDF: {e}")

    return referencias_markdown


def integrar_imagenes_en_markdown(texto_markdown, referencias_imagenes):
    """
    Reemplaza los placeholders ``<!-- image -->`` que Docling inserta en el
    Markdown por las referencias reales a las imágenes extraídas localmente.

    Si hay más imágenes referencias que placeholders, las imágenes adicionales
    se agregan al final del Markdown. Si hay menos imágenes que placeholders,
    los placeholders restantes se eliminan.

    :param texto_markdown: Markdown de Docling con ``<!-- image -->``
    :param referencias_imagenes: Lista de cadenas Markdown de imágenes
    :return: Markdown con las imágenes reemplazadas
    """
    if not texto_markdown:
        return texto_markdown

    import re as _re

    # Contar placeholders existentes
    placeholders = _re.findall(r'<!--\s*image\s*-->', texto_markdown, flags=_re.IGNORECASE)
    if not placeholders:
        # No hay placeholders: si hay imágenes, agregarlas al final
        if referencias_imagenes:
            imagenes_extra = '\n\n'.join(referencias_imagenes)
            return f"{texto_markdown}\n\n{imagenes_extra}"
        return texto_markdown

    # Reemplazar cada placeholder por la siguiente imagen disponible
    idx_imagen = 0
    def reemplazar(match):
        nonlocal idx_imagen
        if idx_imagen < len(referencias_imagenes):
            ref = referencias_imagenes[idx_imagen]
            idx_imagen += 1
            return f"\n\n{ref}\n\n"
        else:
            # No hay más imágenes: eliminar el placeholder
            return ""

    texto_con_imagenes = _re.sub(r'<!--\s*image\s*-->', reemplazar, texto_markdown, flags=_re.IGNORECASE)

    # Si quedaron imágenes sin usar, agregarlas al final
    if idx_imagen < len(referencias_imagenes):
        imagenes_restantes = referencias_imagenes[idx_imagen:]
        imagenes_extra = '\n\n'.join(imagenes_restantes)
        texto_con_imagenes = f"{texto_con_imagenes}\n\n{imagenes_extra}"

    return texto_con_imagenes


def convertir_pdf_docling(stream_bytes=None, archivo_path=None, url=None, doc_id=None, imagenes_dir=None, url_base_imagenes=None):
    """
    Convierte un PDF al servidor Docling remoto y devuelve el texto en Markdown.

    El servidor Docling procesa el documento completo con OCR y reconstrucción
    de estructura, siendo mucho más preciso que la extracción simple de PyMuPDF.

    Si se proporcionan ``imagenes_dir`` y ``url_base_imagenes``, se extraen las
    imágenes del PDF con PyMuPDF y se reemplazan los placeholders ``<!-- image -->``
    de Docling por referencias reales a las imágenes guardadas localmente.

    :param stream_bytes: Contenido del PDF en bytes (para archivo subido)
    :param archivo_path: Ruta del archivo en disco (alternativa a stream_bytes)
    :param url: URL del documento PDF (para PDFs desde URL)
    :param doc_id: ID del documento (para asociar imágenes al documento)
    :param imagenes_dir: Directorio local donde guardar las imágenes extraídas
    :param url_base_imagenes: URL base para referenciar las imágenes en Markdown
    :return: Diccionario con 'url' o 'archivo' y el texto extraído en Markdown
    """
    docling_ip = os.getenv('DOCLING_IP', '192.168.1.47')
    docling_port = os.getenv('DOCLING_PORT', '5020')
    base_url = f"http://{docling_ip}:{docling_port}"

    opciones = _construir_opciones_base('md')

    # Bytes del PDF (para extracción de imágenes complementaria)
    pdf_bytes = None
    nombre_pdf = None
    es_url = False

    # Caso 1: El documento viene por URL
    if url and not stream_bytes and not archivo_path:
        es_url = True
        texto = _convertir_url_docling(base_url, url, opciones)
        # Intentar descargar el PDF desde la URL para poder extraer imágenes
        # complementarias con PyMuPDF y reemplazar los placeholders de Docling
        try:
            respuesta = requests.get(url, timeout=30)
            respuesta.raise_for_status()
            pdf_bytes = respuesta.content
            nombre_pdf = os.path.basename(urlparse(url).path) or 'documento.pdf'
        except Exception as e:
            print(f"No se pudo descargar el PDF desde URL para extraer imágenes: {e}")
            pdf_bytes = None
            nombre_pdf = None

    # Caso 2: El documento viene como bytes subidos por formulario
    elif stream_bytes is not None:
        pdf_bytes = stream_bytes
        nombre_pdf = 'documento.pdf'
        texto = _convertir_archivo_docling(base_url, stream_bytes, nombre_pdf, opciones)

    # Caso 3: El documento viene como ruta en disco
    elif archivo_path and os.path.exists(archivo_path):
        nombre_pdf = os.path.basename(archivo_path)
        with open(archivo_path, 'rb') as f:
            pdf_bytes = f.read()
        texto = _convertir_archivo_docling(base_url, pdf_bytes, nombre_pdf, opciones)

    else:
        print("Error: No se proporcionó un PDF válido para extraer con Docling")
        return {"url": "", "texto": ""}

    # Complementar con imágenes extraídas por PyMuPDF
    if pdf_bytes and imagenes_dir and url_base_imagenes:
        referencias_imagenes = extraer_imagenes_pdf_pymupdf(
            pdf_bytes,
            doc_id=doc_id,
            imagenes_dir=imagenes_dir,
            url_base_imagenes=url_base_imagenes
        )
        if referencias_imagenes:
            texto = integrar_imagenes_en_markdown(texto, referencias_imagenes)

    if es_url:
        return {"url": url, "texto": texto}
    else:
        return {"archivo": nombre_pdf, "texto": texto}


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


def extraer_docling_unificado(url=None, stream_bytes=None, archivo_path=None, doc_id=None, imagenes_dir=None, url_base_imagenes=None):
    """
    Función unificada para extraer texto de PDF o HTML usando Docling remoto.

    La detección del tipo de documento se hace por el contenido:

    - Si ``url`` termina en ``.pdf`` o se pasa ``stream_bytes``/``archivo_path``,
      se trata como PDF.
    - Si ``url`` es una página web, se envía como URL.

    Si se proporcionan ``imagenes_dir`` y ``url_base_imagenes``, se extraen las
    imágenes del PDF con PyMuPDF y se reemplazan los placeholders de Docling
    por referencias reales a imágenes guardadas localmente.

    :param url: URL del documento (PDF o página web)
    :param stream_bytes: Contenido del PDF en bytes
    :param archivo_path: Ruta del archivo en disco
    :param doc_id: ID del documento (para asociar imágenes)
    :param imagenes_dir: Directorio local donde guardar las imágenes extraídas
    :param url_base_imagenes: URL base para referenciar las imágenes en Markdown
    :return: Texto extraído en formato Markdown
    """
    # Si hay un archivo o bytes, es un PDF (u otro documento a convertir)
    if stream_bytes or archivo_path:
        return convertir_pdf_docling(
            stream_bytes=stream_bytes,
            archivo_path=archivo_path,
            url=None,
            doc_id=doc_id,
            imagenes_dir=imagenes_dir,
            url_base_imagenes=url_base_imagenes
        )

    # Si llegó URL, puede ser PDF o página web
    if url:
        url_lower = url.lower()
        es_pdf_url = url_lower.endswith('.pdf') or (
            'pdf' in url_lower and 'document' not in url_lower
        )
        if es_pdf_url:
            return convertir_pdf_docling(
                url=url,
                doc_id=doc_id,
                imagenes_dir=imagenes_dir,
                url_base_imagenes=url_base_imagenes
            )
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