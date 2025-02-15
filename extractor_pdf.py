import sys
import subprocess

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
instalar_paquete("pymupdf4llm")
instalar_paquete("PyMuPDF", "fitz")

import requests
import fitz  # PyMuPDF
import pymupdf4llm
import pathlib

def extraer_texto_pdf_markdown(url):
    """
    Descarga un documento PDF desde una URL y extrae el texto en formato Markdown 
    utilizando la librería pymupdf4llm.
    
    :param url: URL del documento PDF a descargar.
    :return: Diccionario con la URL y el texto extraído en formato Markdown.
             Ejemplo:
             {
                 "url": "http://ejemplo.com/documento.pdf",
                 "texto": "Texto extraído en formato Markdown..."
             }
    """
    try:
        # Descarga el archivo PDF
        respuesta = requests.get(url)
        respuesta.raise_for_status()  # Lanza excepción si hay error en la descarga

        # Abrir el PDF desde los datos en memoria usando PyMuPDF (fitz)
        doc = fitz.open(stream=respuesta.content, filetype="pdf")
        
        # Convertir el documento a Markdown usando pymupdf4llm
        md_text = pymupdf4llm.to_markdown(doc)
        
        return {"url": url, "texto": md_text}
    
    except Exception as e:
        print(f"Error al procesar el PDF: {e}")
        return {"url": url, "texto": ""}

if __name__ == "__main__":
    # Modo interactivo: se pide al usuario la URL del PDF a descargar
    url_usuario = input("Ingrese la URL del documento PDF: ").strip()
    resultado = extraer_texto_pdf_markdown(url_usuario)
    print("\nTexto extraído en formato Markdown:")
    print(resultado["texto"])

