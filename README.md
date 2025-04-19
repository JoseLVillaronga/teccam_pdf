# Teccam PDF - Extractor y Lector de Documentos

## Descripción
Teccam PDF es una aplicación web que permite extraer y almacenar texto de documentos PDF y páginas web, convirtiéndolos a formato Markdown para una mejor legibilidad. La aplicación proporciona una interfaz web para la extracción y lectura de documentos.

## Estado del Sistema
- **Fecha de Implementación**: 14 de Febrero de 2025
- **Versión**: 1.0.0
- **Estado**: Producción

## Novedades recientes (Abril 2025)
- Navegación mejorada: ahora la página principal (`/`) y el lector (`/leer`) tienen botones visibles para ir de una a otra, manteniendo el usuario si está definido.
- La página principal soporta modo oscuro o claro automático, adaptándose a la configuración del sistema operativo/navegador.

## Características
- Extracción de texto de archivos PDF
- Extracción de texto de páginas web
- Conversión automática a formato Markdown
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
```

Descripción de las variables:
- `MONGO_USER`: Usuario de MongoDB
- `MONGO_PASS`: Contraseña de MongoDB
- `MONGO_HOST`: Host de MongoDB
- `HTTP_HOST`: Host para el servidor web (localhost para desarrollo)
- `HTTP_PORT`: Puerto para el servidor web
- `EDITORES`: Lista de usuarios con permisos de edición, separados por comas

## Sistema de Permisos

### Tipos de Documentos
- **Documentos Públicos**: Visibles para todos los usuarios
- **Documentos Privados**: Solo visibles para su propietario

### Roles de Usuario
1. **Usuario Normal**
   - Puede ver todos los documentos públicos
   - Puede ver sus documentos privados
   - Puede borrar solo sus propios documentos
   - Identificación visual de documentos propios vs. públicos

2. **Usuario Editor**
   - Todos los permisos de usuario normal
   - Puede borrar cualquier documento (público o privado)
   - Definido en la variable de entorno `EDITORES`

### Gestión de Permisos
- La interfaz muestra badges indicando si un documento es "Público" o "Propio"
- El botón de borrado solo aparece cuando el usuario tiene permisos
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
2. Usar los filtros de búsqueda (título, autor, tema)
3. Seleccionar un documento para leer
4. El contenido se muestra en formato legible con fondo oscuro
5. Puedes volver a la página principal con el botón "Volver al Inicio" (mantiene usuario si aplica).
6. Con usuario definido:
   - Ver documentos públicos y propios privados
   - Doble click en el texto para guardar posición de lectura
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
- PyMuPDF: Procesamiento de PDFs
- BeautifulSoup4: Procesamiento de HTML
- MongoDB: Almacenamiento de documentos
- Markdown2: Conversión a HTML para visualización

### APIs y Endpoints
- `/`: Página principal de extracción
- `/leer`: Interfaz de lectura
- `/api/buscar`: API de búsqueda de documentos
- `/api/documento/<id>`: API para obtener documento específico
- `/procesar`: Endpoint de procesamiento de documentos
- `/api/posicion/<documento_id>`: API para gestionar posiciones de lectura

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
- Control de posición de lectura mediante doble click

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
1. Implementar cache de documentos frecuentes
2. Agregar soporte para más formatos de documento
3. Implementar búsqueda de texto completo
4. Agregar exportación de documentos
5. Implementar sistema de etiquetas

## Soporte
Para reportar problemas o sugerir mejoras, por favor crear un issue en el repositorio.

## Licencia
Este proyecto está bajo la licencia MIT.
