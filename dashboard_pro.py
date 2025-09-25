# dashboard_final.py
# Dashboard minimalista + funcional para tu bot LBANK
import os
import json
import pandas as pd
from datetime import datetime, timezone
from dotenv import load_dotenv
import streamlit as st
import plotly.graph_objects as go

load_dotenv()

CSV_PATH = os.getenv("CSV_PATH", "operaciones.csv")
STATE_PATH = "paper_state.json"
try:
    START_BALANCE = float(os.getenv("PAPER_START_BALANCE", "1000"))
except:
    START_BALANCE = 1000.0

# Estilo CSS: alto contraste, fondo blanco, texto oscuro
st.set_page_config(page_title="Mi Bot — Trading Dashboard", layout="wide")
st.markdown("""
<style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .block-container {
        padding-top: 1.2rem;
        padding-bottom: 1.2rem;
        max-width: 1200px;
        margin: 0 auto;
    }
    .metric-card {
        background: white;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 20px;
        text-align: center;
        box-shadow: 0 2px 8px rgba(0,0,0,0.06);
        margin-bottom: 16px;
    }
    .metric-title {
        font-size: 1.1rem;
        font-weight: 600;
        color: #475569;
        margin-bottom: 8px;
    }
    .metric-value {
        font-size: 1.8rem;
        font-weight: 700;
        color: #0f172a;
    }
    .metric-profit { color: #10b981 !important; }
    .metric-loss { color: #ef4444 !important; }
    h1 {
        text-align: center;
        font-weight: 700;
        color: #0f172a;
        margin-bottom: 1.8rem;
        font-size: 1.8rem;
    }
    .section-title {
        font-weight: 600;
        color: #334155;
        margin-top: 1.5rem;
        margin-bottom: 1rem;
    }
    .open-position {
        background: #f8fafc;
        border-left: 4px solid #4f46e5;
        padding: 12px;
        border-radius: 0 8px 8px 0;
        margin-bottom: 8px;
    }
    .footer-note {
        text-align: center;
        color: #64748b;
        font-size: 0.85rem;
        margin-top: 2rem;
    }
</style>
""", unsafe_allow_html=True)

# === CARGA DE DATOS ===

@st.cache_data(ttl=15)
def load_trades_and_state(csv_path, state_path):
    # Cargar CSV
    if os.path.exists(csv_path):
        try:
            df = pd.read_csv(csv_path)
            df = df.rename(columns={c: c.lower().strip() for c in df.columns})
        except:
            df = pd.DataFrame()
    else:
        df = pd.DataFrame()

    # Cargar estado (posiciones abiertas)
    equity = START_BALANCE
    open_positions = []
    if os.path.exists(state_path):
        try:
            with open(state_path, "r") as f:
                state = json.load(f)
                equity = float(state.get("equity", START_BALANCE))
                open_positions = state.get("positions", [])
        except:
            pass

    return df, equity, open_positions

# Botón de refresco manual
if st.button("🔄 Refrescar datos"):
    st.cache_data.clear()
    st.rerun()

df, current_equity, open_positions = load_trades_and_state(CSV_PATH, STATE_PATH)

# === PROCESAMIENTO DE OPERACIONES CERRADAS ===
closed_trades = pd.DataFrame()
if not df.empty:
    opens = df[df["event"] == "OPEN"].copy()
    closes = df[df["event"] == "CLOSE"].copy()
    if not opens.empty and not closes.empty:
        trades = pd.merge(opens, closes, on="id", suffixes=("", "_close"), how="inner")
        trades["pnl"] = pd.to_numeric(trades.get("pnl_close", trades.get("pnl", 0)), errors="coerce").fillna(0)
        trades["close_ts"] = pd.to_datetime(trades["ts_close"], unit="s", utc=True)
        trades = trades.sort_values("close_ts")
        closed_trades = trades

# === MÉTRICAS ===
total_closed = len(closed_trades)
wins = len(closed_trades[closed_trades["pnl"] > 0]) if not closed_trades.empty else 0
losses = total_closed - wins
win_rate = (wins / total_closed * 100) if total_closed > 0 else 0
pnl_total = float(closed_trades["pnl"].sum()) if not closed_trades.empty else 0.0

# Días activos (días con al menos 1 operación cerrada)
active_days = 0
if not closed_trades.empty:
    closed_trades["date"] = closed_trades["close_ts"].dt.date
    active_days = closed_trades["date"].nunique()

# === INTERFAZ ===
st.title("📊 Mi Bot de Trading")

# Tarjetas superiores
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">Equity Actual</div>
        <div class="metric-value">${current_equity:.2f}</div>
    </div>
    """, unsafe_allow_html=True)

with col2:
    profit_class = "metric-profit" if pnl_total >= 0 else "metric-loss"
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">P&L Total</div>
        <div class="metric-value {profit_class}">${pnl_total:.2f}</div>
    </div>
    """, unsafe_allow_html=True)

with col3:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">Operaciones</div>
        <div class="metric-value">{total_closed}</div>
    </div>
    """, unsafe_allow_html=True)

with col4:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">Win Rate</div>
        <div class="metric-value" style="color: #4f46e5;">{win_rate:.1f}%</div>
    </div>
    """, unsafe_allow_html=True)

# Gráfico de equity (solo operaciones cerradas)
st.markdown('<div class="section-title">Curva de Equity</div>', unsafe_allow_html=True)
if not closed_trades.empty:
    equity_series = START_BALANCE + closed_trades["pnl"].cumsum()
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=closed_trades["close_ts"],
        y=equity_series,
        mode='lines',
        line=dict(color='#3b82f6', width=2.5),
        fill='tozeroy',
        fillcolor='rgba(59, 130, 246, 0.1)'
    ))
    fig.update_layout(
        height=300,
        margin=dict(l=10, r=10, t=20, b=20),
        xaxis_title="",
        yaxis_title="",
        showlegend=False,
        plot_bgcolor='white',
        paper_bgcolor='white',
        xaxis=dict(showgrid=True, gridcolor='#f1f5f9'),
        yaxis=dict(showgrid=True, gridcolor='#f1f5f9', tickprefix="$")
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("No hay operaciones cerradas aún.")

# Posiciones abiertas
st.markdown('<div class="section-title">Posiciones Abiertas ({})</div>'.format(len(open_positions)), unsafe_allow_html=True)
if open_positions:
    for pos in open_positions:
        symbol = pos.get("symbol", "—")
        side = pos.get("side", "—").upper()
        entry = pos.get("entry", 0)
        sl = pos.get("sl", 0)
        tp = pos.get("tp", 0)
        st.markdown(f"""
        <div class="open-position">
            <strong>{symbol}</strong> • {side} • Entry: ${entry:.2f} • SL: ${sl:.2f} • TP: ${tp:.2f}
        </div>
        """, unsafe_allow_html=True)
else:
    st.info("No hay posiciones abiertas.")

# Estadísticas adicionales
st.markdown('<div class="section-title">Estadísticas</div>', unsafe_allow_html=True)
st.write(f"**Días activos**: {active_days}")
st.write(f"**Balance inicial**: ${START_BALANCE:.2f}")

# Pie de página
st.markdown('<div class="footer-note">Dashboard de trading • Datos actualizados en tiempo real</div>', unsafe_allow_html=True)