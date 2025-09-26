# dashboard.py
from flask import Flask, render_template, jsonify
import pandas as pd
import json
import os
from datetime import datetime, timedelta, timezone
import pytz

app = Flask(__name__)

STATE_FILE = "paper_state.json"
CSV_FILE = "operaciones_zaffex.csv"

def parse_timestamp(ts_str):
    """Convierte string ISO a datetime con manejo de zonas horarias"""
    if pd.isna(ts_str) or ts_str == "":
        return None
    try:
        # Intentar parsear como ISO format
        dt = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except:
        return None

def get_period_stats(df, start_date, end_date=None):
    """Calcula estadísticas para un período específico"""
    if end_date is None:
        end_date = datetime.now(timezone.utc)
    
    # Filtrar operaciones de cierre en el período
    closed = df[df['type'] == 'CLOSE'].copy()
    if closed.empty:
        return {"total": 0, "wins": 0, "losses": 0, "win_rate": 0.0, "pnl_total": 0.0}
    
    # Convertir timestamps
    closed['trade_time'] = closed['timestamp'].apply(parse_timestamp)
    closed = closed.dropna(subset=['trade_time'])
    
    # Filtrar por período
    mask = (closed['trade_time'] >= start_date) & (closed['trade_time'] <= end_date)
    period_trades = closed[mask]
    
    if period_trades.empty:
        return {"total": 0, "wins": 0, "losses": 0, "win_rate": 0.0, "pnl_total": 0.0}
    
    total = len(period_trades)
    wins = len(period_trades[period_trades['pnl'] > 0])
    losses = total - wins
    win_rate = (wins / total * 100) if total > 0 else 0.0
    pnl_total = period_trades['pnl'].sum()
    
    return {
        "total": int(total),
        "wins": int(wins),
        "losses": int(losses),
        "win_rate": round(win_rate, 1),
        "pnl_total": round(float(pnl_total), 6)
    }

def get_all_stats():
    """Obtiene estadísticas para diario, semanal y mensual"""
    if not os.path.exists(CSV_FILE):
        empty = {"total": 0, "wins": 0, "losses": 0, "win_rate": 0.0, "pnl_total": 0.0}
        return {"daily": empty, "weekly": empty, "monthly": empty}
    
    try:
        df = pd.read_csv(CSV_FILE, encoding='utf-8')
        now = datetime.now(timezone.utc)
        
        # Diario: últimas 24 horas
        daily_start = now - timedelta(hours=24)
        daily_stats = get_period_stats(df, daily_start, now)
        
        # Semanal: últimos 7 días
        weekly_start = now - timedelta(days=7)
        weekly_stats = get_period_stats(df, weekly_start, now)
        
        # Mensual: últimos 30 días
        monthly_start = now - timedelta(days=30)
        monthly_stats = get_period_stats(df, monthly_start, now)
        
        return {
            "daily": daily_stats,
            "weekly": weekly_stats,
            "monthly": monthly_stats
        }
    except Exception as e:
        print(f"Error en get_all_stats: {e}")
        empty = {"total": 0, "wins": 0, "losses": 0, "win_rate": 0.0, "pnl_total": 0.0}
        return {"daily": empty, "weekly": empty, "monthly": empty}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/state')
def get_state():
    # Cargar estado del portfolio
    equity = 1000.0
    positions = []
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                data = json.load(f)
                equity = data.get("equity", equity)
                positions = data.get("positions", [])
        except:
            pass
    
    # Contar posiciones por modo
    mode_counts = {"agresivo": 0, "moderado": 0, "conservador": 0}
    for p in positions:
        mode = p.get("mode", "moderado")
        if mode in mode_counts:
            mode_counts[mode] += 1
    
    # Obtener estadísticas de períodos
    period_stats = get_all_stats()
    
    return jsonify({
        "equity": round(equity, 2),
        "positions": len(positions),
        "by_mode": mode_counts,
        "period_stats": period_stats
    })

@app.route('/api/trades')
def get_trades():
    if not os.path.exists(CSV_FILE):
        return jsonify([])
    
    try:
        df = pd.read_csv(CSV_FILE, encoding='utf-8')
        closed = df[df['type'] == 'CLOSE'].tail(10)
        trades = []
        for _, row in closed.iterrows():
            trades.append({
                "symbol": row.get("symbol", ""),
                "mode": row.get("mode", ""),
                "pnl": float(row.get("pnl", 0)),
                "reason": row.get("reason", ""),
                "equity": float(row.get("equity", 0))
            })
        return jsonify(trades[::-1])
    except:
        return jsonify([])

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)