"""
Teccam PDF - API de Integración RAG (FastAPI)
=============================================
Servicio desacoplado ejecutado en el puerto 5022 (por defecto) que expone
metadatos y contenido Markdown de la biblioteca de documentos para la
ingesta y sincronización con un sistema RAG local.

Documentación interactiva disponible en /docs (Swagger UI).
"""

from fastapi import FastAPI, HTTPException, Security, Query, Depends, status
from fastapi.security import APIKeyHeader, HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from datetime import datetime, timezone
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from bson import ObjectId
from dotenv import load_dotenv
import uvicorn
import os
import re
import math
from typing import Optional, List

from metadata_doc import VIGENCIA_DEFECTO

# Cargar variables de entorno desde .env
load_dotenv()

# Configuración del servicio
MONGO_USER = os.getenv('MONGO_USER', '')
MONGO_PASS = os.getenv('MONGO_PASS', '')
MONGO_HOST = os.getenv('MONGO_HOST', 'localhost')
RAG_HTTP_HOST = os.getenv('RAG_HTTP_HOST', '0.0.0.0')
RAG_HTTP_PORT = int(os.getenv('RAG_HTTP_PORT', 5022))
RAG_USER = os.getenv('RAG_USER', 'rag')
RAG_API_KEY = os.getenv('RAG_API_KEY', '').strip()

# Inicialización de la aplicación FastAPI
app = FastAPI(
    title="Teccam PDF - API RAG",
    description="API RESTful desacoplada para la sincronización de documentos con el sistema RAG de IA local.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Permitir CORS para consultas locales.
# La autenticación viaja por cabecera (X-API-Key / Bearer), no por cookies, por lo que
# allow_credentials=False es lo correcto: con allow_origins=["*"] + allow_credentials=True,
# Starlette refleja cualquier Origin y la combinación es inválida según el estándar CORS.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuración de seguridad por API Key opcional
apiKeyHeader = APIKeyHeader(name="X-API-Key", auto_error=False)
httpBearer = HTTPBearer(auto_error=False)

async def verificar_api_key(
    api_key_header: Optional[str] = Security(apiKeyHeader),
    bearer_token: Optional[HTTPAuthorizationCredentials] = Security(httpBearer)
):
    """
    Verifica la API Key solo si RAG_API_KEY está configurada en .env.
    Soporta encabezados 'X-API-Key: <token>' y 'Authorization: Bearer <token>'.
    """
    if not RAG_API_KEY:
        return True  # Si no se configuró clave en .env, la API es abierta

    token_recibido = None
    if api_key_header:
        token_recibido = api_key_header.strip()
    elif bearer_token and bearer_token.credentials:
        token_recibido = bearer_token.credentials.strip()

    if not token_recibido or token_recibido != RAG_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Key inválida o no proporcionada. Acceso denegado al servicio RAG.",
            headers={"WWW-Authenticate": "Bearer"}
        )
    return True

# Conexión MongoDB
MONGO_URI = f"mongodb://{MONGO_USER}:{MONGO_PASS}@{MONGO_HOST}"
mongo_client = MongoClient(
    MONGO_URI,
    serverSelectionTimeoutMS=5000,
    connectTimeoutMS=5000,
    socketTimeoutMS=60000,
    connect=False
)
db = mongo_client.teccam_pdf
collection = db.documentos


# Modelos Pydantic para la respuesta OpenAPI
class DocumentoMetadata(BaseModel):
    id: str = Field(..., description="ID único del documento en MongoDB")
    titulo: str = Field(..., description="Título del documento")
    autor: str = Field(..., description="Autor del documento")
    tema: str = Field(..., description="Tema o dominio de conocimiento (metadata key)")
    fecha_creacion: datetime = Field(..., description="Fecha de creación/extracción en UTC")
    caracteres: int = Field(..., description="Cantidad total de caracteres")
    palabras: int = Field(..., description="Cantidad estimada de palabras")
    es_publico: bool = Field(..., description="Indica si el documento es público")
    compartido_con_rag: bool = Field(..., description="Indica si fue compartido explícitamente con el usuario RAG")
    vigencia: str = Field(VIGENCIA_DEFECTO, description="Estado de vigencia del documento")
    fecha_publicacion: Optional[str] = Field(None, description="Fecha de publicación en formato ISO 8601 (YYYY-MM-DD)")

class DocumentoDetalle(DocumentoMetadata):
    url: Optional[str] = Field(None, description="URL de origen o referencia del archivo")
    texto: str = Field(..., description="Contenido completo del documento en formato Markdown")

class PaginatedDocumentosResponse(BaseModel):
    total: int = Field(..., description="Total de documentos que coinciden con el filtro")
    pagina: int = Field(..., description="Página actual")
    total_paginas: int = Field(..., description="Total de páginas disponibles")
    limite: int = Field(..., description="Cantidad de resultados por página")
    documentos: List[DocumentoMetadata] = Field(..., description="Lista de metadatos de documentos")

class TemaSummary(BaseModel):
    tema: str = Field(..., description="Nombre del tema / dominio de conocimiento")
    total_documentos: int = Field(..., description="Cantidad de documentos asociados a este tema")

class TemasResponse(BaseModel):
    total_temas: int = Field(..., description="Cantidad total de temas únicos")
    temas: List[TemaSummary] = Field(..., description="Listado de temas con su conteo")

class HealthCheckResponse(BaseModel):
    status: str = "ok"
    servidor: str = "Teccam PDF - RAG API"
    puerto: int = RAG_HTTP_PORT
    usuario_rag: str = RAG_USER
    autenticacion_requerida: bool = bool(RAG_API_KEY)
    base_datos_conectada: bool


def construir_query_rag(tema: Optional[str] = None, desde: Optional[datetime] = None, vigencia: Optional[str] = None):
    """
    Construye la consulta MongoDB para recuperar únicamente los documentos
    públicos, pertenecientes a RAG_USER o explícitamente compartidos con RAG_USER.
    """
    filtros = [
        {'usuario': {'$exists': False}},
        {'usuario': RAG_USER},
        {'usuarios_compartidos': RAG_USER}
    ]
    query = {'$or': filtros}

    if tema:
        query['tema'] = {'$regex': tema, '$options': 'i'}

    if desde:
        query['fecha_creacion'] = {'$gte': desde}

    if vigencia:
        query['vigencia'] = vigencia

    return query


@app.get("/", response_model=HealthCheckResponse, summary="Verificar estado del servicio RAG")
def health_check():
    """Retorna el estado de salud del servicio RAG y de la conexión a MongoDB."""
    db_ok = False
    try:
        mongo_client.admin.command('ping')
        db_ok = True
    except Exception as e:
        db_ok = False

    return HealthCheckResponse(
        status="ok" if db_ok else "error_db",
        base_datos_conectada=db_ok
    )


@app.get(
    "/api/v1/rag/documentos",
    response_model=PaginatedDocumentosResponse,
    summary="Obtener índice de documentos para RAG",
    dependencies=[Depends(verificar_api_key)]
)
def listar_documentos_rag(
    tema: Optional[str] = Query(None, description="Filtrar por tema o dominio de conocimiento"),
    desde: Optional[datetime] = Query(None, description="Filtrar documentos creados desde una fecha/hora específica (ISO 8601 UTC)"),
    vigencia: Optional[str] = Query(None, description="Filtrar por estado de vigencia (vigente, derogado, parcialmente-vigente, en-proyecto, NA (no aplica))"),
    pagina: int = Query(1, ge=1, description="Número de página"),
    limite: int = Query(50, ge=1, le=1000, description="Cantidad de documentos por página (máx. 1000)")
):
    """
    Devuelve un índice con los **metadatos** de todos los documentos accesibles
    por el usuario RAG (públicos o compartidos).
    
    Ideal para comparar contra la base vectorial y sincronizar cambios nuevos o incrementales.
    """
    try:
        query = construir_query_rag(tema=tema, desde=desde, vigencia=vigencia)
        total = collection.count_documents(query)

        skip = (pagina - 1) * limite
        cursor = collection.find(
            query,
            {
                'titulo': 1, 'autor': 1, 'tema': 1, 'usuario': 1,
                'usuarios_compartidos': 1, 'fecha_creacion': 1, 'texto': 1,
                'vigencia': 1, 'fecha_publicacion': 1
            }
        ).sort('fecha_creacion', -1).skip(skip).limit(limite)

        documentos_meta = []
        for doc in cursor:
            texto = doc.get('texto', '')
            doc_user = doc.get('usuario')
            doc_shared = doc.get('usuarios_compartidos') or []
            if not isinstance(doc_shared, list):
                doc_shared = [str(doc_shared)]

            # Formatear fecha
            fecha = doc.get('fecha_creacion')
            if not fecha:
                fecha = datetime.now(timezone.utc)
            elif fecha.tzinfo is None:
                fecha = fecha.replace(tzinfo=timezone.utc)

            documentos_meta.append(DocumentoMetadata(
                id=str(doc['_id']),
                titulo=doc.get('titulo', ''),
                autor=doc.get('autor', ''),
                tema=doc.get('tema', ''),
                fecha_creacion=fecha,
                caracteres=len(texto),
                palabras=len(re.findall(r'\b\w+\b', texto)),
                es_publico=doc_user is None,
                compartido_con_rag=(doc_user is not None and doc_user != RAG_USER and RAG_USER in doc_shared),
                vigencia=doc.get('vigencia') or VIGENCIA_DEFECTO,
                fecha_publicacion=doc.get('fecha_publicacion') or None
            ))

        total_paginas = max(1, math.ceil(total / limite))

        return PaginatedDocumentosResponse(
            total=total,
            pagina=pagina,
            total_paginas=total_paginas,
            limite=limite,
            documentos=documentos_meta
        )
    except PyMongoError as e:
        raise HTTPException(status_code=500, detail=f"Error de base de datos: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")


@app.get(
    "/api/v1/rag/documentos/{documento_id}",
    response_model=DocumentoDetalle,
    summary="Obtener un documento completo por ID para ingesta/chunking",
    dependencies=[Depends(verificar_api_key)]
)
def obtener_documento_rag(documento_id: str):
    """
    Devuelve el contenido **completo en Markdown** (`texto`) y metadatos del documento especificado.
    """
    if not ObjectId.is_valid(documento_id):
        raise HTTPException(status_code=400, detail="Formato de ID de documento inválido")

    try:
        doc = collection.find_one({'_id': ObjectId(documento_id)})
        if not doc:
            raise HTTPException(status_code=404, detail="Documento no encontrado")

        doc_user = doc.get('usuario')
        doc_shared = doc.get('usuarios_compartidos') or []
        if not isinstance(doc_shared, list):
            doc_shared = [str(doc_shared)]

        # Verificar permisos de acceso para RAG
        tiene_acceso = (doc_user is None) or (doc_user == RAG_USER) or (RAG_USER in doc_shared)
        if not tiene_acceso:
            raise HTTPException(status_code=403, detail="El documento especificado no está accesible para el usuario RAG")

        texto = doc.get('texto', '')
        fecha = doc.get('fecha_creacion')
        if not fecha:
            fecha = datetime.now(timezone.utc)
        elif fecha.tzinfo is None:
            fecha = fecha.replace(tzinfo=timezone.utc)

        return DocumentoDetalle(
            id=str(doc['_id']),
            titulo=doc.get('titulo', ''),
            autor=doc.get('autor', ''),
            tema=doc.get('tema', ''),
            fecha_creacion=fecha,
            caracteres=len(texto),
            palabras=len(re.findall(r'\b\w+\b', texto)),
            es_publico=doc_user is None,
            compartido_con_rag=(doc_user is not None and doc_user != RAG_USER and RAG_USER in doc_shared),
            vigencia=doc.get('vigencia') or VIGENCIA_DEFECTO,
            fecha_publicacion=doc.get('fecha_publicacion') or None,
            url=doc.get('url'),
            texto=texto
        )
    except HTTPException:
        raise
    except PyMongoError as e:
        raise HTTPException(status_code=500, detail=f"Error de base de datos: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")


@app.get(
    "/api/v1/rag/temas",
    response_model=TemasResponse,
    summary="Listar temas/dominios de conocimiento y su número de documentos",
    dependencies=[Depends(verificar_api_key)]
)
def listar_temas_rag():
    """
    Retorna la lista de todos los **temas/dominios** únicos disponibles en la base de datos
    accesibles por el RAG, junto con la cantidad de libros existentes por tema.
    """
    try:
        match_stage = construir_query_rag()
        pipeline = [
            {'$match': match_stage},
            {'$group': {'_id': '$tema', 'total': {'$sum': 1}}},
            {'$sort': {'total': -1}}
        ]

        resultados = list(collection.aggregate(pipeline))
        temas_summary = [
            TemaSummary(
                tema=item['_id'] if item['_id'] else 'Sin Tema',
                total_documentos=item['total']
            )
            for item in resultados
        ]

        return TemasResponse(
            total_temas=len(temas_summary),
            temas=temas_summary
        )
    except PyMongoError as e:
        raise HTTPException(status_code=500, detail=f"Error de base de datos: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")


if __name__ == "__main__":
    if not RAG_API_KEY and RAG_HTTP_HOST not in ("127.0.0.1", "localhost", "::1"):
        print(
            "ADVERTENCIA DE SEGURIDAD: RAG_API_KEY no está configurada y el servicio "
            f"escucha en {RAG_HTTP_HOST}:{RAG_HTTP_PORT}. La API queda abierta a la red "
            "sin autenticación. Defina RAG_API_KEY en .env o restrinja RAG_HTTP_HOST a "
            "127.0.0.1 si solo la consume IA local del mismo equipo."
        )
    print(f"Iniciando Teccam PDF RAG API en http://{RAG_HTTP_HOST}:{RAG_HTTP_PORT}")
    print(f"Documentación OpenAPI en http://localhost:{RAG_HTTP_PORT}/docs")
    uvicorn.run(app, host=RAG_HTTP_HOST, port=RAG_HTTP_PORT)
