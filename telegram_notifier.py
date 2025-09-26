# telegram_notifier.py
import requests
import os
from typing import Optional

class TelegramNotifier:
    def __init__(self, token: Optional[str], allowed_ids: Optional[str]):
        self.bot_token = str(token or "").strip()
        self.allowed_ids = []
        if allowed_ids:
            # Manejar múltiples IDs separados por comas
            ids = str(allowed_ids).strip().split(",")
            self.allowed_ids = [id_str.strip() for id_str in ids if id_str.strip()]
        
        self._enabled = bool(self.bot_token and self.allowed_ids)
        print(f"[TELEGRAM] Inicializado - Token: {'✓' if self.bot_token else '✗'}, IDs: {self.allowed_ids}")

    def enabled(self) -> bool:
        return self._enabled

    def _send_to_all(self, text: str):
        if not self._enabled:
            print("[TELEGRAM] Deshabilitado - sin token o IDs")
            return
            
        print(f"[TELEGRAM] Enviando a {len(self.allowed_ids)} destinatarios: {text[:50]}...")
        
        for chat_id in self.allowed_ids:
            try:
                url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
                payload = {
                    "chat_id": chat_id,
                    "text": text[:4000],  # Límite de Telegram
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True
                }
                response = requests.post(url, json=payload, timeout=10)
                if response.status_code == 200:
                    print(f"[TELEGRAM] ✅ Enviado a {chat_id}")
                else:
                    print(f"[TELEGRAM] ❌ Error {response.status_code}: {response.text}")
            except Exception as e:
                print(f"[TELEGRAM] ❌ Excepción: {e}")

    def send(self, message: str):
        """Método simple para pruebas"""
        self._send_to_all(message)
    
    # Mantener métodos específicos para compatibilidad
    def send_open(self, **kwargs):
        self.send("📈 Prueba de APERTURA")
    
    def send_close(self, **kwargs):
        self.send("✅ Prueba de CIERRE")
    
    def send_summary(self, **kwargs):
        self.send("📊 Prueba de RESUMEN")
    
    def send_pause(self, **kwargs):
        self.send("⏸️ Prueba de PAUSA")
    
    def send_error(self, error_msg: str):
        self.send(f"⚠️ ERROR: {error_msg}")
