# Teccam PDF - Extractor y Lector de Documentos

## Descripción
Teccam PDF es una aplicación web que permite extraer y almacenar texto de documentos PDF y páginas web, convirtiéndolos a formato Markdown para una mejor legibilidad. La aplicación proporciona una interfaz web para la extracción y lectura de documentos.

## Estado del Sistema
- **Fecha de Implementación**: 14 de Febrero de 2025
- **Versión**: 1.0.0
- **Estado**: Producción

## Novedades recientes (Agosto 2026)
- **API RAG desacoplada en FastAPI (Puerto 5022)**: Se implementó un microservicio independiente en FastAPI para la ingesta y sincronización de documentos con sistemas RAG (*Retrieval-Augmented Generation*) de IA local. Expone una interfaz Swagger OpenAPI en `/docs` y endpoints optimizados para consultar el índice de libros accesibles por el usuario `rag` (documentos públicos o compartidos), filtrar por temas/dominios, realizar sincronizaciones incrementales por fecha (`desde`) y descargar contenido en Markdown. Incluye autenticación opcional vía `RAG_API_KEY`.
- **Motor de extracción con Docling remoto**: Se agregó un nuevo motor de extracción de documentos basado en `docling-serve`, que permite convertir PDF (y páginas web) a Markdown con OCR y reconstrucción de estructura de página, siendo mucho más preciso que la extracción simple con PyMuPDF, especialmente en documentos escaneados o con tablas complejas.
  - *Motivo*: Mejorar la calidad de extracción en documentos escaneados, tablas complejas y OCR.
  - *Configuración*: `DOCLING_IP` y `DOCLING_PORT` en `.env` (por defecto `192.168.1.47:5020`).
  - *Uso*: En `/procesar`, seleccionar `motor=docling` para activar este motor. Soporta conversión síncrona y asíncrona (con polling de estado para archivos grandes).
- **Extracción y visualización de imágenes**: Se agregó la extracción automática de imágenes incrustadas en documentos PDF (vía PyMuPDF) y la descarga de imágenes en páginas web. Los archivos se guardan organizados en `static/documentos/<doc_id>/` y se referencian en el texto Markdown con estilos adaptados al modo oscuro. Al eliminar un documento, se limpia automáticamente su carpeta de imágenes del disco.
  - *Motivo*: Permitir la visualización completa de documentos técnicos, manuales y artículos que dependen de figuras, diagramas y capturas para su comprensión.
- **Integración de imágenes en Docling**: Cuando se usa el motor Docling, las imágenes del PDF se extraen complementariamente con PyMuPDF y se reemplazan los placeholders `<!-- image -->` (que Docling inserta en el Markdown) por referencias reales a las imágenes guardadas localmente. Si hay imágenes extra sin placeholder, se agregan al final del Markdown.
  - *Motivo*: Docling coloca placeholders de imágenes pero no guarda las imágenes reales; este paso complementario completa la visualización.
- **Recomposición de palabras partidas con guión (`-`) en PDFs**: Se corrigió el algoritmo de limpieza de texto para detectar cuando una palabra se corta al final de la línea física del PDF, extrayendo la sílaba inicial de la línea siguiente y fusionándola a la palabra original (ej: `investiga-` + `ción` $\rightarrow$ `investigación`).
  - *Motivo*: Evitar que las palabras quedaran truncadas en dos líneas separadas sin el guión visual en el lector web.
- **Persistencia de tareas de traducción en MongoDB con TTL**: El estado de las traducciones asíncronas con DeepSeek se migró desde un diccionario en memoria RAM a la colección `tareas_traduccion` en MongoDB, con un índice de expiración automática (TTL) de 24 horas (`expireAfterSeconds=86400`).
  - *Motivo*: Garantizar consistencia total en entornos de producción multi-proceso (como Gunicorn/uWSGI), donde diferentes *workers* atienden las consultas de estado de traducción.
- **Renderizado seguro en el Lector (Fix de comillas y caracteres especiales)**: Se reescribió la función de renderizado de la lista de documentos en JavaScript (`leer.html`) para utilizar creación programática del DOM (`document.createElement` y eventos nativos) en lugar de interpolación de cadenas en atributos `onclick`.
  - *Motivo*: Evitar errores de sintaxis (`Uncaught SyntaxError`) y bloqueos en la interfaz cuando los títulos o autores contienen comillas simples (`'`), dobles (`"`) o apóstrofes.
- **Modernización y limpieza de código**: Se eliminaron las llamadas dinámicas a `pip install` en tiempo de ejecución en los extractores y se sustituyó `datetime.utcnow()` (obsoleto en Python 3.12+) por `datetime.now(timezone.utc)`.

## Novedades anteriores (Julio 2026)
- **Compartir Documentos Privados**: se permite compartir documentos privados con uno o varios usuarios específicos (separados por coma). Los usuarios receptores pueden buscar y leer el documento compartido (con badge "Compartido").
- **Edición de Documentos (Metadatos y Visibilidad)**: los usuarios creadores y los editores declarados en `EDITORES` pueden modificar el Título, Autor, Tema, usuarios compartidos y conmutar la visibilidad entre Público y Privado directamente desde la interfaz.
- **Optimización de rendimiento**: paginación del contenido de documentos en páginas más pequeñas (~50 líneas cada una), con carga bajo demanda. Solo se convierte a HTML la página que se está visualizando, no el documento completo.
- **Caché en disco (Persistente y Concurrente)**: integración de `Flask-Caching` con almacenamiento temporal en disco (FileSystemCache) durante 5 minutos. Permite un funcionamiento óptimo y consistente en entornos concurrentes y de producción multi-proceso (como Gunicorn/uWSGI).
- **Índices MongoDB**: se crearon índices en `titulo`, `autor`, `tema`, `usuario` y `fecha_creacion` para acelerar las búsquedas.
- **Timeouts de conexión**: configurado timeout de 5 segundos para conexiones a MongoDB, evitando que la aplicación se cuelgue si la base de datos no responde.
- **Paginación de resultados de búsqueda**: los resultados se muestran de a 20 documentos por página, con navegación entre páginas.
- **Navegación por teclado**: mientras se lee un documento, se pueden usar las teclas de flecha izquierda (anterior) y derecha (siguiente) para cambiar de página.
- **Barra de navegación de páginas**: nueva interfaz con botones para primera/anterior/siguiente/última página, e input numérico para ir a una página específica.
- **Indicadores de carga**: se agregaron spinners mientras se cargan las páginas del documento.
- **Scroll automático**: al cambiar de página, el scroll vuelve al inicio automáticamente.
- **Seguridad (Sanitización XSS)**: integración de `DOMPurify` en el lector para limpiar y sanitizar el HTML de los documentos extraídos antes de renderizarse en pantalla, neutralizando código malicioso.
- **Traducción de libros con DeepSeek**: integración de la API de DeepSeek (`deepseek-v4-flash`) para traducir títulos, temas y textos de libros ya cargados a Español, Inglés o Portugués, preservando la estructura Markdown y el formato original de forma asíncrona (con barra de progreso).

## Novedades anteriores (Abril 2025)
- Navegación mejorada: ahora la página principal (`/`) y el lector (`/leer`) tienen botones visibles para ir de una a otra, manteniendo el usuario si está definido.
- La página principal soporta modo oscuro o claro automático, adaptándose a la configuración del sistema operativo/navegador.

## Características
- Extracción de texto e imágenes de archivos PDF
- Extracción de texto e imágenes de páginas web

- Conversión automática a formato Markdown
- Traducción inteligente de documentos (Español/Inglés/Portugués) usando la API de DeepSeek
- Almacenamiento en MongoDB
- Interfaz de búsqueda y lectura
- Diseño responsive
- Modo oscuro para lectura confortable
- Sistema de documentos públicos/privados
- Marcadores de posición de lectura
- Integración con sistemas de autenticación externos

## Requisitos del Sistema
- Python 3.12 o superior
- MongoDB
- Systemd (para la instalación como servicio)
- Acceso a Internet (para descargar documentos)

## Configuración

### Variables de Entorno (.env)
Crear un archivo `.env` basado en `.env.example` con la siguiente configuración:

```bash
MONGO_USER=user
MONGO_PASS=password
MONGO_HOST=host
HTTP_HOST=localhost
HTTP_PORT=5018
EDITORES=editor1,editor2,editor3

# API de Inteligencia Artificial (Traductor DeepSeek)
OPENAI_API_KEY=tu_api_key_aqui
OPENAI_MODEL=deepseek-v4-flash
OPENAI_BASE_URL=https://api.deepseek.com/v1

# Servidor Docling (motor de extracción avanzado)
DOCLING_IP=192.168.1.47
DOCLING_PORT=5020

# Servidor RAG (FastAPI en puerto desacoplado 5022)
RAG_HTTP_HOST=0.0.0.0
RAG_HTTP_PORT=5022
RAG_USER=rag
RAG_API_KEY=tu_clave_api_rag_aqui
```


Descripción de las variables:
- `MONGO_USER`: Usuario de MongoDB
- `MONGO_PASS`: Contraseña de MongoDB
- `MONGO_HOST`: Host de MongoDB
- `HTTP_HOST`: Host para el servidor web (localhost para desarrollo)
- `HTTP_PORT`: Puerto para el servidor web
- `EDITORES`: Lista de usuarios con permisos de edición, separados por comas
- `OPENAI_API_KEY`: API Key para acceder a la API de DeepSeek
- `OPENAI_MODEL`: Identificador del modelo (por ejemplo, `deepseek-v4-flash`)
- `OPENAI_BASE_URL`: URL base de la API compatible con OpenAI para el modelo DeepSeek
- `DOCLING_IP`: IP del servidor Docling (por defecto `192.168.1.47`)
- `DOCLING_PORT`: Puerto del servidor Docling (por defecto `5020`)
- `RAG_HTTP_HOST`: Host de escucha para la API RAG (por defecto `0.0.0.0`)
- `RAG_HTTP_PORT`: Puerto de escucha para la API RAG (por defecto `5022`)
- `RAG_USER`: Nombre del usuario asignado para la lectura de documentos RAG (por defecto `rag`)
- `RAG_API_KEY`: Clave secreta opcional para proteger las consultas de la API RAG


## Sistema de Permisos

### Tipos de Documentos
- **Documentos Públicos**: Visibles para todos los usuarios.
- **Documentos Privados**: Visibles únicamente para su propietario/creador.
- **Documentos Compartidos**: Documentos privados que el propietario ha compartido explícitamente con usuarios específicos (separados por comas), quienes tienen acceso de lectura (identificados con el badge "Compartido").

### Roles de Usuario
1. **Usuario Normal**
   - Puede ver todos los documentos públicos.
   - Puede ver sus documentos privados y los documentos compartidos directamente con él.
   - Puede borrar, editar y compartir solo sus propios documentos privados (modificando título, autor, tema, visibilidad público/privado y usuarios compartidos).
   - Identificación visual de documentos mediante badges: "Público", "Propio" o "Compartido".

2. **Usuario Editor**
   - Todos los permisos de usuario normal.
   - Puede borrar, editar y gestionar la compartición de cualquier documento (público o privado).
   - Definido en la variable de entorno `EDITORES`.

### Gestión de Permisos
- La interfaz muestra badges indicando si un documento es "Público" o "Propio"
- Los botones de borrado y edición solo aparecen cuando el usuario tiene permisos
- La verificación de permisos se realiza tanto en frontend como en backend
- Los editores se definen en el archivo `.env` mediante la variable `EDITORES`

### Ejemplo de Configuración de Editores
```bash
# En .env
EDITORES=jlvillaronga,lsaravia,vcampolongo
```

## Instalación

### Instalación Automática (Recomendada)

1. Clonar el repositorio:
```bash
git clone <repositorio>
cd teccam_pdf
```

2. Ejecutar el instalador:
```bash
./install.sh
```

El instalador:
- Crea un entorno virtual
- Instala las dependencias
- Configura el servicio systemd
- Inicia la aplicación

### Instalación Manual

1. Clonar el repositorio:
```bash
git clone <repositorio>
cd teccam_pdf
```

2. Crear y activar el entorno virtual:
```bash
python -m venv venv
source ./venv/bin/activate
```

3. Instalar dependencias:
```bash
pip install -r requirements.txt
```

4. Configurar variables de entorno:
```bash
cp .env.example .env
# Editar .env con tus configuraciones
```

5. Ejecutar la aplicación:
```bash
python app.py
```

## Uso

### Extracción de Documentos
1. Acceder a `http://localhost:5018` (opcionalmente con `?usuario=nombre_usuario`)
2. Ingresar la URL del documento (PDF o página web)
3. Completar metadatos (título, autor, tema)
4. Si hay usuario definido, elegir si el documento será público
5. Procesar el documento
6. Puedes ir al lector de documentos con el botón "Ir a Lector" (mantiene usuario si aplica).

También se puede pre-cargar una URL:
```
http://localhost:5018/?url=https://ejemplo.com/documento.pdf&usuario=nombre_usuario
```

### Lectura de Documentos
1. Acceder a `http://localhost:5018/leer` (opcionalmente con `?usuario=nombre_usuario`)
2. Usar los filtros de búsqueda (título, autor, tema). Los resultados se muestran paginados (20 por página).
3. Seleccionar un documento para leer
4. El contenido se muestra en formato legible con fondo oscuro, dividido en páginas
5. Navegación entre páginas:
   - Botones: primera, anterior, siguiente, última página
   - Input numérico para ir a una página específica
   - Teclas de flecha izquierda (anterior) y derecha (siguiente)
6. Puedes volver a la página principal con el botón "Volver al Inicio" (mantiene usuario si aplica).
7. Con usuario definido o rol de Editor:
   - Ver documentos públicos y propios privados
   - Editar título, autor, tema y cambiar visibilidad Público/Privado (si es creador o editor)
   - Doble click en el texto para guardar posición de lectura
   - Ctrl+S para guardar posición de lectura
   - Al reabrir, se restaura automáticamente la última posición

## Estructura del Proyecto
```
teccam_pdf/
├── app.py                 # Aplicación principal Flask (Puerto 5018)
├── rag_api.py             # Servicio RAG desacoplado en FastAPI (Puerto 5022)
├── extractor_html.py      # Extractor de páginas web
├── extractor_pdf.py       # Extractor de PDFs
├── extractor_docling.py   # Extractor de documentos con Docling remoto
├── requirements.txt       # Dependencias
├── install.sh            # Script de instalación
├── .env                  # Configuración local
├── .env.example          # Ejemplo de configuración
└── templates/
    ├── index.html        # Página de extracción
    └── leer.html         # Página de lectura
```


## Administración del Servicio

### Comandos Systemd
```bash
# Ver estado del servicio web principal
systemctl --user status teccam_pdf.service

# Ver estado del servicio RAG
systemctl --user status teccam_rag.service

# Iniciar servicios
systemctl --user start teccam_pdf.service
systemctl --user start teccam_rag.service

# Detener servicios
systemctl --user stop teccam_pdf.service
systemctl --user stop teccam_rag.service

# Reiniciar servicios
systemctl --user restart teccam_pdf.service
systemctl --user restart teccam_rag.service

# Ver logs en tiempo real
journalctl --user -u teccam_pdf.service -f
journalctl --user -u teccam_rag.service -f
```

## API RAG para Sistemas de IA Local (Puerto 5022)

La aplicación incluye un microservicio totalmente independiente construido en **FastAPI** que corre por defecto en el puerto `5022`. Este servicio expone automáticamente la documentación Swagger de OpenAPI en `http://localhost:5022/docs`.

### Mecanismo de Visibilidad RAG
El usuario configurado en `RAG_USER` (por defecto `rag`) solo tiene acceso a:
1. Documentos **Públicos** (donde no hay propietario asignado).
2. Documentos **Compartidos** explícitamente con el usuario `rag`.

### Ejemplos de uso con `curl`

Define tu clave API en la sesión (o utiliza la configurada en `.env`):
```bash
API_KEY="tu_clave_api_rag_aqui"
```

#### 1. Verificar Estado del Servicio (Health Check)
```bash
curl -s http://localhost:5022/ | jq .
```

#### 2. Obtener Índice de Documentos (Metadatos RAG)
```bash
curl -s -H "X-API-Key: $API_KEY" \
  "http://localhost:5022/api/v1/rag/documentos?limite=10" | jq .
```

#### 3. Filtrar Documentos por Tema / Dominio
```bash
curl -s -H "X-API-Key: $API_KEY" \
  "http://localhost:5022/api/v1/rag/documentos?tema=Estrategia" | jq .
```

#### 4. Sincronización Incremental (Fecha `desde` en UTC)
```bash
curl -s -H "X-API-Key: $API_KEY" \
  "http://localhost:5022/api/v1/rag/documentos?desde=2026-08-01T00:00:00Z" | jq .
```

#### 5. Consultar Temas y Conteo de Documentos
```bash
curl -s -H "X-API-Key: $API_KEY" \
  "http://localhost:5022/api/v1/rag/temas" | jq .
```

#### 6. Obtener Contenido Completo en Markdown por ID
```bash
curl -s -H "X-API-Key: $API_KEY" \
  "http://localhost:5022/api/v1/rag/documentos/ID_DEL_DOCUMENTO" | jq .
```


## Componentes y Dependencias

### Principales Dependencias
- Flask: Framework web
- Flask-Caching: Gestión de caché concurrente y persistente
- PyMuPDF: Procesamiento de PDFs
- BeautifulSoup4: Procesamiento de HTML
- MongoDB: Almacenamiento de documentos
- Markdown2: Conversión a HTML para visualización

### APIs y Endpoints
- `/`: Página principal de extracción
- `/leer`: Interfaz de lectura
- `/api/buscar`: API de búsqueda de documentos (con paginación: `pagina` y `limite`)
- `/api/documento/<id>`: API para obtener documento (GET), eliminarlo (DELETE) o editar sus metadatos/visibilidad (PUT)
- `/api/documento/<id>/pagina/<n>`: API para obtener una página específica del documento (GET)
- `/procesar`: Endpoint de procesamiento de documentos (POST)
- `/api/posicion/<documento_id>`: API para gestionar posiciones de lectura (GET/POST)
- `/api/traducir/<id>`: API para iniciar el job de traducción asíncrona de un libro (POST)
- `/api/traducir/estado/<job_id>`: API para consultar el estado y avance de la traducción (GET)

## Decisiones Técnicas

### Almacenamiento
- Se eligió MongoDB por su flexibilidad con documentos de longitud variable
- Los documentos se almacenan en formato Markdown para preservar la estructura

### Interfaz de Usuario
- Diseño responsive usando Bootstrap 5
- Modo oscuro o claro automático en la página principal, según configuración del sistema operativo
- Navegación directa entre la página principal y el lector mediante botones visibles
- Procesamiento asíncrono para mejor experiencia de usuario
- Notificaciones toast para feedback de acciones
- Control de posición de lectura mediante doble click o Ctrl+S
- Navegación por teclado con flechas izquierda/derecha en el lector
- Paginación de contenido para carga eficiente de documentos grandes
- Indicadores de carga (spinners) durante la obtención de páginas
- Scroll automático al inicio al cambiar de página

### Seguridad
- Servicio ejecutado a nivel usuario (no root)
- Variables sensibles en archivo .env
- Validación de entradas de usuario

## Estructura de Datos

### Colecciones MongoDB
- **documentos**: Almacena los documentos procesados
  - Campos estándar: título, autor, tema, texto, fecha_creación
  - Campo opcional 'usuario' para documentos privados

- **posiciones_lectura**: Almacena marcadores de posición
  - documento_id: Referencia al documento
  - usuario: Propietario del marcador
  - posicion: Valor del scroll
  - ultima_actualizacion: Timestamp

- **tareas_traduccion**: Almacena el estado y avance de las traducciones asíncronas
  - job_id: Identificador único del trabajo de traducción (UUID)
  - estado: Estado actual (`procesando`, `completado`, `error`)
  - paginas_procesadas: Cantidad de páginas traducidas
  - total_paginas: Total de páginas del documento
  - resultado_id: ID del nuevo documento traducido en MongoDB
  - error: Mensaje de error en caso de fallo
  - fecha_creacion: Timestamp con índice TTL de 24 horas (`expireAfterSeconds=86400`)

## Integración con Sistemas Externos

### Sistema de Usuarios
La aplicación está diseñada para integrarse con sistemas de autenticación externos:
- Acepta parámetro `usuario` vía GET en todas las rutas
- No requiere login propio
- Gestiona documentos públicos y privados
- Mantiene marcadores de lectura por usuario

### Ejemplos de Integración
```
# Acceso como usuario específico
http://localhost:5018/?usuario=nombre_usuario
http://localhost:5018/leer?usuario=nombre_usuario

# Acceso público (sin usuario)
http://localhost:5018/
http://localhost:5018/leer
```

## Mantenimiento

### Logs
Los logs del servicio se pueden consultar con:
```bash
journalctl --user -u teccam_pdf.service -f
```

### Respaldos
Se recomienda respaldar regularmente la base de datos MongoDB:
```bash
mongodump --db teccam_pdf
```

## Próximos Pasos y Mejoras Potenciales
1. **Caché distribuida (Redis)**: Migrar el almacenamiento de `Flask-Caching` de disco a un clúster de Redis si la aplicación escala a múltiples servidores independientes.
2. Agregar soporte para más formatos de documento (DOCX, EPUB, etc.)
3. Implementar búsqueda de texto completo (full-text search en MongoDB)
4. Agregar exportación de documentos (PDF, TXT, EPUB)
5. Implementar sistema de etiquetas / categorías
6. Carga progresiva de imágenes dentro de los documentos
7. Modo de lectura continua (sin paginación, con scroll infinito)

## Soporte
Para reportar problemas o sugerir mejoras, por favor crear un issue en el repositorio.

## Licencia
Este proyecto está bajo la licencia MIT.
