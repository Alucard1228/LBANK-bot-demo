# strategy_simple_rsi_ema.py
# Estrategia simplificada: solo RSI + cruce EMA35/EMA50

from dataclasses import dataclass
from typing import Dict
import pandas as pd
import numpy as np

# Intentar usar tus indicadores
try:
    from indicators import ema, rsi, atr
except Exception:
    # Fallback básico (no debería usarse si tienes indicators.py)
    def ema(series: pd.Series, n: int) -> pd.Series:
        return series.ewm(span=n, adjust=False).mean()
    def rsi(series: pd.Series, n: int = 14) -> pd.Series:
        delta = series.diff()
        up = delta.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
        down = (-delta.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
        rs = up / (down.replace(0, 1e-12))
        return 100 - (100 / (1 + rs))
    def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
        tr = pd.concat([
            df["high"] - df["low"],
            (df["high"] - df["close"].shift()).abs(),
            (df["low"] - df["close"].shift()).abs()
        ], axis=1).max(axis=1)
        return tr.ewm(alpha=1/n, adjust=False).mean()

@dataclass
class StrategyParams:
    ema_fast: int = 35
    ema_slow: int = 50
    rsi_period: int = 14
    rsi_threshold: float = 50.0  # debe estar por encima para entrar
    risk_k: float = 2.5         # SL = entry - risk_k * ATR
    tp_r: float = 2.0           # TP = entry + tp_r * (entry - SL)

def make_signal(df_ltf: pd.DataFrame, df_htf: pd.DataFrame, p: StrategyParams) -> Dict:
    # Validación mínima de datos
    if len(df_ltf) < max(100, p.ema_slow + p.rsi_period + 14):
        return {}

    close = df_ltf["close"]
    ema_fast = ema(close, p.ema_fast)
    ema_slow = ema(close, p.ema_slow)
    rsi_series = rsi(close, p.rsi_period)
    atr_series = atr(df_ltf, 14)

    # Últimos valores
    px = float(close.iloc[-1])
    ema_f = float(ema_fast.iloc[-1])
    ema_s = float(ema_slow.iloc[-1])
    rsi_val = float(rsi_series.iloc[-1])
    atr_val = float(atr_series.iloc[-1])

    # Verificar NaN
    if any(pd.isna([px, ema_f, ema_s, rsi_val, atr_val])):
        return {}

    # Condición 1: cruce EMA (hoy EMA35 > EMA50, ayer no)
    ema_cross = (ema_fast.iloc[-1] > ema_slow.iloc[-1]) and (ema_fast.iloc[-2] <= ema_slow.iloc[-2])
    
    # Condición 2: RSI > 50
    rsi_ok = rsi_val > p.rsi_threshold
    
    # Condición 3: precio por encima de EMA50
    price_above_ema = px > ema_s

    if ema_cross and rsi_ok and price_above_ema:
        entry = px
        sl = entry - p.risk_k * atr_val
        if sl <= 0 or (entry - sl) <= 0:
            return {}
        tp = entry + p.tp_r * (entry - sl)
        return {"side": "long", "entry": float(entry), "sl": float(sl), "tp": float(tp)}

    return {}