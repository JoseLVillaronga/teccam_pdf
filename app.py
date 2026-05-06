from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
import os
import datetime
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from extractor_html import extraer_texto_html_markdown
from extractor_pdf import extraer_texto_pdf_markdown, extraer_texto_pdf_archivo
from urllib.parse import urlparse
from bson import ObjectId
import markdown2
import hashlib
import json
import math

# Cargar variables de entorno
load_dotenv()

# Obtener lista de editores desde variables de entorno
EDITORES = os.getenv('EDITORES', '').split(',')

# Configuración
RESULTADOS_POR_PAGINA = int(os.getenv('RESULTADOS_POR_PAGINA', 20))
LINEAS_POR_PAGINA = int(os.getenv('LINEAS_POR_PAGINA', 50))
CACHE_TTL = int(os.getenv('CACHE_TTL', 300))  # 5 minutos por defecto

def es_editor(usuario):
    """Verifica si un usuario está en la lista de editores."""
    return usuario in EDITORES

app = Flask(__name__)

# Configuración de MongoDB con timeouts para evitar que se cuelgue
MONGO_URI = f"mongodb://{os.getenv('MONGO_USER')}:{os.getenv('MONGO_PASS')}@{os.getenv('MONGO_HOST')}"
client = MongoClient(
    MONGO_URI,
    serverSelectionTimeoutMS=5000,  # Timeout de 5 segundos para seleccionar servidor
    connectTimeoutMS=5000,          # Timeout de conexión
    socketTimeoutMS=30000,          # Timeout de socket para operaciones largas
    maxPoolSize=10                  # Limitar conexiones en pool
)
db = client.teccam_pdf
collection = db.documentos
posiciones_collection = db.posiciones_lectura

# Crear índices para acelerar búsquedas
def asegurar_indices():
    try:
        collection.create_index([('titulo', 'text'), ('autor', 'text'), ('tema', 'text')])
        collection.create_index([('usuario', 1)])
        collection.create_index([('fecha_creacion', -1)])
        posiciones_collection.create_index([
            ('documento_id', 1), ('usuario', 1)
        ], unique=True)
        print("Índices creados/verificados correctamente")
    except Exception as e:
        print(f"Error al crear índices: {e}")

# Ejecutar al inicio
asegurar_indices()

# Caché simple en memoria
cache_memoria = {}
cache_tiempos = {}

def obtener_cache(key):
    """Obtiene un valor del caché si no ha expirado."""
    if key in cache_memoria and key in cache_tiempos:
        if (datetime.datetime.utcnow() - cache_tiempos[key]).total_seconds() < CACHE_TTL:
            return cache_memoria[key]
        else:
            # Limpiar caché expirado
            del cache_memoria[key]
            del cache_tiempos[key]
    return None

def guardar_cache(key, value):
    """Guarda un valor en el caché."""
    cache_memoria[key] = value
    cache_tiempos[key] = datetime.datetime.utcnow()

def limpiar_cache():
    """Limpia el caché completamente."""
    cache_memoria.clear()
    cache_tiempos.clear()

def es_pdf(url):
    """Determina si una URL corresponde a un archivo PDF."""
    return urlparse(url).path.lower().endswith('.pdf')

def dividir_en_paginas(texto_markdown, lineas_por_pagina=LINEAS_POR_PAGINA):
    """
    Divide el texto markdown en páginas de aproximadamente N líneas cada una.
    Respeta los saltos de párrafo para no cortar en medio de un párrafo.
    """
    lineas = texto_markdown.split('\n')
    paginas = []
    pagina_actual = []
    contador_lineas = 0
    
    for linea in lineas:
        pagina_actual.append(linea)
        contador_lineas += 1
        
        # Si llegamos al límite y la línea está vacía (fin de párrafo), cerramos página
        if contador_lineas >= lineas_por_pagina and linea.strip() == '':
            paginas.append('\n'.join(pagina_actual))
            pagina_actual = []
            contador_lineas = 0
    
    # Agregar la última página si quedó contenido
    if pagina_actual:
        paginas.append('\n'.join(pagina_actual))
    
    # Si no hay páginas (texto vacío), devolver una página vacía
    if not paginas:
        paginas = ['']
    
    return paginas

@app.route('/', methods=['GET'])
def index():
    # Si hay una URL y usuario en los parámetros GET, los pasamos a la plantilla
    url = request.args.get('url', '')
    usuario = request.args.get('usuario', '')
    return render_template('index.html', url=url, usuario=usuario)

@app.route('/leer', methods=['GET'])
def leer():
    """Página para leer documentos guardados."""
    usuario = request.args.get('usuario', '')
    return render_template('leer.html', usuario=usuario)

@app.route('/api/buscar', methods=['GET'])
def buscar_documentos():
    """API para buscar documentos por título, autor o tema con paginación."""
    titulo = request.args.get('titulo', '')
    autor = request.args.get('autor', '')
    tema = request.args.get('tema', '')
    usuario = request.args.get('usuario', '')
    pagina = int(request.args.get('pagina', 1))
    resultados_por_pagina = int(request.args.get('limite', RESULTADOS_POR_PAGINA))
    
    # Validar parámetros
    pagina = max(1, pagina)
    resultados_por_pagina = min(max(1, resultados_por_pagina), 100)
    
    # Construir la consulta
    query = {}
    if titulo:
        query['titulo'] = {'$regex': titulo, '$options': 'i'}
    if autor:
        query['autor'] = {'$regex': autor, '$options': 'i'}
    if tema:
        query['tema'] = {'$regex': tema, '$options': 'i'}
    
    # Si no hay filtros, mostrar los más recientes
    sort_field = 'fecha_creacion'
    sort_direction = -1
    
    # Filtrar documentos según el usuario
    if usuario:
        # Si hay usuario, mostrar documentos públicos o del usuario
        query['$or'] = [
            {'usuario': {'$exists': False}},  # documentos públicos
            {'usuario': usuario}              # documentos del usuario
        ]
    else:
        # Si no hay usuario, mostrar solo documentos públicos
        query['usuario'] = {'$exists': False}
    
    # Generar clave de caché
    cache_key = f"buscar:{hashlib.md5(json.dumps(query, sort_keys=True).encode()).hexdigest()}:{pagina}:{resultados_por_pagina}"
    cache_key_total = f"buscar_total:{hashlib.md5(json.dumps(query, sort_keys=True).encode()).hexdigest()}"
    
    # Intentar obtener del caché
    cached_result = obtener_cache(cache_key)
    cached_total = obtener_cache(cache_key_total)
    
    if cached_result is not None and cached_total is not None:
        documentos = cached_result
        total = cached_total
    else:
        try:
            # Contar total de documentos (para paginación)
            total = collection.count_documents(query)
            
            # Buscar documentos con paginación
            skip = (pagina - 1) * resultados_por_pagina
            documentos = list(collection.find(
                query,
                {'titulo': 1, 'autor': 1, 'tema': 1, 'usuario': 1}
            ).sort(sort_field, sort_direction).skip(skip).limit(resultados_por_pagina))
            
            # Guardar en caché
            guardar_cache(cache_key, documentos)
            guardar_cache(cache_key_total, total)
        except PyMongoError as e:
            return jsonify({'error': 'Error de base de datos', 'mensaje': str(e)}), 500
    
    # Convertir ObjectId a string para serialización JSON
    for doc in documentos:
        doc['_id'] = str(doc['_id'])
    
    # Añadir información de permisos si hay usuario
    if usuario:
        is_editor = es_editor(usuario)
        for doc in documentos:
            doc['can_delete'] = is_editor or (doc.get('usuario') == usuario)
    
    total_paginas = max(1, math.ceil(total / resultados_por_pagina))
    
    return jsonify({
        'documentos': documentos,
        'total': total,
        'pagina': pagina,
        'total_paginas': total_paginas,
        'resultados_por_pagina': resultados_por_pagina
    })

@app.route('/api/documento/<id>', methods=['GET', 'DELETE'])
def obtener_documento(id):
    """API para obtener o eliminar un documento específico por ID."""
    try:
        if request.method == 'DELETE':
            resultado = collection.delete_one({'_id': ObjectId(id)})
            if resultado.deleted_count > 0:
                limpiar_cache()  # Invalidar caché al eliminar
                return jsonify({
                    'status': 'success',
                    'message': 'Documento eliminado exitosamente'
                })
            else:
                return jsonify({'error': 'Documento no encontrado'}), 404
        else:  # GET - ahora devuelve el texto en markdown (sin convertir a HTML)
            # Intentar obtener del caché
            cache_key = f"documento:{id}"
            cached = obtener_cache(cache_key)
            
            if cached:
                return jsonify(cached)
            
            documento = collection.find_one({'_id': ObjectId(id)})
            if documento:
                texto_markdown = documento['texto']
                
                # Dividir el texto en páginas
                paginas_markdown = dividir_en_paginas(texto_markdown)
                total_paginas = len(paginas_markdown)
                
                # Convertir solo la primera página a HTML
                primera_pagina_html = markdown2.markdown(paginas_markdown[0]) if paginas_markdown else ''
                
                resultado = {
                    'titulo': documento['titulo'],
                    'autor': documento['autor'],
                    'tema': documento['tema'],
                    'total_paginas': total_paginas,
                    'contenido_html': primera_pagina_html,
                    'pagina_actual': 1
                }
                
                # Guardar en caché
                guardar_cache(cache_key, resultado)
                
                return jsonify(resultado)
            else:
                return jsonify({'error': 'Documento no encontrado'}), 404
    except PyMongoError as e:
        return jsonify({'error': 'Error de base de datos', 'mensaje': str(e)}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/documento/<id>/pagina/<int:numero_pagina>', methods=['GET'])
def obtener_pagina_documento(id, numero_pagina):
    """API para obtener una página específica de un documento."""
    try:
        # Intentar obtener del caché
        cache_key = f"documento:{id}:pagina:{numero_pagina}"
        cached = obtener_cache(cache_key)
        
        if cached:
            return jsonify(cached)
        
        documento = collection.find_one(
            {'_id': ObjectId(id)},
            {'texto': 1}  # Solo traer el campo texto
        )
        
        if not documento:
            return jsonify({'error': 'Documento no encontrado'}), 404
        
        paginas_markdown = dividir_en_paginas(documento['texto'])
        total_paginas = len(paginas_markdown)
        
        # Validar número de página
        if numero_pagina < 1 or numero_pagina > total_paginas:
            return jsonify({'error': 'Número de página inválido'}), 400
        
        # Convertir solo la página solicitada a HTML
        pagina_html = markdown2.markdown(paginas_markdown[numero_pagina - 1])
        
        resultado = {
            'contenido_html': pagina_html,
            'pagina_actual': numero_pagina,
            'total_paginas': total_paginas
        }
        
        # Guardar en caché (con TTL más corto para páginas)
        guardar_cache(cache_key, resultado)
        
        return jsonify(resultado)
    
    except PyMongoError as e:
        return jsonify({'error': 'Error de base de datos', 'mensaje': str(e)}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/posicion/<documento_id>', methods=['GET', 'POST'])
def manejar_posicion(documento_id):
    """API para guardar y obtener la posición de lectura de un documento."""
    usuario = request.args.get('usuario')
    
    # Solo procesar si hay usuario definido
    if not usuario:
        return jsonify({'error': 'Usuario no definido'}), 400
        
    try:
        if request.method == 'POST':
            # Guardar posición - ahora guardamos página en lugar de scrollY
            pagina = request.json.get('pagina')
            scroll_pos = request.json.get('posicion', 0)
            
            if pagina is None:
                return jsonify({'error': 'Página no especificada'}), 400
                
            # Actualizar o insertar posición
            posiciones_collection.update_one(
                {'documento_id': ObjectId(documento_id), 'usuario': usuario},
                {
                    '$set': {
                        'pagina': pagina,
                        'posicion': scroll_pos,
                        'ultima_actualizacion': datetime.datetime.utcnow()
                    }
                },
                upsert=True
            )
            
            return jsonify({
                'status': 'success',
                'message': 'Posición guardada exitosamente'
            })
            
        else:  # GET
            # Obtener última posición
            posicion = posiciones_collection.find_one(
                {'documento_id': ObjectId(documento_id), 'usuario': usuario}
            )
            
            if posicion:
                return jsonify({
                    'pagina': posicion.get('pagina', 1),
                    'posicion': posicion.get('posicion', 0)
                })
            else:
                return jsonify({
                    'pagina': 1,
                    'posicion': 0  # Posición por defecto si no hay guardada
                })
                
    except PyMongoError as e:
        return jsonify({'error': 'Error de base de datos', 'mensaje': str(e)}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/procesar', methods=['POST'])
def procesar():
    try:
        titulo = request.form['titulo']
        autor = request.form['autor']
        tema = request.form['tema']
        usuario = request.form.get('usuario', '')
        es_publico = request.form.get('es_publico') == 'true'

        # Verificar si se subió un archivo o se ingresó una URL
        archivo = request.files.get('archivo_pdf')
        url = request.form.get('url', '')

        if archivo and archivo.filename and archivo.filename.lower().endswith('.pdf'):
            # Procesar archivo PDF subido
            archivo_bytes = archivo.read()
            nombre_archivo = archivo.filename
            resultado = extraer_texto_pdf_archivo(archivo_bytes, nombre_archivo)
            url_origen = f"archivo_local:{nombre_archivo}"
        elif url:
            # Extraer el texto según el tipo de URL
            if es_pdf(url):
                resultado = extraer_texto_pdf_markdown(url)
            else:
                resultado = extraer_texto_html_markdown(url)
            url_origen = url
        else:
            return jsonify({
                'status': 'error',
                'message': 'Debe proporcionar una URL o subir un archivo PDF'
            }), 400

        # Preparar documento para MongoDB
        documento = {
            'url': url_origen,
            'titulo': titulo,
            'autor': autor,
            'tema': tema,
            'texto': resultado['texto'],
            'fecha_creacion': datetime.datetime.utcnow()
        }

        # Solo agregar usuario si no es público y se proporcionó un usuario
        if not es_publico and usuario:
            documento['usuario'] = usuario

        # Guardar en MongoDB
        collection.insert_one(documento)
        
        # Limpiar caché de búsqueda al agregar nuevo documento
        limpiar_cache()

        return jsonify({
            'status': 'success',
            'message': 'Documento procesado y guardado exitosamente'
        })

    except PyMongoError as e:
        return jsonify({
            'status': 'error',
            'message': f'Error de base de datos: {str(e)}'
        }), 500
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

if __name__ == '__main__':
    # Obtener host y puerto desde variables de entorno
    http_host = os.getenv('HTTP_HOST', 'localhost')
    http_port = int(os.getenv('HTTP_PORT', 5000))
    
    app.run(
        host=http_host,
        port=http_port,
        debug=True
    )