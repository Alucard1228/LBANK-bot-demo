# state_store.py
import json
import os
from typing import List

def save_state(path: str, equity: float, positions: List):
    """Guarda el estado del portfolio (equity + lista de posiciones)"""
    state = {
        "equity": equity,
        "positions": []
    }
    
    for pos in positions:
        # Convertir objeto Position a dict
        state["positions"].append({
            "mode": pos.mode,
            "symbol": pos.symbol,
            "side": pos.side,
            "entry": pos.entry,
            "qty": pos.qty,
            "sl": pos.sl,
            "tp": pos.tp,
            "open_time": pos.open_time
        })
    
    with open(path, 'w') as f:
        json.dump(state, f, indent=2)

def load_state(path: str):
    """Carga el estado del portfolio"""
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"[WARN] No se pudo cargar {path}: {e}")
        return None
