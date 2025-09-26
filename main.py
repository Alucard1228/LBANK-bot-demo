# -*- coding: utf-8 -*-
"""
Bot PAPER replicando Zaffex - VERSIÓN PRODUCCIÓN
Ejecuta continuamente sin detenerse
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

# Forzar timezone UTC
os.environ['TZ'] = 'UTC'
try:
    time.tzset()
except:
    pass

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
            return cls({"apiKey": apiKey, "secret": secret, "enableRateLimit": True})
    cls = getattr(ccxt, "binance", None)
    if cls:
        return cls({"enableRateLimit": True})
    raise RuntimeError(f"Exchange no soportado: {ex_id}")

def calculate_rsi(df: pd.DataFrame, period: int = 9) -> pd.Series:
    return ta.momentum.RSIIndicator(close=df["close"], window=period).rsi()

def main():
    env = load_env(".env")
    
    # FORZAR MODO PRODUCCIÓN
    FORCE_PRODUCTION = True

    EXCHANGE_ID = env.get("EXCHANGE","lbank")
    SYMBOLS = ["btc_usdt", "eth_usdt"]
    LTF = clean_tf(env.get("TIMEFRAME_LTF","1m"))

    RISK   = {"agresivo": parse_float(env.get("RISK_AGRESIVO","0.20"),0.20),
              "moderado": parse_float(env.get("RISK_MODERADO","0.15"),0.15),
              "conservador": parse_float(env.get("RISK_CONSERVADOR","0.10"),0.10)}
    
    TP_PCT = {"agresivo": parse_float(env.get("TP_PCT_AGRESIVO","1.0"),1.0),
              "moderado": parse_float(env.get("TP_PCT_MODERADO","1.0"),1.0),
              "conservador": parse_float(env.get("TP_PCT_CONSERVADOR","1.0"),1.0)}
    
    SL_PCT = {"agresivo": parse_float(env.get("SL_PCT_AGRESIVO","1.2"),1.2),
              "moderado": parse_float(env.get("SL_PCT_MODERADO","1.2"),1.2),
              "conservador": parse_float(env.get("SL_PCT_CONSERVADOR","1.2"),1.2)}

    DEMO_MAX_TRADE_USDT = parse_float(env.get("DEMO_MAX_TRADE_USDT","50"),50.0)
    DEMO_MAX_POSITIONS  = parse_int(env.get("DEMO_MAX_POSITIONS","12"),12)
    MIN_NOTIONAL_USDT   = parse_float(env.get("MIN_NOTIONAL_USDT","0.5"),0.5)
    FEE_TAKER = parse_float(env.get("FEE_TAKER","0.001"),0.001)
    SPREAD_BPS= parse_float(env.get("SPREAD_BPS","0.0003"),0.0003)

    RSI_PERIOD = parse_int(env.get("RSI_PERIOD","9"),9)
    RSI_BUY_THRESHOLD = parse_float(env.get("RSI_REV_LOW","25"),25.0)

    ENTRY_COOLDOWN_MIN = parse_int(env.get("ENTRY_COOLDOWN_MIN","1"),1)
    SYMBOL_LOCK_MIN = parse_int(env.get("SYMBOL_LOCK_MIN","3"),3)
    DAILY_LOSS_LIMIT_PCT = parse_float(env.get("DAILY_LOSS_LIMIT_PCT_MODERADO","0.05"),0.05)
    COOLDOWN_LOSSES = parse_int(env.get("COOLDOWN_LOSSES_MODERADO","2"),2)
    COOLDOWN_MIN = parse_int(env.get("COOLDOWN_MIN_MODERADO","30"),30)

    BATCH_SIZE = {"agresivo": parse_int(env.get("BATCH_SIZE_AGRESIVO","3"),3),
                  "moderado": parse_int(env.get("BATCH_SIZE_MODERADO","4"),4),
                  "conservador": parse_int(env.get("BATCH_SIZE_CONSERVADOR","5"),5)}

    SLEEP_SEC = parse_int(env.get("SLEEP_SEC","2"),2)
    CSV_PATH = env.get("CSV_PATH","operaciones_zaffex.csv")
    PAPER_START_BALANCE = parse_float(env.get("PAPER_START_BALANCE","235"),235.0)

    tg = TelegramNotifier(env.get("TELEGRAM_TOKEN"), env.get("TELEGRAM_ALLOWED_IDS"))
    if tg.enabled():
        tg.send("🤖 Bot Zaffex REALISTA iniciado — Saldo: $235")

    try:
        ex = get_exchange(EXCHANGE_ID, env.get("API_KEY",""), env.get("API_SECRET",""))
    except Exception as e:
        if tg.enabled(): 
            tg.send_error(f"Exchange init: {str(e)[:200]}")
        return

    portfolio = PaperPortfolio(start_eq=PAPER_START_BALANCE, fee_taker=FEE_TAKER)
    logger = TradeLogger(csv_path=CSV_PATH)
    
    print(f"[FRESH] Inicio fresco con equity={PAPER_START_BALANCE}")
    print(f"[INFO] Zaffex REALISTA: Saldo ${PAPER_START_BALANCE} | LTF={LTF}")

    last_ltf_close: Dict[str, Optional[pd.Timestamp]] = {s: None for s in SYMBOLS}
    last_entry_time: Dict[str, datetime] = {}
    symbol_lock_until: Dict[str, datetime] = {}
    paused_until: Optional[datetime] = None

    # ✅ BUCLE INFINITO SIN CONDICIONES DE SALIDA
    while True:
        now = datetime.now(timezone.utc)

        for symbol in SYMBOLS:
            try:
                df_ltf = fetch_ohlcv_df(ex, symbol, LTF, limit=100)
            except Exception as e:
                if tg.enabled(): tg.send_error(f"Error datos {symbol}: {str(e)[:200]}")
                continue

            ltf_last_close_ts = df_ltf.index[-1]
            if last_ltf_close[symbol] is not None and ltf_last_close_ts <= last_ltf_close[symbol]:
                continue
            last_ltf_close[symbol] = ltf_last_close_ts

            # Cierre de posiciones
            last_px = float(df_ltf["close"].iloc[-1])
            for profile in ["agresivo", "moderado", "conservador"]:
                active_positions = portfolio.get_positions(profile, symbol)
                for pos in active_positions[:]:
                    if last_px >= pos.tp or last_px <= pos.sl:
                        pnl, fee = portfolio.close_position(pos, last_px)
                        portfolio.remove_position(pos)
                        if tg.enabled():
                            tg.send(f"✅ {'TP' if last_px >= pos.tp else 'SL'} {symbol} PnL: {pnl:.6f}")

            # Verificación de límites
            eq_dd = max(0.0, (PAPER_START_BALANCE - portfolio.equity) / PAPER_START_BALANCE)
            if eq_dd >= DAILY_LOSS_LIMIT_PCT:
                cooldown_minutes = 30
                paused_until = now + timedelta(minutes=cooldown_minutes)
                if tg.enabled(): 
                    tg.send(f"⏸️ Pausa {cooldown_minutes} min por límite diario")
                time.sleep(60)
                continue

            # Señal de entrada
            rsi_series = calculate_rsi(df_ltf, RSI_PERIOD)
            current_rsi = rsi_series.iloc[-1]

            for profile in ["agresivo", "moderado", "conservador"]:
                if current_rsi < RSI_BUY_THRESHOLD:
                    risk_frac = RISK[profile]
                    total_risk_capital = portfolio.equity * risk_frac
                    batch_size = BATCH_SIZE[profile]
                    entry = last_px * (1 + SPREAD_BPS)
                    sl_pct = SL_PCT[profile] / 100.0
                    tp_pct = TP_PCT[profile] / 100.0
                    notional_per_lot = total_risk_capital / batch_size
                    
                    if notional_per_lot < MIN_NOTIONAL_USDT:
                        notional_per_lot = MIN_NOTIONAL_USDT
                    qty_per_lot = notional_per_lot / entry
                    
                    for i in range(batch_size):
                        if len(portfolio.positions) >= DEMO_MAX_POSITIONS:
                            break
                        sl = entry * (1 - sl_pct)
                        tp = entry * (1 + tp_pct)
                        portfolio.open(profile, symbol, "long", entry, qty_per_lot, sl, tp)
                    
                    if tg.enabled():
                        tg.send(f"📈 OPEN {symbol} {profile} x{batch_size} lotes @ {entry:.2f}")
                    break  # Solo una señal por ciclo

        save_state(STATE_PATH, portfolio.equity, portfolio.positions)
        time.sleep(SLEEP_SEC)

if __name__ == "__main__":
    main()
