# 🤖 Algorithmic Trading Bot

An automated stock market screener and trading bot built with Python and [Alpaca](https://alpaca.markets/) (Paper Trading).

## Features
- 📊 **Scans 25 top stocks** every 5 minutes
- 🧠 **5-factor analysis** before every buy (SMA crossover, SMA200 trend, RSI, MACD, Volume)
- 🛡️ **Risk management** — automatic stop-loss (-3%) and take-profit (+5%)
- 📱 **Telegram alerts** — get notified on your phone for every trade
- 📈 **Backtesting** — test the strategy on 3 years of historical data
- 🖥️ **Live dashboard** — Streamlit web UI with charts and portfolio stats

## Project Structure
```
trading_bot/
├── bot.py            # Main screener bot (runs every 5 min)
├── backtest.py       # Backtesting engine (3 years of history)
├── dashboard.py      # Streamlit live dashboard
├── requirements.txt  # Python dependencies
├── .env.example      # Environment variable template
└── README.md
```

## Quick Start

### 1. Clone the repo
```bash
git clone https://github.com/YOUR_USERNAME/trading-bot.git
cd trading-bot
```

### 2. Create a virtual environment
```bash
python -m venv venv

# Windows
.\venv\Scripts\activate

# Mac/Linux
source venv/bin/activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Set environment variables
```bash
# Windows PowerShell
$env:APCA_API_KEY_ID="your_alpaca_key"
$env:APCA_API_SECRET_KEY="your_alpaca_secret"

# Optional: Telegram alerts
$env:TELEGRAM_BOT_TOKEN="your_telegram_bot_token"
$env:TELEGRAM_CHAT_ID="your_telegram_chat_id"
```

### 5. Run the bot
```bash
.\venv\Scripts\python bot.py
```

## Other Commands

```bash
# Run backtesting (3 years of SPY history)
.\venv\Scripts\python backtest.py

# Launch live dashboard (opens in browser)
.\venv\Scripts\streamlit run dashboard.py
```

## Strategy — 5-Factor Buy Filter
The bot only buys when **ALL 5 signals** are green:

| Signal | Condition |
|---|---|
| ✅ SMA Crossover | 20-day SMA > 50-day SMA |
| ✅ Long-term Trend | Price above 200-day SMA |
| ✅ RSI | Between 40–65 (healthy momentum) |
| ✅ Volume | Above 20-day average |
| ✅ MACD | MACD line above Signal line |

## Risk Management
- **Stop-loss:** Auto-sell if position drops **-3%**
- **Take-profit:** Auto-sell if position gains **+5%**
- **Max positions:** 3 stocks held at once

## Watchlist (25 stocks)
`AAPL` `MSFT` `NVDA` `GOOGL` `META` `AMZN` `TSLA` `JPM` `BAC` `GS`
`JNJ` `UNH` `PFE` `XOM` `CVX` `WMT` `COST` `MCD` `HD` `SPY`
`QQQ` `DIA` `AMD` `INTC` `AVGO`

## Getting API Keys

### Alpaca (Free Paper Trading)
1. Sign up at [alpaca.markets](https://alpaca.markets/)
2. Go to **Account → API Keys → Generate New Key** (Paper Trading)

### Telegram Alerts (Optional)
1. Message **@BotFather** on Telegram → `/newbot`
2. Get your Chat ID from **@userinfobot**

## ⚠️ Disclaimer
This bot is for **educational purposes only**. Always test with paper trading before using real money. Trading involves significant financial risk.
