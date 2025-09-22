# -*- coding: utf-8 -*-
"""
cron_run_demo_ohlcv.py
Paper trading con datos en vivo (ccxt/LBank) usando OHLCV 1m:
- Señal: EMA(12/26) + filtro de volatilidad por ATR(14)
- TP/SL en múltiplos de ATR (distintos por modo)
- Simulación con fees y pequeño spread
- Envía notificaciones a Telegram (aperturas/cierres) y resumen final
- Guarda operaciones en operaciones.csv y acumula equity

Variables de entorno clave (con valores por defecto razonables):
- PAPER_START_BALANCE=1000
- CSV_PATH=operaciones.csv
- RUNTIME_SEC=17900            # ~5h por slot
- SLEEP_SEC=20                 # pausa entre iteraciones
- SYMBOLS=BTC/USDT,ETH/USDT,SOL/USDT
- FEE_TAKER=0.001              # 0.1%
- SPREAD_BPS=0.0002            # 0.02%
- TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
- TELEGRAM_EVENT_NOTIF=1       # 1=on, 0=off (mensajes por trade)
"""

import os, csv, time, math, requests, traceback
from datetime import datetime, timezone
import pandas as pd
import ccxt

# ---------- Config ----------
PAPER_START_BALANCE = float(os.getenv("PAPER_START_BALANCE", "1000"))
CSV_PATH   = os.getenv("CSV_PATH", "operaciones.csv")
RUNTIME_SEC = int(os.getenv("RUNTIME_SEC", "17900"))  # ~ 4h 58m
SLEEP_SEC   = float(os.getenv("SLEEP_SEC", "20"))
SYMBOLS = [s.strip() for s in os.getenv("SYMBOLS","BTC/USDT,ETH/USDT,SOL/USDT").split(",") if s.strip()]
TIMEFRAME = os.getenv("TIMEFRAME","1m")

# Riesgo / tamaño por modo (fracción del equity para dimensionar stake base)
RISK = {
    "agresivo":    float(os.getenv("RISK_AGRESIVO","0.05")),
    "moderado":    float(os.getenv("RISK_MODERADO","0.025")),
    "conservador": float(os.getenv("RISK_CONSERVADOR","0.01")),
}
# Multiplicadores ATR para TP/SL por modo (más prudente en conservador)
ATR_MULT = {
    "agresivo":    {"tp": 1.6, "sl": 1.0},
    "moderado":    {"tp": 1.4, "sl": 1.0},
    "conservador": {"tp": 1.2, "sl": 1.0},
}

FEE_TAKER = float(os.getenv("FEE_TAKER","0.001"))
SPREAD_BPS= float(os.getenv("SPREAD_BPS","0.0002"))

TG_TOKEN = os.getenv("TELEGRAM_TOKEN","")
TG_CHAT  = os.getenv("TELEGRAM_CHAT_ID","")
TG_EVENTS = os.getenv("TELEGRAM_EVENT_NOTIF","1") in ("1","true","True","YES","yes")

# ---------- Utils ----------
def utcnow_iso():
    return datetime.now(timezone.utc).isoformat()

def ensure_csv(path):
    if not os.path.exists(path):
        with open(path,"w",newline="",encoding="utf-8") as f:
            csv.writer(f).writerow(["fecha","modo","par","accion","precio","qty","pnl","equity"])

def append_row(row):
    with open(CSV_PATH,"a",newline="",encoding="utf-8") as f:
        csv.writer(f).writerow(row)

def read_df():
    if not os.path.exists(CSV_PATH) or os.path.getsize(CSV_PATH)==0:
        return pd.DataFrame(columns=["fecha","modo","par","accion","precio","qty","pnl","equity"])
    try:
        df = pd.read_csv(CSV_PATH, parse_dates=["fecha"], on_bad_lines="skip", engine="python")
    except Exception:
        df = pd.read_csv(CSV_PATH, on_bad_lines="skip", engine="python")
        if "fecha" in df.columns:
            df["fecha"]=pd.to_datetime(df["fecha"],errors="coerce")
    df.columns=[c.strip().lower() for c in df.columns]
    if "pnl" in df.columns: df["pnl"]=pd.to_numeric(df["pnl"],errors="coerce").fillna(0.0)
    if "equity" in df.columns: df["equity"]=pd.to_numeric(df["equity"],errors="coerce")
    return df.dropna(subset=["fecha"], how="any").sort_values("fecha")

def fmt_money(x, d=2):
    x = float(x); sign = "" if x>=0 else "-"
    return f"{sign}$ {abs(x):.{d}f}"

def tg_send(text:str):
    if not (TG_TOKEN and TG_CHAT): return
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TG_CHAT, "text": text, "parse_mode":"Markdown"}, timeout=15)
    except Exception:
        pass

# ---------- Data feed ----------
class LBankFeed:
    def __init__(self):
        self.c = ccxt.lbank({"enableRateLimit": True})
        self.mk = None
    def load(self):
        if self.mk is None:
            self.mk = self.c.load_markets()
    def valid(self, symbol):
        self.load(); return symbol in self.mk
    def round_price(self, symbol, px):
        self.load(); m=self.mk.get(symbol)
        if not m: return float(px)
        prec = (m.get("precision") or {}).get("price")
        if prec is not None: return float(round(px,int(prec)))
        tick = (m.get("limits") or {}).get("price",{}).get("min")
        if tick: return float(math.floor(px/tick)*tick)
        return float(px)
    def round_amount(self, symbol, amt):
        self.load(); m=self.mk.get(symbol)
        if not m: return float(amt)
        prec = (m.get("precision") or {}).get("amount")
        if prec is not None:
            val=float(round(amt,int(prec)))
            return 0.0 if val<(10**-int(prec)) else val
        step=(m.get("limits") or {}).get("amount",{}).get("min")
        if step: return float(math.floor(amt/step)*step)
        return float(amt)
    def min_notional(self, symbol):
        self.load(); m=self.mk.get(symbol)
        return (m.get("limits") or {}).get("cost",{}).get("min")
    def ticker(self, symbol):
        try:
            t = self.c.fetch_ticker(symbol); time.sleep(0.2)
            return t
        except Exception:
            return None
    def ohlcv(self, symbol, timeframe="1m", limit=150):
        # Trae últimos 'limit' candles
        for _ in range(2):
            try:
                o = self.c.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
                time.sleep(0.2)
                return o
            except Exception:
                time.sleep(1)
        return []

# ---------- Indicadores ----------
def df_from_ohlcv(ohlcv):
    # ohlcv: [ [ts, open, high, low, close, volume], ... ]
    if not ohlcv: return pd.DataFrame(columns=["time","open","high","low","close","volume"])
    d = pd.DataFrame(ohlcv, columns=["time","open","high","low","close","volume"])
    d["time"] = pd.to_datetime(d["time"], unit="ms", utc=True)
    return d

def ema(series, n):
    return series.ewm(span=n, adjust=False).mean()

def atr(df, n=14):
    h,l,c = df["high"], df["low"], df["close"]
    prev_c = c.shift(1)
    tr = pd.concat([ (h-l).abs(), (h-prev_c).abs(), (l-prev_c).abs() ], axis=1).max(axis=1)
    return tr.rolling(n).mean()

# ---------- Estrategia ----------
def pick_symbols(feed:LBankFeed):
    out=[]
    for s in SYMBOLS:
        if feed.valid(s): out.append(s)
        if len(out)>=3: break
    return out or ["BTC/USDT"]

def should_open_long(d: pd.DataFrame) -> bool:
    # Señal: cruce EMA12>EMA26 en la vela cerrada, con filtro de ATR>0
    if len(d) < 50: return False
    d = d.copy()
    d["ema12"] = ema(d["close"], 12)
    d["ema26"] = ema(d["close"], 26)
    d["atr14"] = atr(d, 14)
    # Usar la vela cerrada (penúltima fila)
    i = -2
    if pd.isna(d["ema12"].iloc[i]) or pd.isna(d["ema26"].iloc[i]) or pd.isna(d["atr14"].iloc[i]): 
        return False
    # Cruce alcista reciente y algo de volatilidad
    cross_up = (d["ema12"].iloc[i] > d["ema26"].iloc[i]) and (d["ema12"].iloc[i-1] <= d["ema26"].iloc[i-1])
    vol_ok = d["atr14"].iloc[i] > 0
    return bool(cross_up and vol_ok)

def run_once():
    ensure_csv(CSV_PATH)
    feed = LBankFeed()
    symbols = pick_symbols(feed)
    df_hist = read_df()
    equity = float(df_hist["equity"].iloc[-1]) if ("equity" in df_hist.columns and not df_hist.empty and pd.notna(df_hist["equity"].iloc[-1])) else PAPER_START_BALANCE

    # Posiciones abiertas por (modo, símbolo)
    opens = {}  # (modo, sym) -> dict(entry, qty, tp, sl, t_open)

    t0 = time.time()
    last_bar_time = {s: None for s in symbols}  # para no duplicar señales en misma vela

    while time.time() - t0 < RUNTIME_SEC:
        for sym in symbols:
            try:
                # OHLCV y última barra
                raw = feed.ohlcv(sym, timeframe=TIMEFRAME, limit=150)
                d = df_from_ohlcv(raw)
                if d.empty: continue
                last_ts = d["time"].iloc[-1]
                # Evita procesar varias veces la misma vela cerrada
                if last_bar_time.get(sym) == last_ts:
                    continue
                last_bar_time[sym] = last_ts

                # Señal (penúltima vela)
                signal_long = should_open_long(d)

                # Precio simulación con spread
                tk = feed.ticker(sym)
                if not tk: continue
                bid = tk.get("bid") or tk.get("last") or tk.get("close")
                ask = tk.get("ask") or tk.get("last") or tk.get("close")
                if not (bid and ask): continue
                bid = float(bid) * (1 - SPREAD_BPS)
                ask = float(ask) * (1 + SPREAD_BPS)

                # ATR actual para TP/SL
                d["atr14"] = atr(d,14)
                atr_now = float(d["atr14"].iloc[-2]) if not pd.isna(d["atr14"].iloc[-2]) else None
                if atr_now is None or atr_now <= 0: 
                    continue

                # ——— Gestionar posiciones por modo ———
                for modo, r in RISK.items():
                    key = (modo, sym)
                    # Cierre por TP/SL si hay abierta
                    if key in opens:
                        pos = opens[key]
                        # Marcar precio de salida al bid (vendes)
                        px_exit = feed.round_price(sym, bid)
                        pnl_gross = (px_exit - pos["entry"]) * pos["qty"]
                        fee = (pos["entry"]*pos["qty"] + px_exit*pos["qty"]) * FEE_TAKER
                        pnl = pnl_gross - fee

                        hit_tp = px_exit >= pos["tp"]
                        hit_sl = px_exit <= pos["sl"]
                        timeout = (time.time() - pos["t_open"]) > 3600  # 1h por vela intradía (failsafe)

                        if hit_tp or hit_sl or timeout:
                            equity += pnl
                            append_row([utcnow_iso(), modo, sym, "CERRAR", round(px_exit,6), round(pos["qty"],6), round(pnl,6), round(equity,2)])
                            if TG_EVENTS:
                                res = "✅ TP" if hit_tp else ("❌ SL" if hit_sl else "⏱️ TimeOut")
                                tg_send(f"{res} *{modo}* {sym}\nSalida: {px_exit:.6f}\nPnL: {fmt_money(pnl)}\nEquity: {fmt_money(equity)}")
                            del opens[key]
                        else:
                            # mantener abierta
                            pass

                    # Apertura si no hay posición y hay señal
                    if key not in opens and signal_long:
                        stake_usdt = max(5.0, equity * r * 0.25)  # 25% del riesgo teórico para no sobre-operar
                        px_entry = feed.round_price(sym, ask)
                        qty = stake_usdt / px_entry
                        qty = feed.round_amount(sym, qty)
                        # Respeto de notional mínimo
                        mn = feed.min_notional(sym) or 0.0
                        if mn>0 and qty*px_entry<mn:
                            need = feed.round_amount(sym, mn/px_entry)
                            qty = max(qty, need)
                        if qty <= 0: 
                            continue

                        # Fees compra impactan equity
                        cost = px_entry*qty
                        equity -= cost * (1 + FEE_TAKER)

                        # TP/SL según modo
                        tp = px_entry + ATR_MULT[modo]["tp"] * atr_now
                        sl = px_entry - ATR_MULT[modo]["sl"] * atr_now

                        opens[key] = {"entry": px_entry, "qty": qty, "tp": tp, "sl": sl, "t_open": time.time()}
                        append_row([utcnow_iso(), modo, sym, "ABRIR", round(px_entry,6), round(qty,6), 0.0, round(equity,2)])
                        if TG_EVENTS:
                            tg_send(f"🟢 *ABRIR* {modo} {sym}\nEntrada: {px_entry:.6f}\nTP: {tp:.6f}\nSL: {sl:.6f}\nQty: {qty:.6f}\nEquity: {fmt_money(equity)}")

            except Exception as e:
                # No interrumpir slot por un error puntual
                traceback.print_exc()
                time.sleep(1)

        time.sleep(SLEEP_SEC)

    # Cierre forzado de lo abierto al final del slot
    for key, pos in list(opens.items()):
        sym = key[1]
        tk = feed.ticker(sym)
        last = tk.get("bid") or tk.get("last") if tk else pos["entry"]
        px = feed.round_price(sym, float(last))
        fee = (pos["entry"]*pos["qty"] + px*pos["qty"]) * FEE_TAKER
        pnl = (px - pos["entry"]) * pos["qty"] - fee
        equity += pnl
        append_row([utcnow_iso(), key[0], sym, "CERRAR", round(px,6), round(pos["qty"],6), round(pnl,6), round(equity,2)])
        if TG_EVENTS:
            res = "🟡 Cierre fin de slot"
            tg_send(f"{res} *{key[0]}* {sym}\nSalida: {px:.6f}\nPnL: {fmt_money(pnl)}\nEquity: {fmt_money(equity)}")

    # Resumen final del slot
    dff = read_df()
    total_pnl = float(dff["pnl"].sum()) if "pnl" in dff.columns else 0.0
    ops = len(dff)
    wins = int((dff["pnl"]>0).sum()) if "pnl" in dff.columns else 0
    wr = (wins/ops*100) if ops>0 else 0.0
    # Mejor modo por PnL
    best_mode = ""
    best_pnl = -1e18
    if "modo" in dff.columns and "pnl" in dff.columns:
        by_mode = dff.groupby("modo")["pnl"].sum().sort_values(ascending=False)
        if len(by_mode)>0:
            best_mode = str(by_mode.index[0])
            best_pnl = float(by_mode.iloc[0])

    if TG_TOKEN and TG_CHAT:
        tg_send(f"📊 *Slot DEMO (OHLCV) completado*\nEquity: *{fmt_money(equity)}*\nPNL total: *{fmt_money(total_pnl)}*\nWinrate: *{wr:.2f}%*\nOps: *{ops}*\nMejor modo: *{best_mode}* ({fmt_money(best_pnl)})")

if __name__ == "__main__":
    run_once()
