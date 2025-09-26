# telegram_notifier.py
import requests
import os
from typing import Optional

class TelegramNotifier:
    def __init__(self, token: Optional[str], allowed_ids: Optional[str]):
        self.bot_token = token or ""
        self.allowed_ids = (allowed_ids or "").split(",") if allowed_ids else []
        self._enabled = bool(self.bot_token and self.allowed_ids)

    def enabled(self) -> bool:
        return self._enabled

    def _send_to_all(self, text: str):
        if not self._enabled:
            return
        for chat_id in self.allowed_ids:
            try:
                url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
                payload = {
                    "chat_id": chat_id.strip(),
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True
                }
                requests.post(url, json=payload, timeout=10)
            except Exception as e:
                print(f"[TELEGRAM] Error: {e}")

    def send_open(self, symbol: str, mode: str, lotes: int, entry: float, sl: float, tp: float, equity: float, rsi: float = 0):
        """Notificación mejorada para apertura de operaciones"""
        text = (
            f"📈 <b>OPEN BATCH</b>\n"
            f"<b>Símbolo:</b> {symbol.upper()}\n"
            f"<b>Modo:</b> {mode.upper()}\n"
            f"<b>Lotes:</b> {lotes}\n"
            f"<b>Entrada:</b> {entry:.2f}\n"
            f"<b>SL:</b> {sl:.2f} ({((entry-sl)/entry*100):.1f}%)\n"
            f"<b>TP:</b> {tp:.2f} ({((tp-entry)/entry*100):.1f}%)\n"
            f"<b>RSI:</b> {rsi:.1f}\n"
            f"<b>Equity:</b> ${equity:.2f}"
        )
        self._send_to_all(text)

    def send_close(self, symbol: str, mode: str, exit_price: float, pnl: float, pnl_pct: float, reason: str, 
                   win_rate: float, equity: float, total_ops: int):
        """Notificación mejorada para cierre de operaciones"""
        reason_text = "🎯 Take Profit" if reason == "TP" else "🛑 Stop Loss" if reason == "SL" else reason
        
        # Emoji según resultado
        emoji = "✅" if pnl >= 0 else "❌"
        pnl_color = "green" if pnl >= 0 else "red"
        
        text = (
            f"{emoji} <b>{reason_text}</b>\n"
            f"<b>Símbolo:</b> {symbol.upper()}\n"
            f"<b>Modo:</b> {mode.upper()}\n"
            f"<b>Salida:</b> {exit_price:.2f}\n"
            f"<b>PnL:</b> <span class='{pnl_color}'>{pnl:+.6f}</span> ({pnl_pct:+.2f}%)\n"
            f"<b>Win Rate:</b> {win_rate:.1f}% ({total_ops} ops)\n"
            f"<b>Equity:</b> ${equity:.2f}"
        )
        self._send_to_all(text)

    def send_summary(self, minutes: int, trades: int, wins: int, losses: int, 
                    win_rate: float, pnl: float, equity: float, 
                    daily_dd: float = 0.0, by_mode: dict = None):
        """Resumen mejorado"""
        mode_stats = ""
        if by_mode:
            mode_stats = "\n<b>Por modo:</b>\n"
            for mode, count in by_mode.items():
                if count > 0:
                    mode_stats += f"• {mode.title()}: {count}\n"
        
        text = (
            f"📊 <b>Resumen {minutes}m</b>\n"
            f"<b>Operaciones:</b> {trades}\n"
            f"<b>Win Rate:</b> {win_rate:.1f}%\n"
            f"<b>PnL:</b> {pnl:+.6f}\n"
            f"<b>Equity:</b> ${equity:.2f}\n"
            f"<b>Drawdown:</b> {daily_dd:.2f}%{mode_stats}"
        )
        self._send_to_all(text)

    def send_pause(self, minutes: int, reason: str = "Pérdidas diarias"):
        """Notificación de pausa mejorada"""
        text = (
            f"⏸️ <b>PAUSA TEMPORAL</b>\n"
            f"<b>Razón:</b> {reason}\n"
            f"<b>Duración:</b> {minutes} minutos\n"
            f"<b>Reanuda:</b> Automáticamente"
        )
        self._send_to_all(text)

    def send_error(self, error_msg: str):
        """Notificación de errores"""
        text = f"⚠️ <b>ERROR EN BOT</b>\n<code>{error_msg[:200]}</code>"
        self._send_to_all(text)

    def send(self, message: str):
        """Método genérico para retrocompatibilidad"""
        self._send_to_all(message)
