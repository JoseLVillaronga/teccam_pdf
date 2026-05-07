import sys
import subprocess
import re

def instalar_paquete(paquete, nombre_modulo=None):
    """
    Instala un paquete mediante pip si no está ya instalado.
    
    :param paquete: Nombre del paquete para instalar con pip.
    :param nombre_modulo: Nombre del módulo a importar (si es distinto del nombre del paquete).
    """
    nombre_modulo = nombre_modulo or paquete
    try:
        __import__(nombre_modulo)
    except ImportError:
        print(f"Instalando el paquete '{paquete}'...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", paquete])

# Instalamos las dependencias necesarias
instalar_paquete("requests")
instalar_paquete("PyMuPDF", "fitz")

import requests
import fitz  # PyMuPDF


def limpiar_texto_pdf(texto):
    """
    Limpia y reestructura el texto extraído de un PDF para unir líneas
    que pertenecen al mismo párrafo.
    
    Características:
    - Une líneas que terminan con un guión (palabras partidas por salto de línea)
    - Une líneas consecutivas que no tienen separación (mismo párrafo)
    - Preserva párrafos separados por líneas en blanco
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
    
    def finalizar_parrafo():
        if parrafo_actual:
            texto_parrafo = ' '.join(parrafo_actual)
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
        
        # Detectar si la línea termina con guión (palabra partida)
        if linea.endswith('-') or linea.endswith('-\n'):
            # Quitar el guión y agregar sin espacio (la palabra continúa)
            parrafo_actual.append(linea_stripped.rstrip('-'))
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
                    # Si la línea anterior termina en punto y esta empieza con
                    # mayúscula, podría ser nueva oración en el mismo párrafo
                    parrafo_actual.append(linea_stripped)
                else:
                    finalizar_parrafo()
                    parrafo_actual.append(linea_stripped)
        else:
            parrafo_actual.append(linea_stripped)
    
    # Finalizar el último párrafo
    finalizar_parrafo()
    
    return '\n\n'.join(parrafos)


def extraer_texto_pdf_directo(stream_bytes):
    """
    Extrae texto de un PDF usando PyMuPDF (fitz) directamente,
    con limpieza para preservar saltos de línea y párrafos.
    
    :param stream_bytes: Contenido del PDF en bytes
    :return: Texto extraído en formato Markdown
    """
    try:
        doc = fitz.open(stream=stream_bytes, filetype="pdf")
        paginas_texto = []
        
        for num_pagina in range(len(doc)):
            pagina = doc[num_pagina]
            texto_pagina = pagina.get_text("text")
            texto_limpio = limpiar_texto_pdf(texto_pagina)
            if texto_limpio.strip():
                paginas_texto.append(texto_limpio)
        
        doc.close()
        
        # Unir todas las páginas con separación
        texto_completo = '\n\n---\n\n'.join(paginas_texto)
        return texto_completo
    
    except Exception as e:
        print(f"Error al extraer texto del PDF: {e}")
        return ""


def extraer_texto_pdf_markdown(url):
    """
    Descarga un documento PDF desde una URL y extrae el texto en formato Markdown
    usando extracción directa con PyMuPDF.
    
    :param url: URL del documento PDF a descargar.
    :return: Diccionario con la URL y el texto extraído en formato Markdown.
    """
    try:
        respuesta = requests.get(url)
        respuesta.raise_for_status()
        
        texto_extraido = extraer_texto_pdf_directo(respuesta.content)
        
        return {"url": url, "texto": texto_extraido}
    
    except Exception as e:
        print(f"Error al procesar el PDF desde URL: {e}")
        return {"url": url, "texto": ""}


def extraer_texto_pdf_archivo(archivo_bytes, nombre_archivo):
    """
    Extrae el texto de un archivo PDF subido directamente, en formato Markdown.
    
    :param archivo_bytes: Contenido del archivo PDF en bytes.
    :param nombre_archivo: Nombre del archivo original (para identificación).
    :return: Diccionario con el nombre del archivo y el texto extraído en formato Markdown.
    """
    try:
        texto_extraido = extraer_texto_pdf_directo(archivo_bytes)
        
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