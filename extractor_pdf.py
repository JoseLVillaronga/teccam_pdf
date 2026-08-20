import re
import os
import requests
import fitz  # PyMuPDF




def limpiar_texto_pdf(texto):
    """
    Limpia y reestructura el texto extraído de un PDF para preservar
    los saltos de línea dentro del párrafo y unir palabras partidas por guión.
    
    Características:
    - Une palabras partidas por guión al final de línea con la sílaba siguiente
    - Preserva líneas consecutivas dentro del mismo párrafo con \n
    - Separa párrafos con \n\n (doble salto de línea)
    - Detecta nuevas páginas (form feed) y las marca como separación
    
    :param texto: Texto crudo extraído del PDF
    :return: Texto limpio con párrafos bien formados
    """
    if not texto.strip():
        return texto
    
    # Paso 1: Separar el texto en líneas, preservando las líneas en blanco como separadores
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
            # Unir líneas del párrafo con \n (salto de línea simple)
            # para que Markdown pueda renderizarlas con <br>
            texto_parrafo = '\n'.join(parrafo_actual)
            # Limpiar espacios múltiples
            texto_parrafo = re.sub(r' +', ' ', texto_parrafo)
            # Limpiar espacios antes de puntuación
            texto_parrafo = re.sub(r'\s+([.,;:!?\)\]])', r'\1', texto_parrafo)
            # Limpiar espacios después de apertura
            texto_parrafo = re.sub(r'([\(\[])\s+', r'\1', texto_parrafo)
            parrafos.append(texto_parrafo.strip())
            parrafo_actual.clear()
    
    for linea in lineas:
        linea_stripped = linea.strip()
        
        # Línea vacía = separador de párrafos
        if not linea_stripped:
            finalizar_parrafo()
            continue
        
        # Detectar cambio de página (form feed o similar)
        if linea_stripped.startswith('\x0c') or linea_stripped.startswith('[PAGE'):
            finalizar_parrafo()
            # Agregar el marcador de página
            parrafos.append(linea_stripped)
            continue
        
        # Si la línea previa terminó con guión, unimos la primera palabra/sílaba
        if linea_pendiente_guion is not None:
            partes = linea_stripped.split(None, 1)
            primera_palabra = partes[0]
            resto = partes[1] if len(partes) > 1 else ""
            
            # Reconstruimos la palabra completa en la línea superior
            linea_reconstruida = linea_pendiente_guion + primera_palabra
            parrafo_actual.append(linea_reconstruida)
            linea_pendiente_guion = None
            
            # Si no quedó más texto en esta línea, continuamos a la siguiente
            if not resto:
                continue
            linea_stripped = resto
        
        # Detectar si la línea actual termina con guión (palabra partida)
        if (linea_stripped.endswith('-') or linea_stripped.endswith('—')) and len(linea_stripped) > 1:
            # Guardar la línea sin el guión en espera de la siguiente línea
            linea_pendiente_guion = linea_stripped.rstrip('-—').rstrip()
        elif parrafo_actual and len(linea_stripped) > 0:
            # Verificar si la línea actual parece continuación:
            # - No comienza con mayúscula (probable continuación)
            # - O es muy corta
            # - O la línea anterior no terminaba con punto
            linea_anterior = parrafo_actual[-1] if parrafo_actual else ''
            
            es_continuacion = (
                # No comienza con mayúscula (es continuación directa)
                not linea_stripped[0].isupper() and len(linea_stripped) < 100
                # O la línea anterior no terminaba con punto (no es fin de oración)
                or (linea_anterior and not linea_anterior.rstrip().endswith('.'))
            )
            
            if es_continuacion:
                parrafo_actual.append(linea_stripped)
            else:
                # Nueva oración que podría ser parte del mismo párrafo
                # pero chequeamos si hay suficiente separación lógica
                if linea_anterior and linea_anterior.rstrip().endswith('.') and len(linea_stripped) > 3:
                    parrafo_actual.append(linea_stripped)
                else:
                    finalizar_parrafo()
                    parrafo_actual.append(linea_stripped)
        else:
            parrafo_actual.append(linea_stripped)
    
    # Finalizar el último párrafo
    finalizar_parrafo()
    
    return '\n\n'.join(parrafos)


def extraer_texto_pdf_directo(stream_bytes, doc_id=None, imagenes_dir=None, url_base_imagenes=None, min_width=100, min_height=100):
    """
    Extrae texto de un PDF usando PyMuPDF (fitz) directamente,
    con limpieza para preservar saltos de línea y párrafos, y extracción opcional de imágenes.
    
    :param stream_bytes: Contenido del PDF en bytes
    :param doc_id: ID del documento (opcional)
    :param imagenes_dir: Directorio local en disco donde guardar las imágenes extraídas (opcional)
    :param url_base_imagenes: URL base o prefijo web para referenciar las imágenes en Markdown (opcional)
    :param min_width: Ancho mínimo en px para extraer una imagen (descarta iconos o líneas)
    :param min_height: Alto mínimo en px para extraer una imagen
    :return: Texto extraído en formato Markdown con referencias a imágenes
    """
    try:
        doc = fitz.open(stream=stream_bytes, filetype="pdf")
        paginas_texto = []
        
        if imagenes_dir:
            os.makedirs(imagenes_dir, exist_ok=True)
            
        xrefs_procesados = set()

        for num_pagina in range(len(doc)):
            pagina = doc[num_pagina]
            texto_pagina = pagina.get_text("text")
            texto_limpio = limpiar_texto_pdf(texto_pagina)
            
            # Extracción de imágenes de la página
            markdown_imagenes = []
            if imagenes_dir and url_base_imagenes:
                try:
                    image_list = pagina.get_images(full=True)
                    for img_idx, img_info in enumerate(image_list, start=1):
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
                            
                        img_filename = f"pag_{num_pagina + 1}_img_{img_idx}.{image_ext}"
                        img_filepath = os.path.join(imagenes_dir, img_filename)
                        
                        with open(img_filepath, "wb") as f:
                            f.write(image_bytes)
                            
                        xrefs_procesados.add(xref)
                        img_url = f"{url_base_imagenes.rstrip('/')}/{img_filename}"
                        markdown_imagenes.append(f"\n\n![Figura {img_idx} (Pág. {num_pagina + 1})]({img_url})\n\n")
                except Exception as img_err:
                    print(f"Advertencia al extraer imágenes de página {num_pagina + 1}: {img_err}")
            
            # Ensamblar contenido de la página
            contenido_pagina = texto_limpio.strip()
            if markdown_imagenes:
                if contenido_pagina:
                    contenido_pagina += "".join(markdown_imagenes)
                else:
                    contenido_pagina = "".join(markdown_imagenes).strip()
                    
            if contenido_pagina:
                paginas_texto.append(contenido_pagina)
        
        doc.close()
        
        # Unir todas las páginas con separación
        texto_completo = '\n\n---\n\n'.join(paginas_texto)
        return texto_completo
    
    except Exception as e:
        print(f"Error al extraer texto e imágenes del PDF: {e}")
        return ""


def extraer_texto_pdf_markdown(url, doc_id=None, imagenes_dir=None, url_base_imagenes=None):
    """
    Descarga un documento PDF desde una URL y extrae el texto en formato Markdown
    usando extracción directa con PyMuPDF.
    
    :param url: URL del documento PDF a descargar.
    :param doc_id: ID del documento (opcional)
    :param imagenes_dir: Directorio local donde guardar imágenes
    :param url_base_imagenes: URL base de imágenes
    :return: Diccionario con la URL y el texto extraído en formato Markdown.
    """
    try:
        respuesta = requests.get(url, timeout=30)
        respuesta.raise_for_status()
        
        texto_extraido = extraer_texto_pdf_directo(
            respuesta.content,
            doc_id=doc_id,
            imagenes_dir=imagenes_dir,
            url_base_imagenes=url_base_imagenes
        )
        
        return {"url": url, "texto": texto_extraido}
    
    except Exception as e:
        print(f"Error al procesar el PDF desde URL: {e}")
        return {"url": url, "texto": ""}


def extraer_texto_pdf_archivo(archivo_bytes, nombre_archivo, doc_id=None, imagenes_dir=None, url_base_imagenes=None):
    """
    Extrae el texto de un archivo PDF subido directamente, en formato Markdown.
    
    :param archivo_bytes: Contenido del archivo PDF en bytes.
    :param nombre_archivo: Nombre del archivo original (para identificación).
    :param doc_id: ID del documento (opcional)
    :param imagenes_dir: Directorio local donde guardar imágenes
    :param url_base_imagenes: URL base de imágenes
    :return: Diccionario con el nombre del archivo y el texto extraído en formato Markdown.
    """
    try:
        texto_extraido = extraer_texto_pdf_directo(
            archivo_bytes,
            doc_id=doc_id,
            imagenes_dir=imagenes_dir,
            url_base_imagenes=url_base_imagenes
        )
        
        return {"archivo": nombre_archivo, "texto": texto_extraido}
    
    except Exception as e:
        print(f"Error al procesar el archivo PDF '{nombre_archivo}': {e}")
        return {"archivo": nombre_archivo, "texto": ""}


if __name__ == "__main__":
    # Modo interactivo: se pide al usuario la URL del PDF a descargar
    url_usuario = input("Ingrese la URL del documento PDF: ").strip()
    resultado = extraer_texto_pdf_markdown(url_usuario)
    print("\nTexto extraído en formato Markdown:")
    print(resultado["texto"])