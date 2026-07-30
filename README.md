# Teccam PDF - Extractor y Lector de Documentos

## Descripción
Teccam PDF es una aplicación web que permite extraer y almacenar texto de documentos PDF y páginas web, convirtiéndolos a formato Markdown para una mejor legibilidad. La aplicación proporciona una interfaz web para la extracción y lectura de documentos.

## Estado del Sistema
- **Fecha de Implementación**: 14 de Febrero de 2025
- **Versión**: 1.0.0
- **Estado**: Producción

## Novedades recientes (Julio 2026)
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
- Extracción de texto de archivos PDF
- Extracción de texto de páginas web
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
├── app.py                 # Aplicación principal Flask
├── extractor_html.py      # Extractor de páginas web
├── extractor_pdf.py       # Extractor de PDFs
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
# Ver estado
systemctl --user status teccam_pdf.service

# Iniciar servicio
systemctl --user start teccam_pdf.service

# Detener servicio
systemctl --user stop teccam_pdf.service

# Reiniciar servicio
systemctl --user restart teccam_pdf.service

# Ver logs
journalctl --user -u teccam_pdf.service -f
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
