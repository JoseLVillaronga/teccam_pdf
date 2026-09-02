import os
import requests
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import html2text


def extraer_texto_html_markdown(url, doc_id=None, imagenes_dir=None, url_base_imagenes=None):
    """
    Descarga una página HTML desde una URL, elimina menús y componentes interactivos,
    descarga imágenes locales si se especifica un directorio,
    y extrae el contenido textual respetando los estilos y saltos de línea, convirtiéndolo a Markdown.
    
    :param url: URL de la página HTML a descargar.
    :param doc_id: ID del documento (opcional).
    :param imagenes_dir: Directorio local donde guardar imágenes descargadas (opcional).
    :param url_base_imagenes: URL base o prefijo web para referenciar las imágenes en Markdown (opcional).
    :return: Diccionario con la URL y el texto extraído en formato Markdown.
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        # Descargamos el contenido HTML
        respuesta = requests.get(url, headers=headers, timeout=30)
        respuesta.raise_for_status()
        html_contenido = respuesta.text

        # Parseamos el HTML con BeautifulSoup
        soup = BeautifulSoup(html_contenido, "html.parser")
        
        # Eliminamos etiquetas que usualmente contienen elementos interactivos o no deseados.
        # Conservamos <img> para procesarlas.
        for etiqueta in soup(["nav", "header", "footer", "aside", "script", "style", 
                              "form", "input", "button", "select", "option", "noscript", "iframe"]):
            etiqueta.decompose()

        # Extraemos el contenido principal (body o todo el documento)
        contenido_principal = soup.body or soup

        # Procesar y descargar imágenes si se configuró un directorio
        if imagenes_dir and url_base_imagenes:
            os.makedirs(imagenes_dir, exist_ok=True)
            img_index = 1
            for img_tag in contenido_principal.find_all('img'):
                # Obtener la URL de la imagen (soportando atributos de lazy-loading)
                src = img_tag.get('src') or img_tag.get('data-src') or img_tag.get('data-original') or ''
                src = src.strip()
                
                # Ignorar imágenes en base64 o vacías
                if not src or src.startswith('data:'):
                    img_tag.decompose()
                    continue

                full_img_url = urljoin(url, src)
                
                # Descargar imagen
                try:
                    res_img = requests.get(full_img_url, headers=headers, timeout=15)
                    if res_img.status_code == 200 and len(res_img.content) > 1024:  # Descartar pixels < 1KB
                        content_type = res_img.headers.get('Content-Type', '').lower()
                        if 'png' in content_type:
                            ext = 'png'
                        elif 'webp' in content_type:
                            ext = 'webp'
                        elif 'gif' in content_type:
                            ext = 'gif'
                        elif 'svg' in content_type:
                            ext = 'svg'
                        else:
                            # Detectar de la URL o usar jpg por defecto
                            parsed_path = urlparse(full_img_url).path
                            ext_candidate = os.path.splitext(parsed_path)[1].lstrip('.').lower()
                            ext = ext_candidate if ext_candidate in ['jpg', 'jpeg', 'png', 'webp', 'gif'] else 'jpg'

                        img_filename = f"web_img_{img_index}.{ext}"
                        img_filepath = os.path.join(imagenes_dir, img_filename)
                        
                        with open(img_filepath, 'wb') as f_img:
                            f_img.write(res_img.content)

                        # Reemplazar la URL en el tag por la URL local estática
                        img_tag['src'] = f"{url_base_imagenes.rstrip('/')}/{img_filename}"
                        img_index += 1
                    else:
                        img_tag.decompose()
                except Exception as err_img:
                    print(f"No se pudo descargar imagen {full_img_url}: {err_img}")
                    img_tag.decompose()

        # Convertimos el HTML limpio a cadena
        html_limpio = str(contenido_principal)
        
        # Configuramos html2text para convertir a Markdown
        conversor = html2text.HTML2Text()
        conversor.ignore_links = False
        conversor.ignore_images = False if (imagenes_dir and url_base_imagenes) else True
        conversor.body_width = 0
        
        markdown_texto = conversor.handle(html_limpio)
        
        return {"url": url, "texto": markdown_texto}
    
    except Exception as e:
        print(f"Error al procesar la página HTML: {e}")
        return {"url": url, "texto": "", "error": str(e)}

if __name__ == "__main__":
    # Modo interactivo: se pide al usuario la URL de la página HTML a descargar
    url_usuario = input("Ingrese la URL de la página HTML: ").strip()
    resultado = extraer_texto_html_markdown(url_usuario)
    print("\nTexto extraído en formato Markdown:")
    print(resultado["texto"])
