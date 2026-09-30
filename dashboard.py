import os
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from alpaca.trading.client import TradingClient
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from datetime import datetime, timedelta, timezone
import time

st.set_page_config(page_title="Trading Bot Dashboard", page_icon="📈", layout="wide")

API_KEY = os.environ.get('APCA_API_KEY_ID')
SECRET_KEY = os.environ.get('APCA_API_SECRET_KEY')
SYMBOL = 'SPY'
SHORT_WINDOW = 20
LONG_WINDOW = 50

if not API_KEY or not SECRET_KEY:
    st.error("API keys not found. Set APCA_API_KEY_ID and APCA_API_SECRET_KEY environment variables, then restart.")
    st.stop()

@st.cache_resource
def get_clients():
    trading = TradingClient(API_KEY, SECRET_KEY, paper=True)
    data = StockHistoricalDataClient(API_KEY, SECRET_KEY)
    return trading, data

trading_client, data_client = get_clients()

@st.cache_data(ttl=60)
def get_portfolio():
    account = trading_client.get_account()
    return account

@st.cache_data(ttl=60)
def get_positions():
    return trading_client.get_all_positions()

@st.cache_data(ttl=60)
def get_orders():
    from alpaca.trading.requests import GetOrdersRequest
    from alpaca.trading.enums import QueryOrderStatus
    req = GetOrdersRequest(status=QueryOrderStatus.ALL, limit=20)
    return trading_client.get_orders(filter=req)

@st.cache_data(ttl=300)
def get_price_data(symbol, days=120):
    end_time = datetime.now(timezone.utc) - timedelta(days=1)
    start_time = end_time - timedelta(days=days)
    req = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame.Day,
        start=start_time,
        end=end_time,
        feed="iex"
    )
    bars = data_client.get_stock_bars(req)
    if bars.data and symbol in bars.data:
        df = bars.df.reset_index(level=0, drop=True)
        df['SMA20'] = df['close'].rolling(SHORT_WINDOW).mean()
        df['SMA50'] = df['close'].rolling(LONG_WINDOW).mean()
        return df
    return pd.DataFrame()

# --- UI ---
st.title("📈 Algorithmic Trading Bot Dashboard")
st.caption(f"Paper Trading | Strategy: SMA {SHORT_WINDOW}/{LONG_WINDOW} Crossover | Symbol: {SYMBOL}")

if st.button("🔄 Refresh"):
    st.cache_data.clear()
    st.rerun()

# Portfolio Metrics
try:
    account = get_portfolio()
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("💰 Portfolio Value", f"${float(account.portfolio_value):,.2f}")
    col2.metric("💵 Cash", f"${float(account.cash):,.2f}")
    col3.metric("📊 Buying Power", f"${float(account.buying_power):,.2f}")
    equity_change = float(account.portfolio_value) - float(account.last_equity)
    col4.metric("📅 Daily P&L", f"${equity_change:,.2f}", delta=f"{equity_change:+.2f}")
except Exception as e:
    st.error(f"Error loading account: {e}")

st.divider()

# Price Chart with SMAs
col_chart, col_positions = st.columns([2, 1])

with col_chart:
    st.subheader(f"📉 {SYMBOL} Price + SMA Signals")
    try:
        df = get_price_data(SYMBOL)
        if not df.empty:
            fig = make_subplots(rows=2, cols=1, row_heights=[0.75, 0.25], shared_xaxes=True, vertical_spacing=0.05)
            fig.add_trace(go.Candlestick(x=df.index, open=df['open'], high=df['high'], low=df['low'], close=df['close'], name='Price'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['SMA20'], name=f'SMA {SHORT_WINDOW}', line=dict(color='orange', width=1.5)), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['SMA50'], name=f'SMA {LONG_WINDOW}', line=dict(color='blue', width=1.5)), row=1, col=1)
            fig.add_trace(go.Bar(x=df.index, y=df['volume'], name='Volume', marker_color='lightblue'), row=2, col=1)
            fig.update_layout(height=500, xaxis_rangeslider_visible=False, template='plotly_dark', showlegend=True)
            st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.error(f"Error loading chart: {e}")

with col_positions:
    st.subheader("📌 Current Positions")
    try:
        positions = get_positions()
        if positions:
            for p in positions:
                pnl = float(p.unrealized_pl)
                st.metric(label=f"{p.symbol} ({p.qty} shares)", value=f"${float(p.market_value):,.2f}", delta=f"P&L: ${pnl:+.2f}")
        else:
            st.info("No open positions.")
    except Exception as e:
        st.error(f"Error loading positions: {e}")

    st.subheader("🕐 Recent Orders")
    try:
        orders = get_orders()
        if orders:
            order_data = [{'Symbol': o.symbol, 'Side': o.side.value.upper(), 'Qty': o.qty, 'Status': o.status.value, 'Time': str(o.created_at)[:16]} for o in orders[:10]]
            st.dataframe(pd.DataFrame(order_data), use_container_width=True, hide_index=True)
        else:
            st.info("No recent orders.")
    except Exception as e:
        st.error(f"Error loading orders: {e}")

st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Auto-refreshes every 60s")
time.sleep(1)
