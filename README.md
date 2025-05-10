# Raspberry Pi OLED System Monitor

Este proyecto utiliza una Raspberry Pi para mostrar diversa información del sistema en una pantalla OLED SSD1306 (128x64). La navegación entre pantallas y la función de apagado seguro de la Pi se controlan mediante dos botones.

## Características

* **Pantalla de Red:** Muestra el tipo de conexión (WiFi/Ethernet), SSID (si es WiFi) y la dirección IPv4 actual.
* **Pantalla de Almacenamiento:** Muestra el espacio libre en disco y el porcentaje de uso del almacenamiento principal.
* **Pantalla de Sistema:** Muestra el porcentaje de uso actual de la CPU y el uso de la RAM (MB usados y porcentaje).
* **Pantalla de Temperatura del CPU:** Muestra la temperatura actual del procesador de la Raspberry Pi.
* **Pantalla de Fecha y Hora:** Muestra la fecha y hora actuales del sistema.
* **Navegación por Botón:** Un botón dedicado para ciclar entre las diferentes pantallas de información.
* **Apagado por Botón:** Un botón dedicado para iniciar un apagado seguro de la Raspberry Pi.

## Hardware Requerido

* Raspberry Pi (probado en Raspberry Pi 4 Model B, adaptable a otros modelos).
* Pantalla OLED SSD1306 (interfaz I2C, resolución 128x64).
* 2 x Botones Pulsadores Momentáneos.
* Cables Jumper (macho-hembra y/o macho-macho).
* (Opcional) Protoboard (placa de pruebas) para facilitar las conexiones.

## Configuración de Software

1.  **Sistema Operativo:** Raspberry Pi OS (o una distribución Linux compatible).
2.  **Python 3:** Asegúrate de que esté instalado.
3.  **Entorno Virtual (Recomendado):**
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    ```
4.  **Librerías de Python:** Instala las dependencias desde el archivo `requirements.txt` (ver más abajo) o manualmente:
    ```bash
    # Con el entorno virtual activado:
    pip install adafruit-circuitpython-ssd1306 Pillow gpiozero psutil adafruit-blinka pigpio
    ```
5.  **Demonio `pigpiod`:** Esta librería usa `pigpio` para el control de GPIO. Necesitas instalar y habilitar el demonio `pigpiod`:
    ```bash
    sudo apt update
    sudo apt install pigpio -y
    sudo systemctl start pigpiod
    sudo systemctl enable pigpiod 
    ```
    Verifica su estado con `sudo systemctl status pigpiod`.
6.  **Interfaz I2C:** Habilita la interfaz I2C en tu Raspberry Pi:
    ```bash
    sudo raspi-config
    ```
    Navega a `Interface Options` -> `I2C` -> y selecciona `Yes`. Reinicia si se te solicita.
7.  **(Opcional) Permiso de Apagado sin Contraseña:** Para que el botón de apagado funcione cuando el script se ejecuta como usuario normal (recomendado para el inicio automático), configura `sudoers` para permitir a tu usuario ejecutar `/sbin/shutdown` sin contraseña:
    * Ejecuta `sudo visudo`.
    * Añade la siguiente línea al final del archivo (reemplaza `tu_usuario` con tu nombre de usuario real):
        ```
        tu_usuario ALL=(ALL) NOPASSWD: /sbin/shutdown
        ```
    * Guarda y cierra el archivo con cuidado.

## Conexiones (Pines GPIO - Numeración BCM)

* **Pantalla OLED SSD1306 (I2C):**
    * `VCC` -> Pin 3.3V de la Pi (ej. Pin Físico 1)
    * `GND` -> Pin GND de la Pi (ej. Pin Físico 6)
    * `SDA` -> Pin GPIO 2 (SDA) de la Pi (Pin Físico 3)
    * `SCL` -> Pin GPIO 3 (SCL) de la Pi (Pin Físico 5)

* **Botón de Apagado:**
    * Un terminal -> Pin GPIO 17 de la Pi (Pin Físico 11)
    * Otro terminal -> Pin GND de la Pi
    * *(Nota: El script usa la resistencia pull-up interna del GPIO17)*

* **Botón de Cambio de Pantalla:**
    * Un terminal -> Pin GPIO 27 de la Pi (Pin Físico 13)
    * Otro terminal -> Pin GND de la Pi
    * *(Nota: El script usa la resistencia pull-up interna del GPIO27)*

## Ejecución del Script

1.  Navega al directorio del proyecto.
2.  Activa el entorno virtual (si estás usando uno):
    ```bash
    source .venv/bin/activate
    ```
3.  Ejecuta el script:
    ```bash
    python info_display.py
    ```

## Inicio Automático al Arrancar (Usando `systemd`)

1.  Crea un archivo de servicio, por ejemplo, `/etc/systemd/system/info_display.service`:
    ```bash
    sudo nano /etc/systemd/system/info_display.service
    ```
2.  Pega el siguiente contenido (ajusta `User`, `WorkingDirectory` y `ExecStart` a tu configuración):

    ```ini
    [Unit]
    Description=Servicio de Pantalla de Información SSD1306 para Raspberry Pi
    After=network.target pigpiod.service
    Requires=pigpiod.service

    [Service]
    Type=simple
    User=tu_usuario # Reemplaza con tu nombre de usuario
    WorkingDirectory=/home/tu_usuario/System_Monitor_SSD1306 # Ruta a tu proyecto
    ExecStart=/home/tu_usuario/System_Monitor_SSD1306/.venv/bin/python /home/tu_usuario/System_Monitor_SSD1306/info_display.py # Ruta al Python del venv y al script
    
    Restart=on-failure
    RestartSec=5
    
    StandardOutput=journal
    StandardError=journal
    SyslogIdentifier=info-display

    [Install]
    WantedBy=multi-user.target
    ```
3.  Guarda el archivo y establece los permisos correctos:
    ```bash
    sudo chmod 644 /etc/systemd/system/info_display.service
    ```
4.  Recarga `systemd`, habilita e inicia el servicio:
    ```bash
    sudo systemctl daemon-reload
    sudo systemctl enable info_display.service
    sudo systemctl start info_display.service
    ```
5.  Para ver los logs del servicio:
    ```bash
    journalctl -u info_display.service -f
    ```
