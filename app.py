from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
import os
import datetime
from pymongo import MongoClient
from extractor_html import extraer_texto_html_markdown
from extractor_pdf import extraer_texto_pdf_markdown
from urllib.parse import urlparse
from bson import ObjectId
import markdown2

# Cargar variables de entorno
load_dotenv()

app = Flask(__name__)

# Configuración de MongoDB
MONGO_URI = f"mongodb://{os.getenv('MONGO_USER')}:{os.getenv('MONGO_PASS')}@{os.getenv('MONGO_HOST')}"
client = MongoClient(MONGO_URI)
db = client.teccam_pdf
collection = db.documentos

def es_pdf(url):
    """Determina si una URL corresponde a un archivo PDF."""
    return urlparse(url).path.lower().endswith('.pdf')

@app.route('/', methods=['GET'])
def index():
    # Si hay una URL en los parámetros GET, la pasamos a la plantilla
    url = request.args.get('url', '')
    return render_template('index.html', url=url)

@app.route('/leer', methods=['GET'])
def leer():
    """Página para leer documentos guardados."""
    return render_template('leer.html')

@app.route('/api/buscar', methods=['GET'])
def buscar_documentos():
    """API para buscar documentos por título, autor o tema."""
    titulo = request.args.get('titulo', '')
    autor = request.args.get('autor', '')
    tema = request.args.get('tema', '')
    
    # Construir la consulta
    query = {}
    if titulo:
        query['titulo'] = {'$regex': titulo, '$options': 'i'}
    if autor:
        query['autor'] = {'$regex': autor, '$options': 'i'}
    if tema:
        query['tema'] = {'$regex': tema, '$options': 'i'}
    
    # Buscar documentos
    documentos = list(collection.find(
        query,
        {'titulo': 1, 'autor': 1, 'tema': 1}
    ))
    
    # Convertir ObjectId a string para serialización JSON
    for doc in documentos:
        doc['_id'] = str(doc['_id'])
    
    return jsonify(documentos)

@app.route('/api/documento/<id>', methods=['GET', 'DELETE'])
def obtener_documento(id):
    """API para obtener o eliminar un documento específico por ID."""
    try:
        if request.method == 'DELETE':
            resultado = collection.delete_one({'_id': ObjectId(id)})
            if resultado.deleted_count > 0:
                return jsonify({
                    'status': 'success',
                    'message': 'Documento eliminado exitosamente'
                })
            else:
                return jsonify({'error': 'Documento no encontrado'}), 404
        else:  # GET
            documento = collection.find_one({'_id': ObjectId(id)})
            if documento:
                # Convertir el Markdown a HTML
                html_content = markdown2.markdown(documento['texto'])
                return jsonify({
                    'contenido_html': html_content,
                    'titulo': documento['titulo'],
                    'autor': documento['autor'],
                    'tema': documento['tema']
                })
            else:
                return jsonify({'error': 'Documento no encontrado'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/procesar', methods=['POST'])
def procesar():
    try:
        url = request.form['url']
        titulo = request.form['titulo']
        autor = request.form['autor']
        tema = request.form['tema']

        # Extraer el texto según el tipo de URL
        if es_pdf(url):
            resultado = extraer_texto_pdf_markdown(url)
        else:
            resultado = extraer_texto_html_markdown(url)

        # Preparar documento para MongoDB
        documento = {
            'url': url,
            'titulo': titulo,
            'autor': autor,
            'tema': tema,
            'texto': resultado['texto'],
            'fecha_creacion': datetime.datetime.utcnow()
        }

        # Guardar en MongoDB
        collection.insert_one(documento)

        return jsonify({
            'status': 'success',
            'message': 'Documento procesado y guardado exitosamente'
        })

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
