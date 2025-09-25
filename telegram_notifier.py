# -*- coding: utf-8 -*-
import time, requests
from typing import List, Optional

class TelegramNotifier:
    def __init__(self, token: Optional[str], allowed_ids_csv: Optional[str] = None):
        self.token = (token or "").strip()
        self.base = f"https://api.telegram.org/bot{self.token}" if self.token else None
        self.allowed_ids: List[int] = []
        if allowed_ids_csv:
            for x in str(allowed_ids_csv).split(","):
                x = x.strip()
                if x:
                    try: self.allowed_ids.append(int(x))
                    except: pass
        self._last_ts = 0.0
        self._min_interval = 1.0

    def enabled(self) -> bool:
        return bool(self.base and self.allowed_ids)

    def _send(self, chat_id: int, text: str):
        if not self.base: return False
        now = time.time()
        if now - self._last_ts < self._min_interval:
            time.sleep(self._min_interval - (now - self._last_ts))
        self._last_ts = time.time()
        try:
            url = f"{self.base}/sendMessage"
            payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
            r = requests.post(url, json=payload, timeout=10)
            return r.ok
        except Exception:
            return False

    def send(self, text: str):
        if not self.enabled(): return False
        any_ok = False
        for cid in self.allowed_ids:
            any_ok = self._send(cid, text) or any_ok
        return any_ok
