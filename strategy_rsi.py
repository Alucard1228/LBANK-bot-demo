# -*- coding: utf-8 -*-
"""
Estrategia RSI:
A) Tendencial (ADX alto): entra LONG cuando RSI cruza > 50 (no sobreextendido), precio > EMA50,
   ATR% suficiente y distancia a EMA50 contenida.
B) Reversión (ADX bajo): entra LONG cuando RSI cruza > rsi_rev_low (=30 por defecto) con los mismos
   controles de volatilidad/distancia; pensado para rangos.
SL por ATR (risk_k) y TP por múltiplos de R (tp_r).
"""

from dataclasses import dataclass
from typing import Dict
import pandas as pd
import numpy as np

# Intentar usar tus indicadores; si no están, usar fallbacks simples
try:
    from indicators import ema, rsi, atr, adx
except Exception:
    def ema(series: pd.Series, n: int) -> pd.Series:
        return series.ewm(span=n, adjust=False).mean()

    def rsi(series: pd.Series, n: int = 14) -> pd.Series:
        delta = series.diff()
        up = (delta.clip(lower=0)).ewm(alpha=1/n, adjust=False).mean()
        down = (-delta.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
        rs = up / (down.replace(0, 1e-12))
        return 100 - (100 / (1 + rs))

    def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
        high, low, close = df["high"], df["low"], df["close"]
        prev_close = close.shift(1)
        tr = pd.concat([(high - low).abs(),
                        (high - prev_close).abs(),
                        (low - prev_close).abs()], axis=1).max(axis=1)
        return tr.ewm(alpha=1/n, adjust=False).mean()

    def adx(df: pd.DataFrame, n: int = 14) -> pd.Series:
        high, low, close = df["high"], df["low"], df["close"]
        plus_dm = (high.diff()).where((high.diff() > low.diff()), 0.0).clip(lower=0)
        minus_dm = (-low.diff()).where((high.diff() <= low.diff()), 0.0).clip(lower=0)
        trur = atr(df, n)
        plus_di = 100 * (plus_dm.ewm(alpha=1/n, adjust=False).mean() / trur.replace(0, 1e-12))
        minus_di = 100 * (minus_dm.ewm(alpha=1/n, adjust=False).mean() / trur.replace(0, 1e-12))
        dx = 100 * ((plus_di - minus_di).abs() / ((plus_di + minus_di).replace(0, 1e-12)))
        return dx.ewm(alpha=1/n, adjust=False).mean()

@dataclass
class StrategyParams:
    # Medias / ATR
    ema_fast: int = 35
    ema_slow: int = 50
    atr_period: int = 14

    # Filtros comunes
    adx_min: float = 20.0
    max_ema_dist_atr: float = 0.8        # distancia máx precio-EMA50 en múltiplos de ATR
    atr_pct_threshold: float = 35.0      # (ATR/close*100) mínimo en LTF

    # RSI tendencial
    rsi_period: int = 14
    rsi_entry: float = 50.0              # cruce arriba activa entrada tendencial
    rsi_exit: float = 47.0               # (opcional, no se usa aquí)
    rsi_ceiling: float = 60.0            # techo para evitar entrar sobreextendido

    # Reversión RSI (para rangos; ADX bajo)
    use_rsi_reversion: bool = True
    adx_min_reversion: float = 18.0      # si ADX(HTF) < esto, considerar reversión
    rsi_rev_low: float = 30.0            # cruce arriba activa BUY de reversión

    # Riesgo / TP
    risk_k: float = 2.6
    tp_r: float = 2.0
    use_short: bool = False

def _atr_pct(df_ltf: pd.DataFrame, atr_period: int) -> pd.Series:
    a = atr(df_ltf, n=atr_period)
    return (a / df_ltf["close"].replace(0, 1e-12) * 100.0).rename("atr_pct")

def make_signal(df_ltf: pd.DataFrame, df_htf: pd.DataFrame, p: StrategyParams) -> Dict:
    if len(df_ltf) < max(100, p.ema_slow + p.rsi_period + p.atr_period):
        return {}

    close_ltf = df_ltf["close"]
    rsi_ltf = rsi(close_ltf, n=p.rsi_period)
    ema_slow = ema(close_ltf, p.ema_slow)
    atr_ltf = atr(df_ltf, p.atr_period)

    last = -1
    rsi_now  = float(rsi_ltf.iloc[last])
    rsi_prev = float(rsi_ltf.iloc[last-1])
    px_now   = float(close_ltf.iloc[last])
    ema_slow_now = float(ema_slow.iloc[last])
    atr_now  = float(atr_ltf.iloc[last])

    # ADX (HTF) para régimen
    adx_htf_now = float(adx(df_htf, n=p.atr_period).iloc[-1])

    # Filtro de volatilidad mínima
    atr_pct_now = float(_atr_pct(df_ltf, p.atr_period).iloc[-1])
    if atr_pct_now < p.atr_pct_threshold:
        return {}

    # Filtro de no-persecución: distancia a EMA50 contenida
    ema_dist_atr = abs(px_now - ema_slow_now) / max(atr_now, 1e-12)
    if ema_dist_atr > p.max_ema_dist_atr:
        return {}

    # ===== A) MODO TENDENCIAL (ADX alto) =====
    if adx_htf_now >= p.adx_min:
        # precio debe estar sobre EMA50
        if not (px_now > ema_slow_now):
            return {}
        # cruce RSI > entrada y no sobreextendido
        cross_up_50 = (rsi_prev < p.rsi_entry) and (rsi_now >= p.rsi_entry)
        if not cross_up_50 or (rsi_now > p.rsi_ceiling):
            return {}
        entry = px_now
        sl = entry - p.risk_k * atr_now
        if sl <= 0 or (entry - sl) <= 0:
            return {}
        r_value = entry - sl
        tp = entry + p.tp_r * r_value
        return {"side":"long","entry":float(entry),"sl":float(sl),"tp":float(tp)}

    # ===== B) MODO REVERSIÓN (ADX bajo) =====
    if p.use_rsi_reversion and (adx_htf_now < p.adx_min_reversion):
        # cruce RSI sobre rsi_rev_low (salida de sobreventa)
        cross_up_rev = (rsi_prev <= p.rsi_rev_low) and (rsi_now > p.rsi_rev_low)
        if not cross_up_rev:
            return {}
        entry = px_now
        sl = entry - p.risk_k * atr_now
        if sl <= 0 or (entry - sl) <= 0:
            return {}
        r_value = entry - sl
        tp = entry + p.tp_r * r_value
        return {"side":"long","entry":float(entry),"sl":float(sl),"tp":float(tp)}

    return {}
