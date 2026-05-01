import serial
import time

# En la Pi 5 con disable-bt, el puerto suele ser /dev/ttyAMA0
# Si no funciona, intenta con /dev/serial0
puerto = '/dev/serial0'
baudios = 115200

try:
    ser = serial.Serial(
        port=puerto,
        baudrate=baudios,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        bytesize=serial.EIGHTBITS,
        timeout=1
    )
    
    print(f"--- Probando Loopback en {puerto} ---")
    print("Presiona Ctrl+C para salir\n")
    
    while True:
        # 1. Enviar datos
        mensaje_enviar = "HOLA_PI_5\n"
        ser.write(mensaje_enviar.encode('utf-8'))
        print(f"Enviado: {mensaje_enviar.strip()}")
        
        # 2. Esperar un poco a que el hardware procese
        time.sleep(0.1)
        
        # 3. Leer datos
        if ser.in_waiting > 0:
            datos_recibidos = ser.readline().decode('utf-8').strip()
            print(f"Recibido: {datos_recibidos}")
            if datos_recibidos == mensaje_enviar.strip():
                print(">>> ¡ÉXITO! El puerto UART funciona correctamente.")
            else:
                print(">>> ERROR: Los datos recibidos no coinciden.")
        else:
            print(">>> ERROR: No se recibió nada (¿Hiciste el puente físico?)")
            
        print("-" * 30)
        time.sleep(1)

except serial.SerialException as e:
    print(f"Error al abrir el puerto: {e}")
    print("\nSUGERENCIAS:")
    print("1. Verifica que no haya otro programa usando el puerto.")
    print("2. Asegúrate de haber puesto 'dtoverlay=disable-bt' en config.txt.")
    print("3. Prueba con /dev/serial0 o /dev/ttyS0.")
except KeyboardInterrupt:
    print("\nPrueba finalizada.")
finally:
    if 'ser' in locals() and ser.is_open:
        ser.close()
