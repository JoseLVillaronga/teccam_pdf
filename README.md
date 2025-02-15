# Teccam PDF - Extractor y Lector de Documentos

## Descripción
Teccam PDF es una aplicación web que permite extraer y almacenar texto de documentos PDF y páginas web, convirtiéndolos a formato Markdown para una mejor legibilidad. La aplicación proporciona una interfaz web para la extracción y lectura de documentos.

## Estado del Sistema
- **Fecha de Implementación**: 14 de Febrero de 2025
- **Versión**: 1.0.0
- **Estado**: Producción

## Características
- Extracción de texto de archivos PDF
- Extracción de texto de páginas web
- Conversión automática a formato Markdown
- Almacenamiento en MongoDB
- Interfaz de búsqueda y lectura
- Diseño responsive
- Modo oscuro para lectura confortable

## Requisitos del Sistema
- Python 3.12 o superior
- MongoDB
- Systemd (para la instalación como servicio)
- Acceso a Internet (para descargar documentos)

## Configuración

### Variables de Entorno (.env)
```bash
MONGO_USER=usuario
MONGO_PASS=contraseña
MONGO_HOST=host
HTTP_HOST=0.0.0.0
HTTP_PORT=5018
```

## Instalación

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

## Uso

### Extracción de Documentos
1. Acceder a `http://localhost:5018`
2. Ingresar la URL del documento (PDF o página web)
3. Completar metadatos (título, autor, tema)
4. Procesar el documento

También se puede pre-cargar una URL:
```
http://localhost:5018/?url=https://ejemplo.com/documento.pdf
```

### Lectura de Documentos
1. Acceder a `http://localhost:5018/leer`
2. Usar los filtros de búsqueda (título, autor, tema)
3. Seleccionar un documento para leer
4. El contenido se muestra en formato legible con fondo oscuro

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

## Decisiones Técnicas

### Almacenamiento
- Se eligió MongoDB por su flexibilidad con documentos de longitud variable
- Los documentos se almacenan en formato Markdown para preservar la estructura

### Interfaz de Usuario
- Diseño responsive usando Bootstrap 5
- Modo oscuro para lectura prolongada
- Procesamiento asíncrono para mejor experiencia de usuario

### Seguridad
- Servicio ejecutado a nivel usuario (no root)
- Variables sensibles en archivo .env
- Validación de entradas de usuario

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
