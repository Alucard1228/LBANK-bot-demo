# -*- coding: utf-8 -*-
import json, time, os

def save_state(path, equity, positions_dict):
    """
    positions_dict: dict[(mode,symbol)] -> Position
    """
    data = {
        "ts": int(time.time()),
        "equity": float(equity),
        "positions": []
    }
    for (mode, symbol), p in positions_dict.items():
        data["positions"].append({
            "mode": p.mode,
            "symbol": p.symbol,
            "side": p.side,
            "entry": float(p.entry),
            "qty": float(p.qty),
            "sl": float(p.sl),
            "tp": float(p.tp),
            "open_time": p.open_time
        })
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)

def load_state(path):
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
