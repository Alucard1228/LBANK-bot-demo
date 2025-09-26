# trades_logger.py
import csv
import os
from datetime import datetime
from typing import Dict

class TradeLogger:
    def __init__(self, csv_path: str = "operaciones_zaffex.csv"):
        self.csv_path = csv_path
        # Añadir columna 'timestamp' si no existe
        if not os.path.exists(csv_path):
            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    "id", "timestamp", "type", "symbol", "mode", "side", 
                    "entry_px", "exit_px", "qty", "pnl", "r", "reason", "equity"
                ])

    def open(self, trade_id: str, data: Dict):
        timestamp = datetime.now().isoformat()
        with open(self.csv_path, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                trade_id,
                timestamp,
                "OPEN",
                data.get("symbol", ""),
                data.get("mode", ""),
                data.get("side", ""),
                data.get("entry_px", 0),
                "",
                data.get("qty", 0),
                "",
                "",
                "",
                data.get("equity", 0)
            ])

    def close(self, trade_id: str, exit_px: float, pnl: float, r: float, reason: str, equity: float):
        timestamp = datetime.now().isoformat()
        with open(self.csv_path, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                trade_id,
                timestamp,
                "CLOSE",
                "",
                "",
                "",
                "",
                exit_px,
                "",
                pnl,
                r,
                reason,
                equity
            ])
