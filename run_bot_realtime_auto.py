# -*- coding: utf-8 -*-
"""
Bot PAPER con estrategia simplificada: RSI + cruce EMA35/EMA50.
Timeframes: LTF=5m, HTF=15m.
Incluye cierre anticipado en 1.0R y 3 modos de riesgo.
"""

import os, time, ccxt
import pandas as pd
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict

from utils_env import load_env, parse_csv, parse_float, parse_int
from strategy_simple_rsi_ema import StrategyParams, make_signal
from paper_portfolio import PaperPortfolio
from trades_logger import TradeLogger
from telegram_notifier import TelegramNotifier
from indicators import atr, adx
from state_store import save_state, load_state

STATE_PATH = "paper_state.json"

def clean_tf(s: str) -> str:
    return (s or "").strip().split()[0]

def fetch_ohlcv_df(ex, symbol: str, timeframe: str, limit: int = 600) -> pd.DataFrame:
    for intento in range(3):
        try:
            o = ex.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
            df = pd.DataFrame(o, columns=["timestamp","open","high","low","close","volume"])
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
            df.set_index("timestamp", inplace=True)
            last_row = df.iloc[-1]
            if not (last_row["low"] <= last_row["close"] <= last_row["high"]):
                raise ValueError("Datos inconsistentes")
            return df
        except Exception as e:
            if intento == 2:
                raise e
            time.sleep(2)

def get_exchange(ex_id: str, apiKey: str, secret: str):
    ex_id = (ex_id or "").lower().strip()
    candidates = ["lbank", "lbank2"] if ex_id in ("lbank","lbank2") else [ex_id]
    for name in candidates:
        cls = getattr(ccxt, name, None)
        if cls:
            print(f"[CFG] Usando exchange {name}")
            return cls({"apiKey": apiKey, "secret": secret, "enableRateLimit": True})
    cls = getattr(ccxt, "binance", None)
    if cls:
        print(f"[WARN] {ex_id} no disponible. Usando binance (feed PAPER).")
        return cls({"enableRateLimit": True})
    raise RuntimeError(f"Exchange no soportado: {ex_id}")

def main():
    env = load_env(".env")

    EXCHANGE_ID = env.get("EXCHANGE","lbank")
    SYMBOLS = parse_csv(env.get("SYMBOLS","btc_usdt,eth_usdt,bnb_usdt"))
    LTF = clean_tf(env.get("TIMEFRAME_LTF","5m"))
    HTF = clean_tf(env.get("TIMEFRAME_HTF","15m"))  # ← ahora es 15m

    RISK   = {"agresivo": parse_float(env.get("RISK_AGRESIVO","0.03"),0.03),
              "moderado": parse_float(env.get("RISK_MODERADO","0.02"),0.02),
              "conservador": parse_float(env.get("RISK_CONSERVADOR","0.01"),0.01)}
    ATR_K  = {"agresivo": parse_float(env.get("ATR_K_AGRESIVO","2.2"),2.2),
              "moderado": parse_float(env.get("ATR_K_MODERADO","2.6"),2.6),
              "conservador": parse_float(env.get("ATR_K_CONSERVADOR","3.0"),3.0)}
    TP_R   = {"agresivo": parse_float(env.get("TP_R_AGRESIVO","1.8"),1.8),
              "moderado": parse_float(env.get("TP_R_MODERADO","2.0"),2.0),
              "conservador": parse_float(env.get("TP_R_CONSERVADOR","2.2"),2.2)}

    DEMO_MAX_TRADE_USDT = parse_float(env.get("DEMO_MAX_TRADE_USDT","100"),100.0)
    DEMO_MAX_POSITIONS  = parse_int(env.get("DEMO_MAX_POSITIONS","5"),5)
    MIN_NOTIONAL_USDT   = parse_float(env.get("MIN_NOTIONAL_USDT","10"),10.0)
    FEE_TAKER = parse_float(env.get("FEE_TAKER","0.001"),0.001)
    SPREAD_BPS= parse_float(env.get("SPREAD_BPS","0.0003"),0.0003)

    EMA_FAST = parse_int(env.get("EMA_FAST","35"),35)
    EMA_SLOW = parse_int(env.get("EMA_SLOW","50"),50)
    RSI_PERIOD = parse_int(env.get("RSI_PERIOD","14"),14)

    ENTRY_COOLDOWN_MIN = parse_int(env.get("ENTRY_COOLDOWN_MIN","10"),10)
    SYMBOL_LOCK_MIN = parse_int(env.get("SYMBOL_LOCK_MIN","15"),15)
    DAILY_LOSS_LIMIT_PCT = parse_float(env.get("DAILY_LOSS_LIMIT_PCT_MODERADO","0.03"),0.03)
    COOLDOWN_LOSSES = parse_int(env.get("COOLDOWN_LOSSES_MODERADO","2"),2)
    COOLDOWN_MIN = parse_int(env.get("COOLDOWN_MIN_MODERADO","45"),45)
    PROFILE_LOCK_MIN = parse_int(env.get("PROFILE_LOCK_MIN","20"),20)

    AUTO_SUMMARY_MIN = parse_int(env.get("AUTO_SUMMARY_MIN","15"),15)
    SLEEP_SEC = parse_int(env.get("SLEEP_SEC","5"),5)
    CSV_PATH = env.get("CSV_PATH","operaciones.csv")
    PAPER_START_BALANCE = parse_float(env.get("PAPER_START_BALANCE","1000"),1000.0)

    RSI_THRESHOLD = parse_float(env.get("RSI_ENTRY","50"),50.0)

    tg = TelegramNotifier(env.get("TELEGRAM_TOKEN"), env.get("TELEGRAM_ALLOWED_IDS"))
    try:
        ex = get_exchange(EXCHANGE_ID, env.get("API_KEY",""), env.get("API_SECRET",""))
    except Exception as e:
        print(f"[ERR] Exchange init: {e}")
        return

    portfolio = PaperPortfolio(start_eq=PAPER_START_BALANCE, fee_taker=FEE_TAKER)
    logger = TradeLogger(csv_path=CSV_PATH)

    st = load_state(STATE_PATH)
    if st:
        try:
            portfolio.equity = float(st.get("equity", portfolio.equity))
            for pos in st.get("positions", []):
                portfolio.open(
                    pos["mode"], pos["symbol"], pos["side"],
                    pos["entry"], pos["qty"], pos["sl"], pos["tp"],
                    reopen=True
                )
            print(f"[STATE] Restaurado: equity={portfolio.equity:.2f} | open={len(portfolio.positions)}")
        except Exception as e:
            print(f"[STATE] No se pudo restaurar: {e}")

    last_ltf_close: Dict[str, Optional[pd.Timestamp]] = {s: None for s in SYMBOLS}
    last_entry_time: Dict[str, datetime] = {}
    symbol_lock_until: Dict[str, datetime] = {}
    current_profile: Dict[str, str] = {s: "moderado" for s in SYMBOLS}
    profile_lock_until: Dict[str, datetime] = {s: datetime.min.replace(tzinfo=timezone.utc) for s in SYMBOLS}
    summary_since = {"trades":0,"wins":0,"losses":0,"pnl":0.0}
    daily_stats = {"trades":0,"wins":0,"losses":0,"pnl":0.0}
    losses_today = 0
    day_str = datetime.now(timezone.utc).date().isoformat()
    paused_until: Optional[datetime] = None

    sp = StrategyParams(
        ema_fast=EMA_FAST,
        ema_slow=EMA_SLOW,
        rsi_period=RSI_PERIOD,
        rsi_threshold=RSI_THRESHOLD,
        risk_k=ATR_K["moderado"],
        tp_r=TP_R["moderado"]
    )

    print(f"[INFO] Estrategia SIMPLE: RSI + EMA | LTF={LTF} HTF={HTF} SYMBOLS={SYMBOLS}")
    if tg.enabled(): tg.send("🤖 Bot (RSI+EMA) iniciado en PAPER — Timeframes: 5m / 15m")

    next_summary_at = datetime.now(timezone.utc).replace(second=0, microsecond=0) + timedelta(minutes=AUTO_SUMMARY_MIN)

    try:
        while True:
            now = datetime.now(timezone.utc)

            if now.date().isoformat() != day_str:
                losses_today = 0; day_str = now.date().isoformat()
                daily_stats = {"trades":0,"wins":0,"losses":0,"pnl":0.0}

            if paused_until and now < paused_until:
                save_state(STATE_PATH, portfolio.equity, portfolio.positions)
                time.sleep(SLEEP_SEC); continue
            else:
                paused_until = None

            if AUTO_SUMMARY_MIN > 0 and now >= next_summary_at:
                tr = summary_since["trades"]; wr = (summary_since["wins"]/tr*100.0) if tr>0 else 0.0
                text = ("🕒 Resumen {m}m\nOps: {t} | Win: {w} | Loss: {l}\nWR: {wr:.1f}% | PnL: {p:.6f}\nEquity: {e:.2f}"
                        ).format(m=AUTO_SUMMARY_MIN, t=tr, w=summary_since["wins"], l=summary_since["losses"],
                                 wr=wr, p=summary_since["pnl"], e=portfolio.equity)
                print("[SUMMARY]", text.replace("\n"," | "))
                if tg.enabled(): tg.send(text)
                summary_since = {"trades":0,"wins":0,"losses":0,"pnl":0.0}
                next_summary_at = now.replace(second=0, microsecond=0) + timedelta(minutes=AUTO_SUMMARY_MIN)

            for symbol in SYMBOLS:
                if symbol in symbol_lock_until and now < symbol_lock_until[symbol]:
                    continue
                try:
                    df_ltf = fetch_ohlcv_df(ex, symbol, LTF, limit=600)
                    df_htf = fetch_ohlcv_df(ex, symbol, HTF, limit=200)  # 15m → menos datos necesarios
                    print(f"[DEBUG] {symbol} → LTF={df_ltf['close'].iloc[-1]:.6f} | HTF={df_htf['close'].iloc[-1]:.6f}")
                except Exception as e:
                    print(f"[WARN] fetch ohlcv {symbol} falló: {e}")
                    if tg.enabled(): tg.send(f"⚠️ Error datos {symbol}: {str(e)[:200]}")
                    continue

                ltf_last_close_ts = df_ltf.index[-1]
                if last_ltf_close[symbol] is not None and ltf_last_close_ts <= last_ltf_close[symbol]:
                    continue
                last_ltf_close[symbol] = ltf_last_close_ts

                # === Seleccionar perfil dinámico usando HTF (15m) ===
                adx_htf = adx(df_htf, n=14).iloc[-1]
                atr_series = atr(df_ltf, 14)
                atr_pct = (atr_series / df_ltf["close"].replace(0,1e-12) * 100.0)
                pctl = (atr_pct.iloc[-200:] <= atr_pct.iloc[-1]).mean() * 100.0 if len(atr_pct) >= 200 else 100.0

                if (adx_htf >= 25) and (pctl >= 50):
                    profile = "agresivo"
                elif (adx_htf <= 18) or (pctl <= 30):
                    profile = "conservador"
                else:
                    profile = "moderado"

                # === Cierre: TP / SL / Ganancia Asegurada ===
                last_px = float(df_ltf["close"].iloc[-1])
                status = portfolio.mark(profile, symbol, last_px)

                if status is None:
                    pos = portfolio.positions.get((profile, symbol))
                    if pos and pos.side == "long" and last_px > pos.entry:
                        r_val = pos.entry - pos.sl
                        if r_val > 0:
                            r_actual = (last_px - pos.entry) / r_val
                            if r_actual >= 1.0:
                                status = "PROFIT_TAKE"

                if status in ("TP", "SL", "PROFIT_TAKE"):
                    pnl, fee, pos = portfolio.close(profile, symbol, last_px)
                    r_val = abs(pos.entry - pos.sl)
                    pnl_r = pnl / max(r_val, 1e-9)
                    from math import isfinite as _isfinite
                    logger.close(
                        f"{symbol}-{pos.open_time}",
                        last_px,
                        round(pnl,6) if _isfinite(pnl) else 0.0,
                        round(pnl_r,6) if _isfinite(pnl_r) else 0.0,
                        reason=status,
                        equity=portfolio.equity
                    )
                    summary_since["trades"] += 1; daily_stats["trades"] += 1
                    if pnl >= 0: summary_since["wins"] += 1; daily_stats["wins"] += 1
                    else: summary_since["losses"] += 1; daily_stats["losses"] += 1; losses_today += 1
                    summary_since["pnl"] += pnl; daily_stats["pnl"] += pnl
                    if tg.enabled(): 
                        reason_text = "Ganancia Asegurada" if status == "PROFIT_TAKE" else status
                        tg.send(f"✅ <b>{reason_text}</b> {symbol}\nexit={last_px:.6f}\nPnL={pnl:.6f} (R={pnl_r:.3f})\nEquity={portfolio.equity:.2f}")
                    continue

                # freno diario
                eq_dd = max(0.0, (PAPER_START_BALANCE - portfolio.equity) / PAPER_START_BALANCE)
                if eq_dd >= DAILY_LOSS_LIMIT_PCT or losses_today >= COOLDOWN_LOSSES:
                    paused_until = now + timedelta(minutes=COOLDOWN_MIN)
                    print(f"[PAUSE] Límite diario. Pausa hasta {paused_until.isoformat()}")
                    if tg.enabled(): tg.send(f"⏸️ <b>Pausa</b> por pérdidas. Reanuda: {paused_until.isoformat()}")
                    continue

                if len(portfolio.positions) >= DEMO_MAX_POSITIONS:
                    continue

                # señal / apertura
                sp.risk_k = ATR_K[profile]
                sp.tp_r = TP_R[profile]
                sig = make_signal(df_ltf, df_htf, sp)
                if sig.get("side") and portfolio.can_open(profile, symbol):
                    t_last = last_entry_time.get(symbol)
                    if t_last and (now - t_last).total_seconds() < ENTRY_COOLDOWN_MIN*60:
                        continue
                    side = sig["side"]; entry = sig["entry"] * (1 + SPREAD_BPS if side=="long" else 1 - SPREAD_BPS)
                    sl = sig["sl"]; tp = sig["tp"]; r_val = abs(entry - sl)
                    if r_val <= 0: continue
                    risk_frac = RISK[profile]
                    notional_risk = portfolio.equity * risk_frac
                    qty = max((notional_risk / r_val), 0.0)
                    notional = entry * qty
                    if notional < MIN_NOTIONAL_USDT or notional > DEMO_MAX_TRADE_USDT:
                        qty = min(max(MIN_NOTIONAL_USDT/entry, qty), DEMO_MAX_TRADE_USDT/entry)
                        notional = entry * qty
                    if notional < MIN_NOTIONAL_USDT: continue
                    portfolio.open(profile, symbol, side, entry, qty, sl, tp)
                    trade_id = f"{symbol}-{now.isoformat()}"
                    logger.open(trade_id, {"symbol":symbol,"mode":profile,"side":side,
                                           "entry_px":round(entry,6),"sl_px":round(sl,6),
                                           "r_value":round(r_val,6),"qty":round(qty,6)})
                    last_entry_time[symbol] = now
                    symbol_lock_until[symbol] = now + timedelta(minutes=SYMBOL_LOCK_MIN)
                    print(f"[OPEN] {symbol} {side} [{profile}] qty={qty:.6f} entry={entry:.6f} sl={sl:.6f} tp={tp:.6f} equity={portfolio.equity:.2f}")
                    if tg.enabled(): tg.send(f"📈 <b>OPEN</b> {symbol} {side} [{profile.upper()}]\nqty={qty:.6f}\nentry={entry:.6f} sl={sl:.6f} tp={tp:.6f}\nequity={portfolio.equity:.2f}")

            save_state(STATE_PATH, portfolio.equity, portfolio.positions)
            time.sleep(SLEEP_SEC)

    except KeyboardInterrupt:
        print(f"[END] Equity final (paper): {portfolio.equity:.2f}  CSV: {os.path.abspath(CSV_PATH)}  Reason=manual")
        if tg.enabled(): tg.send(f"🛑 Bot detenido por usuario. Equity final (paper): {portfolio.equity:.2f}")

if __name__ == "__main__":
    main()