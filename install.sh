#!/bin/bash

# Obtener el directorio actual y el usuario actual
INSTALL_DIR="$(pwd)"
CURRENT_USER="$(whoami)"

echo "Instalando teccam_pdf en $INSTALL_DIR para el usuario $CURRENT_USER"

# Verificar que estamos en el directorio correcto
if [ ! -f "$INSTALL_DIR/app.py" ]; then
    echo "Error: No se encuentra app.py. Ejecute este script desde el directorio del proyecto."
    exit 1
fi

# Crear o actualizar el entorno virtual
echo "Configurando entorno virtual..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

# Instalar dependencias
echo "Instalando dependencias..."
./venv/bin/pip install -r requirements.txt

# Crear el archivo de servicio systemd para el usuario
echo "Configurando servicio systemd..."
SERVICE_FILE="$HOME/.config/systemd/user/teccam_pdf.service"

# Crear directorio si no existe
mkdir -p "$HOME/.config/systemd/user"

# Crear archivo de servicio
cat > "$SERVICE_FILE" << EOL
[Unit]
Description=Teccam PDF Service
After=network.target

[Service]
Type=simple
Environment="PATH=$INSTALL_DIR/venv/bin:/usr/local/bin:/usr/bin:/bin"
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/python app.py
Restart=always
RestartSec=3

[Install]
WantedBy=default.target
EOL

# Recargar servicios de systemd del usuario
systemctl --user daemon-reload

# Habilitar el servicio para que se inicie con el sistema
systemctl --user enable teccam_pdf.service

# Iniciar el servicio
echo "Iniciando el servicio..."
systemctl --user start teccam_pdf.service

# Verificar el estado del servicio
echo "Verificando el estado del servicio..."
systemctl --user status teccam_pdf.service

# Mostrar instrucciones finales
echo "
Instalación completada!

Para administrar el servicio, use los siguientes comandos:
  - Ver estado:    systemctl --user status teccam_pdf.service
  - Iniciar:       systemctl --user start teccam_pdf.service
  - Detener:       systemctl --user stop teccam_pdf.service
  - Reiniciar:     systemctl --user restart teccam_pdf.service
  - Ver logs:      journalctl --user -u teccam_pdf.service -f

El servicio está configurado para iniciarse automáticamente cuando inicies sesión.
Para permitir que el servicio se ejecute sin sesión activa, ejecute:
  sudo loginctl enable-linger $CURRENT_USER

La aplicación está disponible en:
  http://localhost:5018 (o el puerto configurado en .env)
"

# Preguntar si desea habilitar linger
read -p "¿Desea permitir que el servicio se ejecute sin sesión activa? (s/N) " -n 1 -r
echo
if [[ $REPLY =~ ^[Ss]$ ]]; then
    echo "Habilitando linger para $CURRENT_USER..."
    sudo loginctl enable-linger "$CURRENT_USER"
fi
