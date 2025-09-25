# -*- coding: utf-8 -*-
import pandas as pd
from dataclasses import dataclass
from indicators import ema, atr, adx, rsi

@dataclass
class StrategyParams:
    ema_fast: int = 35
    ema_slow: int = 50
    atr_period: int = 14
    rsi_min: float = 45
    rsi_max: float = 60
    adx_min: float = 18
    max_ema_dist_atr: float = 0.8
    atr_pct_threshold: float = 35.0
    risk_k: float = 2.6
    tp_r: float = 2.0
    use_short: bool = False

def _atr_pct(s_atr: pd.Series, close: pd.Series) -> pd.Series:
    return (s_atr / close.replace(0,1e-12) * 100.0).rename("atr_pct")

def _pct_rank_last(s: pd.Series, win: int = 200, default: float = 100.0) -> float:
    if len(s) < max(50, win): return default
    ref = s.iloc[-win:]
    v = ref.iloc[-1]
    return (ref <= v).mean() * 100.0

def make_signal(df_ltf: pd.DataFrame, df_htf: pd.DataFrame, p: StrategyParams) -> dict:
    close = df_ltf["close"]
    ema_f = ema(close, p.ema_fast)
    ema_s = ema(close, p.ema_slow)
    a = atr(df_ltf, p.atr_period)
    adx_h = adx(df_htf, p.atr_period)
    r = rsi(close, 14)
    atr_pct = _atr_pct(a, close)
    atr_pctl = _pct_rank_last(atr_pct, win=200, default=100.0)
    # filtros
    if adx_h.iloc[-1] < p.adx_min: return {"side": None}
    if not (p.rsi_min <= r.iloc[-1] <= p.rsi_max): return {"side": None}
    if atr_pctl < p.atr_pct_threshold: return {"side": None}
    ema_dist_atr = abs(close.iloc[-1] - ema_s.iloc[-1]) / (a.iloc[-1] + 1e-12)
    if ema_dist_atr > p.max_ema_dist_atr: return {"side": None}
    # señal (ema fast > ema slow y precio sobre la slow)
    long_ok = ema_f.iloc[-1] > ema_s.iloc[-1] and close.iloc[-1] > ema_s.iloc[-1]
    if long_ok:
        entry = float(close.iloc[-1])
        sl = entry - p.risk_k * float(a.iloc[-1])
        rr = entry - sl
        tp = entry + p.tp_r * rr
        return {"side": "long", "entry": entry, "sl": sl, "tp": tp}
    return {"side": None}
