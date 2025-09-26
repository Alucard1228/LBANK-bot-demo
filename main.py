# main.py - VERSIÓN OPTIMIZADA PARA RAILWAY
import time
import os
import sys
from datetime import datetime, timezone

# Forzar UTF-8 y UTC
os.environ['PYTHONIOENCODING'] = 'utf-8'
os.environ['TZ'] = 'UTC'
try:
    time.tzset()
except:
    pass

def main():
    print("🤖 Bot Zaffex - Versión Optimizada Railway")
    print("[INFO] Iniciando en modo Background Worker...")
    
    # Reducir buffer de salida para ver logs en tiempo real
    sys.stdout.reconfigure(line_buffering=True)
    
    counter = 0
    while True:
        try:
            counter += 1
            current_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            print(f"[LOOP] {counter} | {current_time}")
            
            # Simular trabajo ligero
            time.sleep(2)
            
            # Forzar liberación de memoria cada 100 ciclos
            if counter % 100 == 0:
                import gc
                gc.collect()
                print("[MEMORY] Garbage collection executed")
                
        except KeyboardInterrupt:
            # Ignorar interrupciones (Railway las envía durante reinicios)
            print("[INFO] Ignorando señal de interrupción...")
            continue
        except Exception as e:
            # Manejar cualquier error y continuar
            print(f"[ERROR] {str(e)[:100]} - Continuando...")
            time.sleep(5)
            continue

if __name__ == "__main__":
    main()
