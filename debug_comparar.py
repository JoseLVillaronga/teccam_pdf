#!/usr/bin/env python3
"""
Compara dos documentos del mismo libro en MongoDB:
uno extraído con el motor viejo (PyMuPDF) y otro con Docling.
Muestra cantidad de caracteres, palabras y páginas.
"""

from pymongo import MongoClient
from dotenv import load_dotenv
import os
import re
import sys

load_dotenv()

user = os.getenv('MONGO_USER')
password = os.getenv('MONGO_PASS')
host = os.getenv('MONGO_HOST')

mongo_uri = f"mongodb://{user}:{password}@{host}"

# Título a buscar (del feedback: "Rito de Cortejo")
titulo = sys.argv[1] if len(sys.argv) > 1 else "Rito de Cortejo"

try:
    client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
    client.admin.command('ping')
    db = client.teccam_pdf
    collection = db.documentos

    # Buscar documentos con ese título, ordenados por fecha de creación descendente
    docs = list(collection.find(
        {'titulo': {'$regex': titulo, '$options': 'i'}},
        {'titulo': 1, 'autor': 1, 'tema': 1, 'texto': 1, 'fecha_creacion': 1, 'url': 1}
    ).sort('fecha_creacion', -1))

    if len(docs) < 2:
        print(f"⚠️  Se encontraron {len(docs)} documento(s) con título que contiene '{titulo}'. Se necesitan al menos 2.")
        for d in docs:
            print(f"  - {d['titulo']} (fecha: {d.get('fecha_creacion')})")
        sys.exit(1)

    # Tomar los dos más recientes
    doc_viejo = docs[1]  # El segundo más reciente (probablemente motor viejo)
    doc_docling = docs[0]  # El más reciente (probablemente Docling)

    print("=" * 80)
    print("COMPARACIÓN DE DOCUMENTOS")
    print("=" * 80)

    for nombre, doc in [("DOCLING (más reciente)", doc_docling), ("VIEJO (anterior)", doc_viejo)]:
        texto = doc.get('texto', '')
        palabras = len(re.findall(r'\b\w+\b', texto))
        caracteres = len(texto)
        lineas = texto.count('\n') + 1
        paginas_estimadas = len(texto) // 5000  # Aproximado: ~5000 chars/página

        print(f"\n--- {nombre} ---")
        print(f"  ID: {doc['_id']}")
        print(f"  Título: {doc['titulo']}")
        print(f"  Autor: {doc.get('autor')}")
        print(f"  Tema: {doc.get('tema')}")
        print(f"  URL: {doc.get('url')}")
        print(f"  Fecha creación: {doc.get('fecha_creacion')}")
        print(f"  Caracteres: {caracteres:,}")
        print(f"  Palabras: {palabras:,}")
        print(f"  Líneas: {lineas:,}")
        print(f"  Aprox. páginas (5000 chars): {paginas_estimadas}")

    # Comparación
    texto_viejo = doc_viejo.get('texto', '')
    texto_docling = doc_docling.get('texto', '')

    palabras_viejo = len(re.findall(r'\b\w+\b', texto_viejo))
    palabras_docling = len(re.findall(r'\b\w+\b', texto_docling))

    caracteres_viejo = len(texto_viejo)
    caracteres_docling = len(texto_docling)

    print("\n" + "=" * 80)
    print("RESULTADO DE LA COMPARACIÓN")
    print("=" * 80)
    print(f"  Caracteres: Docling {caracteres_docling:,} vs Viejo {caracteres_viejo:,} → ratio {caracteres_docling/max(caracteres_viejo,1):.2f}x")
    print(f"  Palabras: Docling {palabras_docling:,} vs Viejo {palabras_viejo:,} → ratio {palabras_docling/max(palabras_viejo,1):.2f}x")
    print(f"  Diferencias: Docling tiene {abs(caracteres_docling-caracteres_viejo):,} caracteres {'más' if caracteres_docling>caracteres_viejo else 'menos'}")

    # Verificación cualitativa: primeros 200 chars de cada uno
    print("\n--- PRIMEROS 300 CARACTERES ---")
    print(f"DOCLING: {texto_docling[:300]!r}")
    print(f"\nVIEJO:   {texto_viejo[:300]!r}")

    # Calcular páginas con la nueva paginación por caracteres (5000 chars/página)
    def dividir_por_caracteres(texto, max_caracteres=5000):
        """Réplica de dividir_en_paginas de app.py basada en caracteres."""
        if not texto:
            return ['']
        parrafos = [p.strip() for p in re.split(r'\n\s*\n', texto) if p.strip()]
        paginas = []
        pagina_actual = []
        caracteres_actuales = 0
        for parrafo in parrafos:
            longitud_parrafo = len(parrafo) + 2
            if longitud_parrafo > max_caracteres:
                if pagina_actual:
                    paginas.append('\n\n'.join(pagina_actual))
                    pagina_actual = []
                    caracteres_actuales = 0
                trozos = [parrafo[i:i+max_caracteres] for i in range(0, len(parrafo), max_caracteres)]
                for trozo in trozos:
                    paginas.append(trozo)
                continue
            if caracteres_actuales + longitud_parrafo > max_caracteres and pagina_actual:
                paginas.append('\n\n'.join(pagina_actual))
                pagina_actual = []
                caracteres_actuales = 0
            pagina_actual.append(parrafo)
            caracteres_actuales += longitud_parrafo
        if pagina_actual:
            paginas.append('\n\n'.join(pagina_actual))
        if not paginas:
            paginas = ['']
        return paginas

    paginas_docling_nuevas = len(dividir_por_caracteres(texto_docling))
    paginas_viejo_nuevas = len(dividir_por_caracteres(texto_viejo))

    print("\n" + "=" * 80)
    print("PAGINACIÓN NUEVA (por caracteres, 5000 chars/página)")
    print("=" * 80)
    print(f"  Docling: {paginas_docling_nuevas} páginas")
    print(f"  Viejo:   {paginas_viejo_nuevas} páginas")
    print(f"  Diferencia: {abs(paginas_docling_nuevas - paginas_viejo_nuevas)} páginas")

except Exception as e:
    print(f"❌ Error: {e}")
    print("\nSugerencias:")
    if "Authentication failed" in str(e):
        print("- Verifica que el usuario y la contraseña sean correctos.")
        print("- Prueba añadiendo '?authSource=admin' al final de la URI si el usuario está en la base 'admin'.")
    elif "connection closed" in str(e) or "Timeout" in str(e):
        print("- Verifica que el host sea correcto y que MongoDB esté escuchando en ese puerto.")