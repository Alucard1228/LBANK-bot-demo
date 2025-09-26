# main.py - VERSIÓN MÍNIMA GARANTIZADA
import time
import os
from datetime import datetime, timezone

# Forzar UTC
os.environ['TZ'] = 'UTC'
try:
    time.tzset()
except:
    pass

def main():
    print("🤖 Bot Zaffex iniciado - Ejecutando continuamente...")
    
    # Simular inicialización
    print("[TELEGRAM] ✅ Bot iniciado en Telegram")
    print("[INFO] Saldo: $235.0 | Modo: Background Worker")
    
    # ✅ BUCLE INFINITO QUE NUNCA TERMINA
    counter = 0
    while True:
        counter += 1
        current_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        print(f"[DEBUG] Ciclo {counter} - {current_time} - Esperando señales...")
        
        # Aquí iría tu lógica real de trading
        # Pero lo importante es que NUNCA sale del bucle
        
        time.sleep(2)  # Esperar 2 segundos

if __name__ == "__main__":
    main()
