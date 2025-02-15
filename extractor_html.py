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
instalar_paquete("beautifulsoup4", "bs4")
instalar_paquete("html2text")

# Importamos los módulos instalados
import requests
from bs4 import BeautifulSoup
import html2text

def extraer_texto_html_markdown(url):
    """
    Descarga una página HTML desde una URL, elimina menús y componentes interactivos,
    y extrae el contenido textual respetando los estilos y saltos de línea, convirtiéndolo a Markdown.
    
    La función procesa el HTML eliminando etiquetas que generalmente contienen componentes
    interactivos o que no forman parte del contenido principal (por ejemplo: <nav>, <header>, 
    <footer>, <aside>, <script>, <style>, <form>, etc.). Luego utiliza 'html2text' para la 
    conversión a Markdown.
    
    :param url: URL de la página HTML a descargar.
    :return: Diccionario con la URL y el texto extraído en formato Markdown.
             Ejemplo:
             {
                 "url": "http://ejemplo.com/pagina.html",
                 "texto": "## Título\n\nContenido extraído..."
             }
    """
    try:
        # Descargamos el contenido HTML
        respuesta = requests.get(url)
        respuesta.raise_for_status()
        html_contenido = respuesta.text

        # Parseamos el HTML con BeautifulSoup
        soup = BeautifulSoup(html_contenido, "html.parser")
        
        # Eliminamos etiquetas que usualmente contienen elementos no deseados.
        # Se pueden ampliar según las necesidades.
        for etiqueta in soup(["nav", "header", "footer", "aside", "script", "style", 
                              "form", "input", "button", "select", "option", "img"]):
            etiqueta.decompose()
        
        # Opcional: Si la página utiliza comentarios u otros elementos no deseados,
        # se podrían eliminar aquí.
        # Extraemos el contenido limpio. En este ejemplo se utiliza el <body> si existe.
        contenido_principal = soup.body or soup
        
        # Convertimos el HTML limpio a cadena
        html_limpio = str(contenido_principal)
        
        # Configuramos html2text para convertir a Markdown
        conversor = html2text.HTML2Text()
        conversor.ignore_links = False  # Si se desea conservar los enlaces
        conversor.ignore_images = True  # Se ignoran las imágenes
        conversor.body_width = 0  # Para evitar el ajuste de línea forzado
        
        markdown_texto = conversor.handle(html_limpio)
        
        return {"url": url, "texto": markdown_texto}
    
    except Exception as e:
        print(f"Error al procesar la página HTML: {e}")
        return {"url": url, "texto": ""}

if __name__ == "__main__":
    # Modo interactivo: se pide al usuario la URL de la página HTML a descargar
    url_usuario = input("Ingrese la URL de la página HTML: ").strip()
    resultado = extraer_texto_html_markdown(url_usuario)
    print("\nTexto extraído en formato Markdown:")
    print(resultado["texto"])
