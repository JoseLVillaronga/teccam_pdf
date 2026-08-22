#!/usr/bin/env python3
"""
Script temporal de diagnóstico para localizar la página que causa
'maximum recursion depth exceeded' al usar markdown2.

Conecta a MongoDB, obtiene el documento, y prueba markdown2 en cada página.
"""
import os
import sys
import traceback

from dotenv import load_dotenv
from pymongo import MongoClient
from bson import ObjectId
import markdown2

# Cargar variables de entorno
load_dotenv()

# Importar la función segura de app.py
from app import markdown_seguro

def dividir_en_paginas(texto_markdown, lineas_por_pagina=50):
    lineas = texto_markdown.split('\n')
    paginas = []
    pagina_actual = []
    contador_lineas = 0

    for linea in lineas:
        pagina_actual.append(linea)
        contador_lineas += 1

        if contador_lineas >= lineas_por_pagina and linea.strip() == '':
            paginas.append('\n'.join(pagina_actual))
            pagina_actual = []
            contador_lineas = 0

    if pagina_actual:
        paginas.append('\n'.join(pagina_actual))

    if not paginas:
        paginas = ['']

    return paginas


def main():
    doc_id_str = sys.argv[1] if len(sys.argv) > 1 else '6a89263abf7c8eaf5cadcd05'

    # Conexión a MongoDB igual que app.py
    MONGO_URI = f"mongodb://{os.getenv('MONGO_USER')}:{os.getenv('MONGO_PASS')}@{os.getenv('MONGO_HOST')}"
    client = MongoClient(
        MONGO_URI,
        serverSelectionTimeoutMS=10000,
        connectTimeoutMS=10000,
        socketTimeoutMS=600000,
        connect=False,
        maxPoolSize=20,
        retryWrites=True
    )
    db = client.teccam_pdf
    collection = db.documentos

    # Obtener el documento
    documento = collection.find_one({'_id': ObjectId(doc_id_str)})
    if not documento:
        print(f"Documento no encontrado: {doc_id_str}")
        return

    texto = documento.get('texto', '')
    titulo = documento.get('titulo', '(sin título)')
    print(f"Documento: {titulo}")
    print(f"Longitud del texto: {len(texto)} caracteres")
    print(f"Número de líneas: {texto.count(chr(10))}")
    print("=" * 80)

    # Dividir en páginas
    paginas = dividir_en_paginas(texto)
    print(f"Total de páginas: {len(paginas)}")
    print("=" * 80)

    # Probar markdown_seguro en cada página (la función corregida)
    fail_count = 0
    for i, pagina in enumerate(paginas):
        try:
            html = markdown_seguro(pagina)
            print(f"[PÁGINA {i+1}] OK ({len(html)} bytes)")
        except Exception as e:
            fail_count += 1
            print(f"[PÁGINA {i+1}] ERROR: {type(e).__name__}: {e}")

            if fail_count >= 3:
                print("Se alcanzaron 3 fallos, deteniendo diagnóstico.")
                break

    print("=" * 80)
    print(f"Total de páginas con error: {fail_count} de {len(paginas)}")

    # Mostrar una muestra del HTML generado para la primera página
    print("\nMuestra del HTML de la página 1 (primeros 800 chars):")
    print(markdown_seguro(paginas[0])[:800])


if __name__ == '__main__':
    main()