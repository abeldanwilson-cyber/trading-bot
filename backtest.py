import os
import pandas as pd
import numpy as np
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from datetime import datetime, timedelta, timezone

# Config
API_KEY = os.environ.get('APCA_API_KEY_ID')
SECRET_KEY = os.environ.get('APCA_API_SECRET_KEY')
SYMBOL = 'SPY'
SHORT_WINDOW = 20
LONG_WINDOW = 50
INITIAL_CAPITAL = 100_000.0
QTY = 10  # shares per trade for backtest

if not API_KEY or not SECRET_KEY:
    print("ERROR: Set APCA_API_KEY_ID and APCA_API_SECRET_KEY environment variables.")
    exit(1)

data_client = StockHistoricalDataClient(API_KEY, SECRET_KEY)

def fetch_history(symbol, years=3):
    end_time = datetime.now(timezone.utc) - timedelta(days=1)
    start_time = end_time - timedelta(days=365 * years)
    req = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame.Day,
        start=start_time,
        end=end_time,
        feed="iex"
    )
    print(f"Fetching {years} years of {symbol} data...")
    bars = data_client.get_stock_bars(req)
    if bars.data and symbol in bars.data:
        df = bars.df.reset_index(level=0, drop=True)
        return df
    else:
        print("No data returned.")
        return pd.DataFrame()

def run_backtest(df):
    df = df.copy()
    df['SMA_Short'] = df['close'].rolling(SHORT_WINDOW).mean()
    df['SMA_Long'] = df['close'].rolling(LONG_WINDOW).mean()
    df.dropna(inplace=True)

    capital = INITIAL_CAPITAL
    position = 0  # shares held
    entry_price = 0.0
    trades = []
    portfolio_values = []

    for i, (idx, row) in enumerate(df.iterrows()):
        price = row['close']
        signal = 1 if row['SMA_Short'] > row['SMA_Long'] else -1

        if signal == 1 and position == 0 and capital >= price * QTY:
            # BUY
            position = QTY
            entry_price = price
            capital -= price * QTY
            trades.append({'date': idx, 'action': 'BUY', 'price': price, 'shares': QTY})

        elif signal == -1 and position > 0:
            # SELL
            capital += price * position
            pnl = (price - entry_price) * position
            trades.append({'date': idx, 'action': 'SELL', 'price': price, 'shares': position, 'pnl': pnl})
            position = 0
            entry_price = 0.0

        portfolio_values.append(capital + position * price)

    # Close any open position at end
    if position > 0:
        last_price = df['close'].iloc[-1]
        capital += last_price * position
        pnl = (last_price - entry_price) * position
        trades.append({'date': df.index[-1], 'action': 'SELL (final)', 'price': last_price, 'shares': position, 'pnl': pnl})
        portfolio_values[-1] = capital

    return pd.DataFrame(trades), pd.Series(portfolio_values, index=df.index)

def calc_metrics(portfolio_series, trades_df):
    total_return = (portfolio_series.iloc[-1] - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100
    daily_returns = portfolio_series.pct_change().dropna()
    sharpe = daily_returns.mean() / daily_returns.std() * np.sqrt(252) if daily_returns.std() != 0 else 0
    rolling_max = portfolio_series.cummax()
    drawdown = (portfolio_series - rolling_max) / rolling_max
    max_drawdown = drawdown.min() * 100

    sell_trades = trades_df[trades_df['action'].str.startswith('SELL')]
    wins = sell_trades[sell_trades['pnl'] > 0] if 'pnl' in sell_trades.columns else pd.DataFrame()
    win_rate = len(wins) / len(sell_trades) * 100 if len(sell_trades) > 0 else 0
    total_pnl = sell_trades['pnl'].sum() if 'pnl' in sell_trades.columns else 0

    return {
        'Total Return': f"{total_return:.2f}%",
        'Final Portfolio Value': f"${portfolio_series.iloc[-1]:,.2f}",
        'Total P&L': f"${total_pnl:,.2f}",
        'Sharpe Ratio': f"{sharpe:.2f}",
        'Max Drawdown': f"{max_drawdown:.2f}%",
        'Total Trades': len(trades_df),
        'Win Rate': f"{win_rate:.1f}%"
    }

if __name__ == '__main__':
    df = fetch_history(SYMBOL, years=3)
    if df.empty:
        exit(1)

    trades_df, portfolio = run_backtest(df)

    print("\n" + "="*50)
    print(f"  BACKTEST RESULTS: SMA {SHORT_WINDOW}/{LONG_WINDOW} on {SYMBOL}")
    print("="*50)
    metrics = calc_metrics(portfolio, trades_df)
    for k, v in metrics.items():
        print(f"  {k:<25} {v}")
    print("="*50)

    trades_df.to_csv('backtest_results.csv', index=False)
    print(f"\nTrade log saved to backtest_results.csv")
    print(f"\nLast 5 trades:")
    print(trades_df.tail())
