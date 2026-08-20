from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
import os
import shutil
from datetime import datetime, timezone

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
import threading
import uuid
import requests
import time
from flask_caching import Cache

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
tareas_collection = db.tareas_traduccion

# Crear índices para acelerar búsquedas
def asegurar_indices():
    try:
        collection.create_index([('titulo', 'text'), ('autor', 'text'), ('tema', 'text')])
        collection.create_index([('usuario', 1)])
        collection.create_index([('usuarios_compartidos', 1)])
        collection.create_index([('fecha_creacion', -1)])
        posiciones_collection.create_index([
            ('documento_id', 1), ('usuario', 1)
        ], unique=True)
        tareas_collection.create_index([('job_id', 1)], unique=True)
        # Índice TTL para limpiar tareas de traducción después de 24 horas (86400 segundos)
        tareas_collection.create_index([('fecha_creacion', 1)], expireAfterSeconds=86400)
        print("Índices creados/verificados correctamente")
    except Exception as e:
        print(f"Error al crear índices: {e}")

# Ejecutar al inicio
asegurar_indices()

# Configuración de caché concurrente en disco (FileSystemCache)
cache_config = {
    "CACHE_TYPE": "FileSystemCache",
    "CACHE_DIR": os.path.join(os.path.abspath(os.path.dirname(__file__)), 'flask_cache'),
    "CACHE_DEFAULT_TIMEOUT": CACHE_TTL
}
cache = Cache(app, config=cache_config)

# Idiomas soportados
IDIOMAS_MAP = {
    'es': 'Español',
    'en': 'Inglés',
    'pt': 'Portugués'
}

def actualizar_tarea_traduccion(job_id, estado, paginas_procesadas=0, total_paginas=0, resultado_id=None, error=None):
    """Actualiza o inserta el estado de una tarea de traducción en MongoDB."""
    try:
        tareas_collection.update_one(
            {'job_id': job_id},
            {
                '$set': {
                    'job_id': job_id,
                    'estado': estado,
                    'paginas_procesadas': paginas_procesadas,
                    'total_paginas': total_paginas,
                    'resultado_id': resultado_id,
                    'error': error,
                    'fecha_actualizacion': datetime.now(timezone.utc)
                },
                '$setOnInsert': {
                    'fecha_creacion': datetime.now(timezone.utc)
                }
            },
            upsert=True
        )
    except Exception as e:
        print(f"Error al actualizar tarea de traducción {job_id}: {e}")

def obtener_tarea_traduccion(job_id):
    """Obtiene el estado de una tarea de traducción desde MongoDB."""
    try:
        tarea = tareas_collection.find_one(
            {'job_id': job_id},
            {'_id': 0, 'fecha_creacion': 0, 'fecha_actualizacion': 0}
        )
        return tarea
    except Exception as e:
        print(f"Error al obtener tarea de traducción {job_id}: {e}")
        return None

def obtener_cache(key):
    """Obtiene un valor del caché si no ha expirado o si existe en disco."""
    return cache.get(key)

def guardar_cache(key, value):
    """Guarda un valor en el caché."""
    cache.set(key, value, timeout=CACHE_TTL)

def limpiar_cache():
    """Limpia el caché completamente."""
    cache.clear()

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
        # Mostrar documentos públicos, propios del usuario o compartidos con él
        query['$or'] = [
            {'usuario': {'$exists': False}},       # documentos públicos
            {'usuario': usuario},                   # documentos del usuario
            {'usuarios_compartidos': usuario}       # documentos compartidos con el usuario
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
                {'titulo': 1, 'autor': 1, 'tema': 1, 'usuario': 1, 'usuarios_compartidos': 1}
            ).sort(sort_field, sort_direction).skip(skip).limit(resultados_por_pagina))
            
            # Convertir ObjectId a string para serialización y almacenamiento en caché
            for doc in documentos:
                doc['_id'] = str(doc['_id'])

            # Guardar en caché
            guardar_cache(cache_key, documentos)
            guardar_cache(cache_key_total, total)
        except Exception as e:
            print(f"Error en buscar_documentos: {e}")
            return jsonify({'error': 'Error de base de datos', 'mensaje': str(e)}), 500

    # Añadir información de permisos y formatear usuarios_compartidos
    is_editor = es_editor(usuario) if usuario else False
    for doc in documentos:
        doc_user = doc.get('usuario')
        doc_shared = doc.get('usuarios_compartidos') or []
        if not isinstance(doc_shared, list):
            doc_shared = [str(doc_shared)]
        if usuario:
            doc['can_delete'] = is_editor or (doc_user == usuario)
            doc['can_edit'] = is_editor or (doc_user == usuario)
            doc['is_shared'] = (doc_user is not None) and (doc_user != usuario) and (usuario in doc_shared)
        doc['usuarios_compartidos'] = ', '.join(doc_shared)
    
    total_paginas = max(1, math.ceil(total / resultados_por_pagina))
    
    return jsonify({
        'documentos': documentos,
        'total': total,
        'pagina': pagina,
        'total_paginas': total_paginas,
        'resultados_por_pagina': resultados_por_pagina
    })

@app.route('/api/documento/<id>', methods=['GET', 'DELETE', 'PUT'])
def obtener_documento(id):
    """API para obtener, eliminar o editar un documento específico por ID."""
    try:
        usuario = request.args.get('usuario', '')
        if not usuario and request.is_json and request.json:
            usuario = request.json.get('usuario', '')

        if request.method == 'DELETE':
            documento = collection.find_one({'_id': ObjectId(id)})
            if not documento:
                return jsonify({'error': 'Documento no encontrado'}), 404
            
            is_editor = es_editor(usuario) if usuario else False
            doc_usuario = documento.get('usuario')
            if not (is_editor or (doc_usuario is not None and doc_usuario == usuario)):
                return jsonify({'error': 'No tiene permisos para eliminar este documento'}), 403

            resultado = collection.delete_one({'_id': ObjectId(id)})
            if resultado.deleted_count > 0:
                limpiar_cache()  # Invalidar caché al eliminar

                # Eliminar carpeta de imágenes asociadas si existe
                doc_dir = os.path.join(app.root_path, 'static', 'documentos', str(id))
                if os.path.exists(doc_dir):
                    try:
                        shutil.rmtree(doc_dir)
                    except Exception as e_del:
                        print(f"Error al eliminar carpeta de imágenes {doc_dir}: {e_del}")

                return jsonify({
                    'status': 'success',
                    'message': 'Documento eliminado exitosamente'
                })
            else:
                return jsonify({'error': 'Documento no encontrado'}), 404

        elif request.method == 'PUT':
            datos = request.json or {}
            documento = collection.find_one({'_id': ObjectId(id)})
            if not documento:
                return jsonify({'error': 'Documento no encontrado'}), 404

            is_editor = es_editor(usuario) if usuario else False
            doc_usuario = documento.get('usuario')
            if not (is_editor or (doc_usuario is not None and doc_usuario == usuario)):
                return jsonify({'error': 'No tiene permisos para editar este documento'}), 403

            nuevo_titulo = datos.get('titulo', '').strip()
            nuevo_autor = datos.get('autor', '').strip()
            nuevo_tema = datos.get('tema', '').strip()
            es_publico = datos.get('es_publico')

            if not nuevo_titulo or not nuevo_autor or not nuevo_tema:
                return jsonify({'error': 'Título, autor y tema son campos obligatorios'}), 400

            # Procesar usuarios compartidos
            raw_compartidos = datos.get('usuarios_compartidos', '')
            if isinstance(raw_compartidos, list):
                lista_compartidos = [str(u).strip() for u in raw_compartidos if str(u).strip()]
            else:
                lista_compartidos = [u.strip() for u in str(raw_compartidos).split(',') if u.strip()]
            lista_compartidos = list(dict.fromkeys(lista_compartidos))

            update_fields = {
                'titulo': nuevo_titulo,
                'autor': nuevo_autor,
                'tema': nuevo_tema
            }
            unset_fields = {}

            if es_publico is True:
                unset_fields['usuario'] = ""
                unset_fields['usuarios_compartidos'] = ""
            elif es_publico is False:
                if doc_usuario:
                    update_fields['usuario'] = doc_usuario
                else:
                    update_fields['usuario'] = usuario

                if lista_compartidos:
                    update_fields['usuarios_compartidos'] = lista_compartidos
                else:
                    unset_fields['usuarios_compartidos'] = ""

            update_op = {'$set': update_fields}
            if unset_fields:
                update_op['$unset'] = unset_fields

            collection.update_one({'_id': ObjectId(id)}, update_op)
            limpiar_cache()

            return jsonify({
                'status': 'success',
                'message': 'Documento actualizado exitosamente'
            })

        else:  # GET - devuelve el texto en markdown y metadatos
            cache_key = f"documento:{id}:{usuario}"
            cached = obtener_cache(cache_key)
            
            if cached:
                return jsonify(cached)
            
            documento = collection.find_one({'_id': ObjectId(id)})
            if documento:
                doc_usuario = documento.get('usuario')
                doc_shared = documento.get('usuarios_compartidos', [])
                is_editor = es_editor(usuario) if usuario else False
                has_access = (doc_usuario is None) or (doc_usuario == usuario) or is_editor or (usuario in doc_shared)
                
                if not has_access:
                    return jsonify({'error': 'No tiene permisos para acceder a este documento'}), 403

                texto_markdown = documento['texto']
                
                # Dividir el texto en páginas
                paginas_markdown = dividir_en_paginas(texto_markdown)
                total_paginas = len(paginas_markdown)
                
                # Convertir solo la primera página a HTML
                primera_pagina_html = markdown2.markdown(paginas_markdown[0], extras=['break-on-newline']) if paginas_markdown else ''
                
                can_edit = is_editor or (doc_usuario is not None and doc_usuario == usuario)
                can_delete = is_editor or (doc_usuario is not None and doc_usuario == usuario)
                is_shared = (doc_usuario is not None) and (doc_usuario != usuario) and (usuario in doc_shared)

                resultado = {
                    'id': str(documento['_id']),
                    'titulo': documento['titulo'],
                    'autor': documento['autor'],
                    'tema': documento['tema'],
                    'usuario': doc_usuario,
                    'es_publico': doc_usuario is None,
                    'usuarios_compartidos': ', '.join(doc_shared),
                    'is_shared': is_shared,
                    'can_edit': can_edit,
                    'can_delete': can_delete,
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
        usuario = request.args.get('usuario', '')
        cache_key = f"documento:{id}:pagina:{numero_pagina}:{usuario}"
        cached = obtener_cache(cache_key)
        
        if cached:
            return jsonify(cached)
        
        documento = collection.find_one(
            {'_id': ObjectId(id)},
            {'texto': 1, 'usuario': 1, 'usuarios_compartidos': 1}
        )
        
        if not documento:
            return jsonify({'error': 'Documento no encontrado'}), 404
        
        doc_usuario = documento.get('usuario')
        doc_shared = documento.get('usuarios_compartidos', [])
        is_editor = es_editor(usuario) if usuario else False
        has_access = (doc_usuario is None) or (doc_usuario == usuario) or is_editor or (usuario in doc_shared)
        
        if not has_access:
            return jsonify({'error': 'No tiene permisos para acceder a este documento'}), 403
        
        paginas_markdown = dividir_en_paginas(documento['texto'])
        total_paginas = len(paginas_markdown)
        
        # Validar número de página
        if numero_pagina < 1 or numero_pagina > total_paginas:
            return jsonify({'error': 'Número de página inválido'}), 400
        
        # Convertir solo la página solicitada a HTML
        # Usamos extras=['break-on-newline'] para preservar saltos de línea simples (\n -> <br>)
        pagina_html = markdown2.markdown(paginas_markdown[numero_pagina - 1], extras=['break-on-newline'])
        
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
                        'ultima_actualizacion': datetime.now(timezone.utc)
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

        # Generar ID previo del documento para asociar imágenes
        doc_id = str(ObjectId())
        doc_dir = os.path.join(app.root_path, 'static', 'documentos', doc_id)
        url_base_imagenes = f"/static/documentos/{doc_id}"

        # Verificar si se subió un archivo o se ingresó una URL
        archivo = request.files.get('archivo_pdf')
        url = request.form.get('url', '')

        if archivo and archivo.filename and archivo.filename.lower().endswith('.pdf'):
            # Procesar archivo PDF subido
            archivo_bytes = archivo.read()
            nombre_archivo = archivo.filename
            resultado = extraer_texto_pdf_archivo(
                archivo_bytes,
                nombre_archivo,
                doc_id=doc_id,
                imagenes_dir=doc_dir,
                url_base_imagenes=url_base_imagenes
            )
            url_origen = f"archivo_local:{nombre_archivo}"
        elif url:
            # Extraer el texto según el tipo de URL
            if es_pdf(url):
                resultado = extraer_texto_pdf_markdown(
                    url,
                    doc_id=doc_id,
                    imagenes_dir=doc_dir,
                    url_base_imagenes=url_base_imagenes
                )
            else:
                resultado = extraer_texto_html_markdown(
                    url,
                    doc_id=doc_id,
                    imagenes_dir=doc_dir,
                    url_base_imagenes=url_base_imagenes
                )
            url_origen = url
        else:
            return jsonify({
                'status': 'error',
                'message': 'Debe proporcionar una URL o subir un archivo PDF'
            }), 400

        # Si el directorio de imágenes se creó pero quedó vacío, lo limpiamos
        if os.path.exists(doc_dir) and not os.listdir(doc_dir):
            try:
                os.rmdir(doc_dir)
            except Exception:
                pass

        # Preparar documento para MongoDB
        documento = {
            '_id': ObjectId(doc_id),
            'url': url_origen,
            'titulo': titulo,
            'autor': autor,
            'tema': tema,
            'texto': resultado['texto'],
            'fecha_creacion': datetime.now(timezone.utc)
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

def ejecutar_traduccion(original_id, idioma_destino, job_id, usuario=None):
    try:
        # 1. Obtener el documento original
        doc = collection.find_one({'_id': ObjectId(original_id)})
        if not doc:
            actualizar_tarea_traduccion(
                job_id,
                estado='error',
                paginas_procesadas=0,
                total_paginas=0,
                resultado_id=None,
                error='Documento original no encontrado'
            )
            return

        api_key = os.getenv('OPENAI_API_KEY')
        base_url = os.getenv('OPENAI_BASE_URL', 'https://api.deepseek.com/v1')
        model = os.getenv('OPENAI_MODEL', 'deepseek-v4-flash')

        if not api_key:
            actualizar_tarea_traduccion(
                job_id,
                estado='error',
                paginas_procesadas=0,
                total_paginas=0,
                resultado_id=None,
                error='API key de DeepSeek (OPENAI_API_KEY) no configurada en .env'
            )
            return

        nombre_idioma = IDIOMAS_MAP.get(idioma_destino, idioma_destino)

        # 2. Traducir metadatos (Título y Tema)
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }

        meta_prompt = (
            f"Traduce el siguiente Título y Tema al {nombre_idioma}. "
            "Responde EXCLUSIVAMENTE en formato JSON con la estructura: "
            '{"titulo": "...", "tema": "..."}. No agregues código markdown, explicaciones ni comentarios.\n\n'
            f"Título: {doc['titulo']}\nTema: {doc['tema']}"
        )

        meta_payload = {
            'model': model,
            'messages': [
                {'role': 'system', 'content': 'Eres un traductor experto que responde únicamente en JSON limpio.'},
                {'role': 'user', 'content': meta_prompt}
            ],
            'temperature': 0.1
        }

        titulo_traducido = f"{doc['titulo']} ({nombre_idioma})"
        tema_traducido = doc['tema']

        try:
            res_meta = requests.post(f"{base_url}/chat/completions", headers=headers, json=meta_payload, timeout=30)
            res_meta.raise_for_status()
            meta_data = res_meta.json()
            content = meta_data['choices'][0]['message']['content'].strip()
            
            # Limpiar bloques markdown si existen
            if content.startswith('```'):
                parts = content.split('```')
                if len(parts) >= 3:
                    content = parts[1]
                    if content.startswith('json'):
                        content = content[4:]
            content = content.strip('` \n')
            
            parsed_meta = json.loads(content)
            titulo_traducido = parsed_meta.get('titulo', titulo_traducido)
            tema_traducido = parsed_meta.get('tema', tema_traducido)
        except Exception as e:
            print(f"Error al traducir metadatos (usando valores por defecto): {e}")

        # 3. Dividir y traducir el texto del documento por páginas
        paginas_originales = dividir_en_paginas(doc['texto'])
        total_paginas = len(paginas_originales)
        
        actualizar_tarea_traduccion(
            job_id,
            estado='procesando',
            paginas_procesadas=0,
            total_paginas=total_paginas,
            resultado_id=None,
            error=None
        )

        paginas_traducidas = []
        
        for idx, pagina in enumerate(paginas_originales):
            if not pagina.strip():
                paginas_traducidas.append('')
                actualizar_tarea_traduccion(
                    job_id,
                    estado='procesando',
                    paginas_procesadas=idx + 1,
                    total_paginas=total_paginas
                )
                continue
                
            prompt_pagina = (
                f"Traduce el siguiente fragmento de texto Markdown al {nombre_idioma}. "
                "Preserva estrictamente la estructura Markdown, enlaces, bloques de código, listas y saltos de línea. "
                "NO agregues aclaraciones, notas, comentarios ni introducciones. Tu respuesta debe ser estrictamente la traducción:\n\n"
                f"{pagina}"
            )
            
            payload_pagina = {
                'model': model,
                'messages': [
                    {'role': 'system', 'content': 'Eres un traductor profesional experto de Markdown. Traduces texto conservando saltos de línea y formato sin añadir notas explicativas.'},
                    {'role': 'user', 'content': prompt_pagina}
                ],
                'temperature': 0.2
            }
            
            exito = False
            error_msg = ""
            for intento in range(3):
                try:
                    res_pag = requests.post(f"{base_url}/chat/completions", headers=headers, json=payload_pagina, timeout=60)
                    res_pag.raise_for_status()
                    res_data = res_pag.json()
                    traducido = res_data['choices'][0]['message']['content']
                    paginas_traducidas.append(traducido)
                    exito = True
                    break
                except Exception as e:
                    error_msg = str(e)
                    time.sleep(2)
            
            if not exito:
                actualizar_tarea_traduccion(
                    job_id,
                    estado='error',
                    paginas_procesadas=idx,
                    total_paginas=total_paginas,
                    resultado_id=None,
                    error=f'Error en la traducción de la página {idx + 1}: {error_msg}'
                )
                return
                
            actualizar_tarea_traduccion(
                job_id,
                estado='procesando',
                paginas_procesadas=idx + 1,
                total_paginas=total_paginas
            )

        # Unir todas las páginas traducidas
        texto_completo_traducido = '\n'.join(paginas_traducidas)

        # 4. Crear el nuevo documento en la DB
        doc_traducido = {
            'url': f"traduccion_de:{doc['_id']}",
            'titulo': f"{titulo_traducido} [Traducido al {nombre_idioma}]",
            'autor': doc['autor'],
            'tema': tema_traducido,
            'texto': texto_completo_traducido,
            'fecha_creacion': datetime.now(timezone.utc)
        }
        
        if 'usuario' in doc:
            doc_traducido['usuario'] = doc['usuario']
            
        resultado = collection.insert_one(doc_traducido)
        nuevo_id = str(resultado.inserted_id)
        
        # Limpiar caché de búsqueda al agregar nuevo documento
        limpiar_cache()
        
        actualizar_tarea_traduccion(
            job_id,
            estado='completado',
            paginas_procesadas=total_paginas,
            total_paginas=total_paginas,
            resultado_id=nuevo_id,
            error=None
        )

    except Exception as e:
        actualizar_tarea_traduccion(
            job_id,
            estado='error',
            paginas_procesadas=0,
            total_paginas=0,
            resultado_id=None,
            error=f'Error general en traducción: {str(e)}'
        )

@app.route('/api/traducir/<id>', methods=['POST'])
def traducir_documento(id):
    """API para iniciar la traducción de un documento."""
    idioma_destino = request.json.get('idioma_destino')
    usuario = request.json.get('usuario')
    
    if not idioma_destino or idioma_destino not in IDIOMAS_MAP:
        return jsonify({'error': 'Idioma de destino inválido'}), 400
        
    try:
        doc = collection.find_one({'_id': ObjectId(id)})
        if not doc:
            return jsonify({'error': 'Documento no encontrado'}), 404
            
        if doc.get('usuario') and doc.get('usuario') != usuario and not es_editor(usuario):
            return jsonify({'error': 'No tiene permisos para acceder a este documento'}), 403
            
        job_id = str(uuid.uuid4())
        
        actualizar_tarea_traduccion(
            job_id,
            estado='procesando',
            paginas_procesadas=0,
            total_paginas=0,
            resultado_id=None,
            error=None
        )
        
        hilo = threading.Thread(
            target=ejecutar_traduccion,
            args=(id, idioma_destino, job_id, usuario)
        )
        hilo.start()
        
        return jsonify({
            'status': 'success',
            'job_id': job_id
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/traducir/estado/<job_id>', methods=['GET'])
def estado_traduccion(job_id):
    """API para consultar el estado de una traducción."""
    tarea = obtener_tarea_traduccion(job_id)
    if not tarea:
        return jsonify({'error': 'Tarea de traducción no encontrada'}), 404
        
    return jsonify(tarea)

if __name__ == '__main__':
    # Obtener host y puerto desde variables de entorno
    http_host = os.getenv('HTTP_HOST', 'localhost')
    http_port = int(os.getenv('HTTP_PORT', 5000))
    
    app.run(
        host=http_host,
        port=http_port,
        debug=True
    )