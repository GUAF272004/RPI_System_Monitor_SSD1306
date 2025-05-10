# -*- coding: UTF-8 -*-
# Script para mostrar información del sistema en una pantalla OLED SSD1306
# en una Raspberry Pi, con navegación y apagado mediante botones.

print("DEBUG: El script info_display.py ha comenzado.") # Mensaje de depuración inicial

# --- Importación de Librerías ---
import time               # Para pausas y control de tiempo
import subprocess         # Para ejecutar comandos del sistema (hostname, iwgetid, shutdown)
import board              # type: ignore # Para la interfaz con el hardware de Adafruit Blinka
import digitalio          # type: ignore # No usado directamente, pero a veces es dependencia de board/blinka
from PIL import Image, ImageDraw, ImageFont # Pillow para manipulación de imágenes y dibujo de texto
import adafruit_ssd1306   # type: ignore # Librería para el controlador de la pantalla OLED SSD1306
import socket             # Para constantes de red como socket.AF_INET

# Configuración de gpiozero y la fábrica de pines pigpio
import gpiozero
from gpiozero.pins.pigpio import PiGPIOFactory # Fábrica de pines que usa el demonio pigpiod

# Establecer pigpio como la fábrica de pines por defecto para gpiozero
# Esto es crucial para un control GPIO robusto y debe hacerse ANTES de crear objetos Button.
try:
    gpiozero.Device.pin_factory = PiGPIOFactory()
    print("INFO: Usando pigpio como fábrica de pines para gpiozero.")
except Exception as e:
    print(f"ERROR CRÍTICO: No se pudo establecer PiGPIOFactory para gpiozero. ¿El demonio pigpiod está corriendo? Error: {e}")
    print("Por favor, verifica que pigpiod esté instalado y corriendo: sudo systemctl start pigpiod")
    exit() # Salir si la fábrica de pines no se puede configurar

import psutil             # Para obtener información del sistema (CPU, RAM, disco, red)
from datetime import datetime # Para obtener y formatear la fecha y hora actual

# --- Configuración de Pantalla SSD1306 (I2C) ---
WIDTH = 128               # Ancho de la pantalla OLED en píxeles
HEIGHT = 64               # Alto de la pantalla OLED en píxeles
BORDER = 5                # Margen pequeño alrededor del contenido en la pantalla

# Inicializar la interfaz I2C y el objeto de la pantalla
try:
    i2c = board.I2C()     # Inicializa el bus I2C por defecto de la Raspberry Pi (SDA GPIO2, SCL GPIO3)
    # Crear el objeto de la pantalla. La dirección I2C puede ser 0x3C o 0x3D.
    display = adafruit_ssd1306.SSD1306_I2C(WIDTH, HEIGHT, i2c, addr=0x3C)
    print("INFO: Pantalla SSD1306 conectada exitosamente.")
except ValueError as e:
    print(f"ERROR CRÍTICO: No se encontró la pantalla SSD1306. Verifica la conexión y la dirección I2C: {e}")
    print("Comprueba con 'i2cdetect -y 1' en la terminal.")
    exit()
except RuntimeError as e: # Errores relacionados con Blinka o la configuración del hardware
    print(f"ERROR CRÍTICO: Error de Runtime al inicializar I2C (¿Problema con Blinka/dependencias?): {e}")
    exit()
except Exception as e: # Captura cualquier otro error durante la inicialización de la pantalla
    print(f"ERROR CRÍTICO: Otro error al inicializar la pantalla: {e}")
    exit()

# Limpiar la pantalla al inicio
display.fill(0) # Rellena la pantalla de negro (0)
display.show()  # Actualiza la pantalla física

# --- Configuración de Fuentes ---
# Intenta cargar fuentes TrueType para una mejor apariencia.
# Si no se encuentran, usa fuentes por defecto más básicas.
try:
    font_big = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)
    font_medium = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
    font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 10)
    print("INFO: Fuentes TrueType cargadas.")
except IOError:
    print("ADVERTENCIA: Fuente TrueType DejaVuSans no encontrada, usando fuente por defecto.")
    print("Considera instalarla con: sudo apt install fonts-dejavu-core")
    font_big = ImageFont.load_default()
    font_medium = ImageFont.load_default()
    font_small = ImageFont.load_default()

# --- Configuración de Botones (Pines GPIO) ---
# Define los pines GPIO que se usarán para los botones.
# Estos números corresponden a la numeración BCM (Broadcom) de los pines.
shutdown_button_pin = 17  # GPIO17 (Pin físico 11) para el botón de apagado
next_screen_button_pin = 27 # GPIO27 (Pin físico 13) para el botón de cambio de pantalla

try:
    # Inicializar los objetos Button de gpiozero.
    # pull_up=True significa que se usa la resistencia pull-up interna de la Pi.
    # El botón debe conectar el pin GPIO a GND cuando se presiona.
    # bounce_time evita múltiples detecciones por un solo pulso (rebote mecánico).
    shutdown_btn = gpiozero.Button(shutdown_button_pin, pull_up=True, bounce_time=0.2)
    next_screen_btn = gpiozero.Button(next_screen_button_pin, pull_up=True, bounce_time=0.2)
    print(f"INFO: Botones configurados en GPIO {shutdown_button_pin} y GPIO {next_screen_button_pin} usando {gpiozero.Device.pin_factory}.")
except gpiozero.exc.BadPinFactory as e: # Error si la fábrica de pines (pigpio) no se pudo usar
    print(f"ERROR CRÍTICO: No se pudo inicializar la librería GPIO (BadPinFactory): {e}")
    print("Asegúrate de que pigpiod esté corriendo si estableciste esa fábrica.")
    exit()
except Exception as e: # Otros errores al configurar los botones
    print(f"ERROR CRÍTICO: Error inesperado al configurar botones GPIO: {e}")
    exit()

# --- Variables de Estado Globales ---
current_screen_index = 0  # Índice de la pantalla que se muestra actualmente
MAX_SCREENS = 5           # Número total de pantallas disponibles
last_interaction_time = time.monotonic() # Para futuras funciones (ej. apagado de pantalla por inactividad)

# --- Funciones para Obtener Información del Sistema ---

def get_network_info():
    """Obtiene el tipo de conexión de red, SSID (para WiFi) y la dirección IPV4."""
    ssid = "N/A"
    ip_address = "N/A"
    connection_type = "Desconectado"
    try:
        active_connection_found = False
        # Obtener todas las IPs asignadas a la máquina
        all_ips_raw = subprocess.check_output(['hostname', '-I'], text=True, timeout=2).strip()
        all_ips = all_ips_raw.split()
        if not all_ips: ip_address = "No IP" # Si no hay IPs
        else:
            # Priorizar IPs que no sean de loopback (127.0.0.1)
            valid_ips = [ip for ip in all_ips if ip != "127.0.0.1"]
            ip_address = valid_ips[0] if valid_ips else all_ips[0] # Tomar la primera IP válida o la primera disponible
        
        interfaces_addrs = psutil.net_if_addrs() # Direcciones de todas las interfaces
        interfaces_stats = psutil.net_if_stats() # Estadísticas de todas las interfaces (ej. si está activa)

        for iface_name, iface_entries in interfaces_addrs.items():
            # Saltar la interfaz de loopback y las interfaces que no estén activas (UP)
            if iface_name == "lo" or not (interfaces_stats[iface_name].isup if hasattr(interfaces_stats[iface_name], 'isup') else False):
                continue
            for entry in iface_entries:
                # Buscar la entrada que coincida con la familia de direcciones IPv4 y la IP obtenida
                if entry.family == socket.AF_INET and entry.address == ip_address:
                    if iface_name.startswith("eth"): # Interfaz Ethernet
                        connection_type = "Ethernet"
                        active_connection_found = True; break
                    elif iface_name.startswith("wlan"): # Interfaz WiFi
                        connection_type = "WiFi"
                        try:
                            # Intentar obtener el SSID usando iwgetid
                            ssid_output = subprocess.check_output(['iwgetid', '-r'], text=True, timeout=2).strip()
                            ssid = ssid_output if ssid_output else "Buscando..."
                        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
                            ssid = "Buscando..." # Si iwgetid falla o no está
                        active_connection_found = True; break
            if active_connection_found: break # Salir si ya encontramos la conexión activa
        
        # Si no se identificó tipo pero hay IP, marcar como "Conectado"
        if not active_connection_found and ip_address not in ["No IP", "N/A"]:
            connection_type = "Conectado"
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"ADVERTENCIA: Error en subproceso obteniendo info de red: {e}"); ip_address = "Error IP"
    except AttributeError as e_attr: # Específico para el error de psutil.AF_INET si ocurriera
        print(f"ADVERTENCIA: AttributeError obteniendo info de red (puede ser psutil): {e_attr}"); ip_address = "Error Attr."
    except Exception as e: # Cualquier otro error
        print(f"ADVERTENCIA: Error general obteniendo info de red: {e}"); ip_address = "Error Gen."
    return connection_type, ssid, ip_address

def get_storage_info():
    """Obtiene el espacio libre y el porcentaje usado del almacenamiento principal (raíz '/')."""
    try:
        disk = psutil.disk_usage('/') # Obtener uso del disco para la partición raíz
        free_gb = disk.free / (1024**3) # Convertir bytes a Gigabytes
        percent_used = disk.percent
        return f"{free_gb:.1f}GB Libres", f"Usado: {percent_used:.0f}%"
    except Exception as e:
        print(f"ADVERTENCIA: Error obteniendo info de almacenamiento: {e}")
        return "Error GB", "Error %"

def get_system_stats():
    """Obtiene el uso actual de CPU y RAM."""
    try:
        cpu_usage = psutil.cpu_percent(interval=0.1) # Porcentaje de uso de CPU
        ram = psutil.virtual_memory()                # Información de la memoria virtual (RAM)
        ram_used_mb = ram.used / (1024**2)           # RAM usada en Megabytes
        ram_percent = ram.percent                    # Porcentaje de RAM usada
        return f"CPU: {cpu_usage:.0f}%", f"RAM: {ram_used_mb:.0f}MB ({ram_percent:.0f}%)"
    except Exception as e:
        print(f"ADVERTENCIA: Error obteniendo stats del sistema: {e}")
        return "CPU: Err%", "RAM: ErrMB (Err%)"

def get_cpu_temperature():
    """Obtiene la temperatura actual del CPU de la Raspberry Pi."""
    try:
        # El archivo del sistema que contiene la temperatura en miligrados Celsius
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            temp_milli_c = int(f.read().strip())
        temp_c = temp_milli_c / 1000.0 # Convertir a grados Celsius
        return f"{temp_c:.1f}°C" # Formatear con un decimal
    except FileNotFoundError:
        print("ADVERTENCIA: No se pudo leer la temperatura del CPU (archivo no encontrado).")
        return "N/A"
    except Exception as e:
        print(f"ADVERTENCIA: Error obteniendo temp. CPU: {e}")
        return "Error"

def get_datetime_info():
    """Obtiene la fecha y hora actuales formateadas."""
    try:
        now = datetime.now()
        date_str = now.strftime("%d/%m/%Y") # Formato DD/MM/YYYY
        time_str = now.strftime("%H:%M:%S") # Formato HH:MM:SS
        return date_str, time_str
    except Exception as e:
        print(f"ADVERTENCIA: Error obteniendo fecha/hora: {e}")
        return "Fecha Err", "Hora Err"

# --- Funciones para Dibujar Pantallas ---

def draw_screen_content(draw, screen_index_to_draw):
    """Dibuja el contenido de la pantalla según el índice proporcionado."""
    # Limpiar la imagen (llenar con negro)
    draw.rectangle((0, 0, display.width, display.height), outline=0, fill=0)
    y_offset = BORDER # Posición Y inicial para dibujar, respetando el borde

    # Lógica para cada pantalla
    if screen_index_to_draw == 0: # Pantalla de Red
        conn_type, ssid, ip = get_network_info()
        draw.text((BORDER, y_offset), "Red:", font=font_big, fill=255)
        y_offset += font_big.getbbox("A")[3] + 4 # Espacio después del título
        line1_network = "Tipo: Desconectado"
        if conn_type == "WiFi": line1_network = f"WiFi: {ssid}"
        elif conn_type not in ["Desconectado", "N/A"]: line1_network = f"Tipo: {conn_type}"
        draw.text((BORDER, y_offset), line1_network, font=font_medium, fill=255)
        y_offset += font_medium.getbbox("A")[3] + 2 # Espacio
        draw.text((BORDER, y_offset), f"IP: {ip}", font=font_medium, fill=255)

    elif screen_index_to_draw == 1: # Pantalla de Almacenamiento
        free_space, used_percent = get_storage_info()
        draw.text((BORDER, y_offset), "Almac.:", font=font_big, fill=255)
        y_offset += font_big.getbbox("A")[3] + 4
        draw.text((BORDER, y_offset), free_space, font=font_medium, fill=255)
        y_offset += font_medium.getbbox("A")[3] + 2
        draw.text((BORDER, y_offset), used_percent, font=font_medium, fill=255)

    elif screen_index_to_draw == 2: # Pantalla de RAM y CPU
        cpu, ram = get_system_stats()
        draw.text((BORDER, y_offset), "Sistema:", font=font_big, fill=255)
        y_offset += font_big.getbbox("A")[3] + 4
        draw.text((BORDER, y_offset), cpu, font=font_medium, fill=255)
        y_offset += font_medium.getbbox("A")[3] + 2
        draw.text((BORDER, y_offset), ram, font=font_medium, fill=255)

    elif screen_index_to_draw == 3: # Pantalla de Temperatura CPU
        cpu_temp = get_cpu_temperature()
        draw.text((BORDER, y_offset), "Temp. CPU:", font=font_big, fill=255)
        y_offset += font_big.getbbox("A")[3] + 4
        draw.text((BORDER, y_offset), cpu_temp, font=font_medium, fill=255)
        
    elif screen_index_to_draw == 4: # Pantalla de Fecha y Hora
        date_str, time_str = get_datetime_info()
        draw.text((BORDER, y_offset), "Fecha y Hora:", font=font_big, fill=255)
        y_offset += font_big.getbbox("A")[3] + 4
        draw.text((BORDER, y_offset), date_str, font=font_medium, fill=255)
        y_offset += font_medium.getbbox("A")[3] + 2
        draw.text((BORDER, y_offset), time_str, font=font_medium, fill=255)
    
    # Dibujar indicador de página (ej. "1/5") en la esquina inferior derecha
    page_indicator = f"{screen_index_to_draw + 1}/{MAX_SCREENS}"
    # Usar textbbox para obtener las dimensiones exactas del texto y posicionarlo correctamente
    text_bbox = font_small.getbbox(page_indicator)
    text_width = text_bbox[2] - text_bbox[0]
    text_height = text_bbox[3] - text_bbox[1]
    draw.text((WIDTH - BORDER - text_width, HEIGHT - BORDER - text_height), page_indicator, font=font_small, fill=255)

def update_display():
    """Crea una imagen, dibuja el contenido de la pantalla actual y la muestra."""
    image = Image.new("1", (display.width, display.height)) # Crear imagen en modo blanco y negro ("1")
    draw = ImageDraw.Draw(image)                             # Crear objeto para dibujar en la imagen
    draw_screen_content(draw, current_screen_index)          # Llamar a la función que dibuja el contenido específico
    display.image(image)                                     # Cargar la imagen en el buffer de la pantalla
    display.show()                                           # Actualizar la pantalla física

# --- Funciones de Callback para Botones ---
# Estas funciones se ejecutan cuando se presionan los botones correspondientes.

def handle_shutdown_press():
    """Maneja la presión del botón de apagado: muestra mensaje y apaga la Pi."""
    global last_interaction_time
    last_interaction_time = time.monotonic() # Actualizar tiempo de interacción
    print("INFO: Botón de apagado presionado. Iniciando apagado...")
    
    # Mostrar mensaje "Apagando..." en la pantalla
    image = Image.new("1", (display.width, display.height)); draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, display.width, display.height), outline=0, fill=0) # Limpiar pantalla
    text = "Apagando..."; text_bbox = draw.textbbox((0,0), text, font=font_medium)
    textwidth, textheight = text_bbox[2] - text_bbox[0], text_bbox[3] - text_bbox[1]
    draw.text(((WIDTH - textwidth) / 2, (HEIGHT - textheight) / 2), text, font=font_medium, fill=255) # Centrar texto
    display.image(image); display.show()
    
    time.sleep(3) # Mostrar el mensaje por 3 segundos
    
    display.fill(0); display.show() # Limpiar pantalla antes de apagar
    print("INFO: Ejecutando comando de apagado.")
    try:
        # Ejecutar el comando de apagado del sistema.
        # Requiere configuración de sudoers para NOPASSWD si el script no corre como root.
        subprocess.run(['sudo', '/sbin/shutdown', '-h', 'now'], check=True)
    except subprocess.CalledProcessError as e:
        print(f"ERROR: Al ejecutar shutdown: {e}")
    except FileNotFoundError: # Si 'sudo' o 'shutdown' no se encuentran
        print("ERROR CRÍTICO: Comando 'sudo' o '/sbin/shutdown' no encontrado.")

def change_screen_press():
    """Maneja la presión del botón de cambio de pantalla: cicla al siguiente índice y actualiza."""
    global current_screen_index, last_interaction_time
    last_interaction_time = time.monotonic() # Actualizar tiempo de interacción
    current_screen_index = (current_screen_index + 1) % MAX_SCREENS # Ciclar al siguiente índice
    print(f"INFO: Cambiando a pantalla: {current_screen_index + 1}")
    update_display() # Redibujar la pantalla con el nuevo contenido

# Asignar las funciones de callback a los eventos de presión de los botones
shutdown_btn.when_pressed = handle_shutdown_press
next_screen_btn.when_pressed = change_screen_press

# --- Bucle Principal ---
last_data_update_time = 0 # Para controlar la frecuencia de actualización de datos
# Intervalos de actualización para diferentes tipos de pantallas (en segundos)
dynamic_update_interval = 1   # Para pantallas con datos que cambian rápidamente (CPU, RAM, Temp, Hora)
network_update_interval = 10  # Para la pantalla de red (no necesita actualizarse tan a menudo)
storage_update_interval = 30  # Para la pantalla de almacenamiento

update_display() # Mostrar la primera pantalla al iniciar el script
last_interaction_time = time.monotonic() # Inicializar tiempo de interacción

print(f"INFO: Sistema de visualización iniciado. {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("INFO: Presiona Ctrl+C para salir (si se ejecuta manualmente).")
print("INFO: Recuerda que el demonio pigpiod debe estar corriendo (sudo systemctl start pigpiod).")
print("INFO: Para el apagado con botón, configura 'sudoers' si este script no corre como root.")

try:
    while True: # Bucle infinito para mantener el script corriendo
        current_time_monotonic = time.monotonic()
        refresh_needed = False # Bandera para determinar si se necesita redibujar la pantalla

        # Lógica para decidir si se refresca la pantalla actual basada en el intervalo
        if current_screen_index == 0: # Pantalla de Red
            if current_time_monotonic - last_data_update_time > network_update_interval:
                refresh_needed = True
        elif current_screen_index == 1: # Pantalla de Almacenamiento
            if current_time_monotonic - last_data_update_time > storage_update_interval:
                refresh_needed = True
        elif current_screen_index in [2, 3, 4]: # Pantallas dinámicas: Sistema, Temp. CPU, Fecha/Hora
            if current_time_monotonic - last_data_update_time > dynamic_update_interval:
                refresh_needed = True
        
        if refresh_needed:
            update_display() # Redibujar si es necesario
            last_data_update_time = current_time_monotonic # Actualizar el tiempo del último refresco de datos
        
        time.sleep(0.1) # Pequeña pausa para reducir el uso de CPU del script
except KeyboardInterrupt: # Manejar salida con Ctrl+C
    print("\nINFO: Salida solicitada por el usuario (Ctrl+C).")
except Exception as e: # Capturar cualquier otro error inesperado en el bucle principal
    print(f"ERROR INESPERADO EN BUCLE PRINCIPAL: {e}")
finally:
    # Bloque de limpieza: se ejecuta siempre al salir del script (normal o por error)
    print("INFO: Limpiando recursos...")
    if 'display' in locals() and display: # Asegurarse de que 'display' existe
        display.fill(0)
        display.show()
        print("INFO: Pantalla limpiada.")
    if 'shutdown_btn' in locals() and shutdown_btn: # Asegurarse de que los botones existen
        shutdown_btn.close()
    if 'next_screen_btn' in locals() and next_screen_btn:
        next_screen_btn.close()
    print("INFO: Recursos GPIO (botones) liberados.")
    print("INFO: Script finalizado.")
