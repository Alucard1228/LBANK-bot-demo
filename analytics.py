# -*- coding: utf-8 -*-
import pandas as pd
import numpy as np
from typing import Tuple, Dict, Optional
from dotenv import dotenv_values

COLUMNS = ["ts","event","id","symbol","mode","side","entry_px","sl_px","qty","exit_px","pnl","pnl_r","reason","equity"]

def load_env_balance(env_path: str = ".env") -> float:
    try:
        env = dotenv_values(env_path)
        return float(env.get("PAPER_START_BALANCE", 1000))
    except Exception:
        return 1000.0

def load_trades(csv_path: str, start_balance: Optional[float] = None) -> Tuple[pd.DataFrame, pd.DataFrame]:
    df = pd.read_csv(csv_path)
    if df.empty:
        # estructura vacía
        df = pd.DataFrame(columns=COLUMNS)
    else:
        # normaliza columnas conocidas (si falta alguna la añade)
        for c in COLUMNS:
            if c not in df.columns:
                df[c] = np.nan
        df = df[COLUMNS]

    # tipos
    numeric_cols = ["entry_px","sl_px","qty","exit_px","pnl","pnl_r","equity"]
    for c in numeric_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["ts"] = pd.to_datetime(df["ts"], unit="s", utc=True, errors="coerce")
    df = df.sort_values("ts").reset_index(drop=True)

    # Unir OPEN y CLOSE por id
    opens = df[df["event"]=="OPEN"].copy()
    closes = df[df["event"]=="CLOSE"].copy()

    opens = opens.rename(columns={
        "ts":"open_ts","symbol":"open_symbol","mode":"open_mode","side":"open_side",
        "entry_px":"open_entry_px","sl_px":"open_sl_px","qty":"open_qty"
    })
    closes = closes.rename(columns={
        "ts":"close_ts","exit_px":"close_exit_px","pnl":"close_pnl",
        "pnl_r":"close_pnl_r","reason":"close_reason","equity":"close_equity"
    })

    trades = pd.merge(
        opens[["id","open_ts","open_symbol","open_mode","open_side","open_entry_px","open_sl_px","open_qty"]],
        closes[["id","close_ts","close_exit_px","close_pnl","close_pnl_r","close_reason","close_equity"]],
        on="id", how="left"
    ).sort_values("open_ts").reset_index(drop=True)

    # equity preferida (del logger); si falta, reconstruye
    if start_balance is None:
        start_balance = load_env_balance()

    trades["close_pnl"].fillna(0.0, inplace=True)
    trades["pnl_cumsum"] = trades["close_pnl"].cumsum()
    trades["equity_calc"] = start_balance + trades["pnl_cumsum"]
    trades["equity"] = trades["close_equity"].fillna(trades["equity_calc"])

    # outcomes
    trades["is_win"] = (trades["close_pnl"] >= 0).astype(int)
    trades["R"] = trades["close_pnl_r"]

    return df, trades

def stats_overall(trades: pd.DataFrame, start_balance: float) -> Dict[str, float]:
    t = trades.dropna(subset=["close_ts"])  # cerradas
    n = len(t)
    wins = int((t["close_pnl"] >= 0).sum())
    losses = n - wins
    wr = (wins / n * 100.0) if n > 0 else 0.0
    pnl_total = t["close_pnl"].sum() if n>0 else 0.0
    avg_r = t["R"].mean() if "R" in t.columns and n>0 else 0.0
    best = t["close_pnl"].max() if n>0 else 0.0
    worst = t["close_pnl"].min() if n>0 else 0.0

    # equity, dd, profit factor, expectancy
    eq = t["equity"].dropna()
    last_eq = eq.iloc[-1] if len(eq) else start_balance
    ret = eq.pct_change().fillna(0.0)
    # drawdown
    if len(eq):
        peak = eq.cummax()
        dd = (eq/peak - 1.0)
        max_dd = dd.min()  # negativo
    else:
        max_dd = 0.0

    gross_win = t.loc[t["close_pnl"]>0,"close_pnl"].sum()
    gross_loss = -t.loc[t["close_pnl"]<0,"close_pnl"].sum()
    profit_factor = (gross_win / gross_loss) if gross_loss>0 else np.nan
    expectancy = (t["close_pnl"].mean()) if n>0 else 0.0

    return dict(
        trades=n, wins=wins, losses=losses, winrate=wr,
        pnl_total=pnl_total, avg_r=avg_r, best=best, worst=worst,
        last_equity=last_eq, max_drawdown=max_dd, profit_factor=profit_factor, expectancy=expectancy
    )

def table_breakdowns(trades: pd.DataFrame):
    t = trades.dropna(subset=["close_ts"])
    if t.empty:
        return (pd.DataFrame(), pd.DataFrame(), pd.DataFrame())
    # por símbolo
    by_sym = t.groupby("open_symbol").agg(
        trades=("id","count"),
        wr=("is_win","mean"),
        pnl=("close_pnl","sum"),
        avgR=("R","mean")
    ).sort_values("pnl", ascending=False)
    by_sym["wr"] = (by_sym["wr"]*100).round(1); by_sym = by_sym.drop(columns=["wr"]).rename(columns={"wr":"winrate(%)"})

    # por perfil (modo)
    by_mode = t.groupby("open_mode").agg(
        trades=("id","count"),
        wr=("is_win","mean"),
        pnl=("close_pnl","sum"),
        avgR=("R","mean")
    ).sort_values("pnl", ascending=False)
    by_mode["wr"] = (by_mode["wr"]*100).round(1); by_mode = by_mode.drop(columns=["wr"]).rename(columns={"wr":"winrate(%)"})

    # por día
    t["date"] = t["close_ts"].dt.tz_convert(None).dt.date
    by_day = t.groupby("date").agg(
        trades=("id","count"),
        wr=("is_win","mean"),
        pnl=("close_pnl","sum")
    ).reset_index()
    by_day["winrate(%)"] = (by_day["wr"]*100).round(1); by_day = by_day.drop(columns=["wr"])

    return by_sym, by_mode, by_day

def equity_and_drawdown(trades: pd.DataFrame, start_balance: float):
    t = trades.dropna(subset=["close_ts"]).copy()
    if t.empty:
        return pd.DataFrame(), pd.DataFrame()
    eq = t[["close_ts","equity"]].dropna().rename(columns={"close_ts":"ts"})
    eq = eq.set_index("ts").sort_index()
    peak = eq["equity"].cummax()
    dd = (eq["equity"]/peak - 1.0)
    return eq, dd.to_frame("drawdown")

def calendar_returns(trades: pd.DataFrame) -> pd.DataFrame:
    t = trades.dropna(subset=["close_ts"]).copy()
    if t.empty:
        return pd.DataFrame()
    t["date"] = t["close_ts"].dt.tz_convert(None).dt.date
    daily = t.groupby("date")["close_pnl"].sum().reset_index()
    daily["ret"] = daily["close_pnl"]
    daily["date"] = pd.to_datetime(daily["date"])
    daily["year"] = daily["date"].dt.year
    daily["month"] = daily["date"].dt.strftime("%b")
    daily["day"] = daily["date"].dt.day
    return daily

def rolling_metrics(trades: pd.DataFrame, window: int = 20) -> pd.DataFrame:
    t = trades.dropna(subset=["close_ts"]).copy()
    if t.empty: return pd.DataFrame()
    t = t.sort_values("close_ts")
    t["win"] = (t["close_pnl"]>=0).astype(int)
    t["wr_roll"] = t["win"].rolling(window).mean()*100.0
    t["pnl_roll"] = t["close_pnl"].rolling(window).sum()
    t["R_roll"] = t["R"].rolling(window).mean()
    return t[["close_ts","wr_roll","pnl_roll","R_roll"]]
