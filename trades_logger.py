# -*- coding: utf-8 -*-
import csv, os, time
from typing import Dict, Optional

class TradeLogger:
    def __init__(self, csv_path: str = "operaciones.csv"):
        self.csv_path = csv_path
        self._ensure_header()

    def _ensure_header(self):
        if not os.path.exists(self.csv_path):
            with open(self.csv_path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow([
                    "ts","event","id","symbol","mode","side",
                    "entry_px","sl_px","qty","exit_px","pnl","pnl_r","reason","equity"
                ])

    def open(self, trade_id: str, data: Dict):
        with open(self.csv_path, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow([
                int(time.time()), "OPEN", trade_id,
                data.get("symbol",""), data.get("mode",""), data.get("side",""),
                data.get("entry_px",""), data.get("sl_px",""), data.get("qty",""),
                "", "", "", "", ""
            ])

    def close(self, trade_id: str, exit_px: float, pnl: float, pnl_r: float, reason: str, equity: Optional[float] = None):
        with open(self.csv_path, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow([
                int(time.time()), "CLOSE", trade_id,
                "", "", "",
                "", "", "",
                exit_px, pnl, pnl_r, reason,
                equity if equity is not None else ""
            ])
