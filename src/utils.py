from src.classes.Messages import Message
from time import sleep

def cli_interface(tx_queue, running_event, stop_event):
    print("\n--- CLI de Pruebas Activa ---")
    print("Comandos: drive <v> <w>, launc, servo <angle>, stop, ping")
    
    while not stop_event.is_set():
        if not running_event.is_set():
            try:
                cmd_input = input("CMD > ").split()
                if not cmd_input: continue
                
                action = cmd_input[0]
                
                if action == "drive":
                    tx_queue.put_nowait(Message.drive(float(cmd_input[1]), float(cmd_input[2])))
                elif action == "launc":
                    tx_queue.put_nowait(Message.launc())
                elif action == "servo":
                    tx_queue.put_nowait(Message.servo(int(cmd_input[1])))
                elif action == "stop":
                    tx_queue.put_nowait(Message.stop())
                elif action == "ping":
                    tx_queue.put_nowait(Message.ping())
                elif action == "s":
                    tx_queue.put_nowait(Message.drive(0.0,0.0))
                elif action == "l":
                    tx_queue.put_nowait(Message.drive(0.4,0.0))
                    sleep(0.1)
                    tx_queue.put_nowait(Message.drive(1.0,0.0))
                    sleep(1)
                    tx_queue.put_nowait(Message.servo(100))
                    tx_queue.put_nowait(Message.drive(0.0,0.0))
                    sleep(0.5)
                    tx_queue.put_nowait(Message.servo(180))

                    
                else:
                    print("Comando no reconocido.")
            except Exception as e:
                print(f"Error en comando: {e}")
        else:
            # Si el robot está corriendo, pausamos brevemente el hilo CLI
            sleep(1)