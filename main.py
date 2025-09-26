# -*- coding: utf-8 -*-
"""
Bot PAPER replicando Zaffex: 3 modos independientes (agresivo, moderado, conservador)
Cada modo opera con $100 independientes (saldo total = $300)
"""

import os, time, ccxt
import pandas as pd
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict

from utils_env import load_env, parse_csv, parse_float, parse_int
from paper_portfolio import PaperPortfolio
from trades_logger import TradeLogger
from telegram_notifier import TelegramNotifier
from state_store import save_state, load_state
import ta

STATE_PATH = "paper_state.json"

def clean_tf(s: str) -> str:
    return (s or "").strip().split()[0]

def fetch_ohlcv_df(ex, symbol: str, timeframe: str, limit: int = 100) -> pd.DataFrame:
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

def calculate_rsi(df: pd.DataFrame, period: int = 9) -> pd.Series:
    return ta.momentum.RSIIndicator(close=df["close"], window=period).rsi()

def main():
    env = load_env(".env")

    EXCHANGE_ID = env.get("EXCHANGE","lbank")
    SYMBOLS = ["btc_usdt", "eth_usdt"]

    LTF = clean_tf(env.get("TIMEFRAME_LTF","5m"))

    RISK   = {"agresivo": parse_float(env.get("RISK_AGRESIVO","1.0"),1.0),
              "moderado": parse_float(env.get("RISK_MODERADO","1.0"),1.0),
              "conservador": parse_float(env.get("RISK_CONSERVADOR","1.0"),1.0)}
    
    TP_PCT = {"agresivo": parse_float(env.get("TP_PCT_AGRESIVO","1.0"),1.0),
              "moderado": parse_float(env.get("TP_PCT_MODERADO","1.0"),1.0),
              "conservador": parse_float(env.get("TP_PCT_CONSERVADOR","1.0"),1.0)}
    
    SL_PCT = {"agresivo": parse_float(env.get("SL_PCT_AGRESIVO","1.2"),1.2),
              "moderado": parse_float(env.get("SL_PCT_MODERADO","1.2"),1.2),
              "conservador": parse_float(env.get("SL_PCT_CONSERVADOR","1.2"),1.2)}

    DEMO_MAX_TRADE_USDT = parse_float(env.get("DEMO_MAX_TRADE_USDT","100"),100.0)
    DEMO_MAX_POSITIONS  = parse_int(env.get("DEMO_MAX_POSITIONS","24"),24)
    MIN_NOTIONAL_USDT   = parse_float(env.get("MIN_NOTIONAL_USDT","5"),5.0)
    FEE_TAKER = parse_float(env.get("FEE_TAKER","0.001"),0.001)
    SPREAD_BPS= parse_float(env.get("SPREAD_BPS","0.0003"),0.0003)

    RSI_PERIOD = parse_int(env.get("RSI_PERIOD","9"),9)
    RSI_BUY_THRESHOLD = parse_float(env.get("RSI_REV_LOW","25"),25.0)

    ENTRY_COOLDOWN_MIN = parse_int(env.get("ENTRY_COOLDOWN_MIN","1"),1)
    SYMBOL_LOCK_MIN = parse_int(env.get("SYMBOL_LOCK_MIN","3"),3)
    DAILY_LOSS_LIMIT_PCT = parse_float(env.get("DAILY_LOSS_LIMIT_PCT_MODERADO","0.10"),0.10)
    COOLDOWN_LOSSES = parse_int(env.get("COOLDOWN_LOSSES_MODERADO","3"),3)
    COOLDOWN_MIN = parse_int(env.get("COOLDOWN_MIN_MODERADO","20"),20)

    BATCH_SIZE = {"agresivo": parse_int(env.get("BATCH_SIZE_AGRESIVO","4"),4),
                  "moderado": parse_int(env.get("BATCH_SIZE_MODERADO","6"),6),
                  "conservador": parse_int(env.get("BATCH_SIZE_CONSERVADOR","8"),8)}

    AUTO_SUMMARY_MIN = parse_int(env.get("AUTO_SUMMARY_MIN","15"),15)
    SLEEP_SEC = parse_int(env.get("SLEEP_SEC","2"),2)
    CSV_PATH = env.get("CSV_PATH","operaciones_zaffex.csv")
    PAPER_START_BALANCE = parse_float(env.get("PAPER_START_BALANCE","300"),300.0)

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
            for pos_data in st.get("positions", []):
                portfolio.open(
                    pos_data["mode"], 
                    pos_data["symbol"], 
                    pos_data["side"],
                    pos_data["entry"], 
                    pos_data["qty"], 
                    pos_data["sl"], 
                    pos_data["tp"],
                    reopen=True
                )
            print(f"[STATE] Restaurado: equity={portfolio.equity:.2f} | open={len(portfolio.positions)}")
        except Exception as e:
            print(f"[STATE] No se pudo restaurar: {e}")

    last_ltf_close: Dict[str, Optional[pd.Timestamp]] = {s: None for s in SYMBOLS}
    last_entry_time: Dict[str, datetime] = {}
    symbol_lock_until: Dict[str, datetime] = {}
    summary_since = {"trades":0,"wins":0,"losses":0,"pnl":0.0}
    daily_stats = {"trades":0,"wins":0,"losses":0,"pnl":0.0}
    losses_today = 0
    day_str = datetime.now(timezone.utc).date().isoformat()
    paused_until: Optional[datetime] = None

    print(f"[INFO] Zaffex REPLICA: 3 modos | $100 por modo | LTF={LTF}")
    if tg.enabled(): tg.send("🤖 Bot Zaffex (3 modos) iniciado — $100 por modo")

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
                    df_ltf = fetch_ohlcv_df(ex, symbol, LTF, limit=100)
                except Exception as e:
                    print(f"[WARN] fetch ohlcv {symbol} falló: {e}")
                    if tg.enabled(): tg.send(f"⚠️ Error datos {symbol}: {str(e)[:200]}")
                    continue

                ltf_last_close_ts = df_ltf.index[-1]
                if last_ltf_close[symbol] is not None and ltf_last_close_ts <= last_ltf_close[symbol]:
                    continue
                last_ltf_close[symbol] = ltf_last_close_ts

                # === Cierre para los 3 modos ===
                last_px = float(df_ltf["close"].iloc[-1])
                for profile in ["agresivo", "moderado", "conservador"]:
                    active_positions = portfolio.get_positions(profile, symbol)
                    for pos in active_positions[:]:
                        status = None
                        if last_px >= pos.tp:
                            status = "TP"
                        elif last_px <= pos.sl:
                            status = "SL"
                        
                        if status:
                            pnl, fee = portfolio.close_position(pos, last_px)
                            portfolio.remove_position(pos)
                            logger.close(
                                f"{symbol}-{pos.open_time}-{profile}",
                                last_px,
                                round(pnl,6),
                                0.0,
                                reason=status,
                                equity=portfolio.equity
                            )
                            summary_since["trades"] += 1; daily_stats["trades"] += 1
                            if pnl >= 0: 
                                summary_since["wins"] += 1; daily_stats["wins"] += 1
                            else: 
                                summary_since["losses"] += 1; daily_stats["losses"] += 1; losses_today += 1
                            summary_since["pnl"] += pnl; daily_stats["pnl"] += pnl
                            if tg.enabled(): 
                                tg.send(f"✅ <b>{status}</b> {symbol} [{profile}]\nexit={last_px:.2f}\nPnL={pnl:.6f}\nEquity={portfolio.equity:.2f}")

                # freno diario
                eq_dd = max(0.0, (PAPER_START_BALANCE - portfolio.equity) / PAPER_START_BALANCE)
                if eq_dd >= DAILY_LOSS_LIMIT_PCT or losses_today >= COOLDOWN_LOSSES:
                    paused_until = now + timedelta(minutes=COOLDOWN_MIN)
                    print(f"[PAUSE] Límite diario. Pausa hasta {paused_until.isoformat()}")
                    if tg.enabled(): tg.send(f"⏸️ <b>Pausa</b> por pérdidas. Reanuda: {paused_until.isoformat()}")
                    continue

                if len(portfolio.positions) >= DEMO_MAX_POSITIONS:
                    continue

                # === Señal de entrada para los 3 modos ===
                rsi_series = calculate_rsi(df_ltf, RSI_PERIOD)
                current_rsi = rsi_series.iloc[-1]

                for profile in ["agresivo", "moderado", "conservador"]:
                    cooldown_key = f"{symbol}_{profile}"
                    t_last = last_entry_time.get(cooldown_key)
                    if t_last and (now - t_last).total_seconds() < ENTRY_COOLDOWN_MIN*60:
                        continue

                    if current_rsi < RSI_BUY_THRESHOLD:
                        # Cada modo opera con $100
                        capital_por_modo = 100.0
                        batch_size = BATCH_SIZE[profile]
                        entry = last_px * (1 + SPREAD_BPS)
                        tp_pct = TP_PCT[profile] / 100.0
                        sl_pct = SL_PCT[profile] / 100.0
                        notional_per_lot = capital_por_modo / batch_size
                        
                        if notional_per_lot < MIN_NOTIONAL_USDT:
                            notional_per_lot = MIN_NOTIONAL_USDT
                        if notional_per_lot > DEMO_MAX_TRADE_USDT / batch_size:
                            notional_per_lot = DEMO_MAX_TRADE_USDT / batch_size
                        
                        qty_per_lot = notional_per_lot / entry
                        
                        opened = 0
                        for i in range(batch_size):
                            if len(portfolio.positions) >= DEMO_MAX_POSITIONS:
                                break
                            sl = entry * (1 - sl_pct)
                            tp = entry * (1 + tp_pct)
                            portfolio.open(profile, symbol, "long", entry, qty_per_lot, sl, tp)
                            trade_id = f"{symbol}-{now.isoformat()}-{profile}-lot{i}"
                            logger.open(trade_id, {"symbol":symbol,"mode":profile,"side":"long",
                                                   "entry_px":round(entry,6),"sl_px":round(sl,6),
                                                   "tp_px":round(tp,6),"qty":round(qty_per_lot,6)})
                            opened += 1
                        
                        if opened > 0:
                            last_entry_time[cooldown_key] = now
                            print(f"[OPEN] {symbol} long [{profile}] x{opened} lotes | entry={entry:.2f}")
                            if tg.enabled(): 
                                tg.send(f"📈 <b>OPEN</b> {symbol} [{profile.upper()}] x{opened} lotes\nentry={entry:.2f}")

                symbol_lock_until[symbol] = now + timedelta(minutes=SYMBOL_LOCK_MIN)

            save_state(STATE_PATH, portfolio.equity, portfolio.positions)
            time.sleep(SLEEP_SEC)

    except KeyboardInterrupt:
        print(f"[END] Equity final (paper): {portfolio.equity:.2f}")
        if tg.enabled(): tg.send(f"🛑 Bot detenido. Equity final: {portfolio.equity:.2f}")

if __name__ == "__main__":
    main()