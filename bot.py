import os
import time
import logging
import schedule
import requests
import pandas as pd
import numpy as np
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from datetime import datetime, timedelta, timezone

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ── Config ────────────────────────────────────────────────────────────────────
API_KEY    = os.environ.get('APCA_API_KEY_ID')
SECRET_KEY = os.environ.get('APCA_API_SECRET_KEY')

# Watchlist — 25 top liquid stocks across all sectors
WATCHLIST = [
    # Tech
    'AAPL', 'MSFT', 'NVDA', 'GOOGL', 'META', 'AMZN', 'TSLA',
    # Finance
    'JPM', 'BAC', 'GS',
    # Healthcare
    'JNJ', 'UNH', 'PFE',
    # Energy
    'XOM', 'CVX',
    # Consumer
    'WMT', 'COST', 'MCD', 'HD',
    # ETFs (broad market)
    'SPY', 'QQQ', 'DIA',
    # Semiconductors
    'AMD', 'INTC', 'AVGO',
]

MAX_POSITIONS  = 3      # Hold at most 3 stocks at once
QTY_PER_TRADE  = 1      # Shares per buy order

# Indicator settings
SHORT_WINDOW = 20
LONG_WINDOW  = 50
TREND_WINDOW = 200
RSI_PERIOD   = 14
RSI_MIN      = 40
RSI_MAX      = 65
RSI_OVERBOUGHT = 75
MACD_FAST, MACD_SLOW, MACD_SIGNAL = 12, 26, 9

# Risk management
STOP_LOSS_PCT   = 0.03
TAKE_PROFIT_PCT = 0.05

# Telegram (optional)
TELEGRAM_TOKEN   = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

# ── Validate ──────────────────────────────────────────────────────────────────
if not API_KEY or not SECRET_KEY:
    logging.error("Set APCA_API_KEY_ID and APCA_API_SECRET_KEY env variables.")
    exit(1)

trading_client = TradingClient(API_KEY, SECRET_KEY, paper=True)
data_client    = StockHistoricalDataClient(API_KEY, SECRET_KEY)


# ── Telegram ──────────────────────────────────────────────────────────────────
def send_telegram(message: str):
    """Send a message via Telegram Bot API."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        url  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        resp = requests.post(
            url,
            json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"},
            timeout=10
        )
        data = resp.json()
        if resp.status_code == 200 and data.get("ok"):
            logging.info("✅ Telegram message sent.")
        else:
            logging.error(f"❌ Telegram error {resp.status_code}: {data.get('description', data)}")
    except requests.exceptions.ConnectionError:
        logging.error("❌ Telegram: No internet connection.")
    except requests.exceptions.Timeout:
        logging.error("❌ Telegram: Request timed out.")
    except Exception as e:
        logging.error(f"❌ Telegram failed: {e}")


def test_telegram():
    """Send a test message to verify Telegram is configured correctly."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logging.warning("⚠️  Telegram not configured. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID.")
        return False
    logging.info("Sending Telegram test message...")
    try:
        url  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        resp = requests.post(
            url,
            json={"chat_id": TELEGRAM_CHAT_ID, "text": "🤖 *Trading Bot* — Test message! Telegram is working ✅", "parse_mode": "Markdown"},
            timeout=10
        )
        data = resp.json()
        if resp.status_code == 200 and data.get("ok"):
            logging.info("✅ Telegram test PASSED — Check your Telegram app!")
            return True
        else:
            logging.error(f"❌ Telegram test FAILED: {data.get('description', data)}")
            logging.error("   → Double-check TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID")
            return False
    except Exception as e:
        logging.error(f"❌ Telegram test error: {e}")
        return False


# ── Indicators ────────────────────────────────────────────────────────────────
def calc_rsi(series, period=14):
    delta    = series.diff()
    gain     = delta.clip(lower=0)
    loss     = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    rs  = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def calc_macd(series, fast=12, slow=26, signal=9):
    ema_fast    = series.ewm(span=fast, adjust=False).mean()
    ema_slow    = series.ewm(span=slow, adjust=False).mean()
    macd_line   = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram   = macd_line - signal_line
    return macd_line, signal_line, histogram


# ── Fetch ALL watchlist data in one batch call ────────────────────────────────
def fetch_all_data(symbols, days=300):
    """
    Fetches historical bars for ALL symbols in a single API call.
    Returns a dict: { symbol -> DataFrame }
    """
    end_time   = datetime.now(timezone.utc) - timedelta(days=1)
    start_time = end_time - timedelta(days=days)

    logging.info(f"Fetching data for {len(symbols)} symbols...")
    req = StockBarsRequest(
        symbol_or_symbols=symbols,
        timeframe=TimeFrame.Day,
        start=start_time,
        end=end_time,
        feed="iex"
    )
    bars = data_client.get_stock_bars(req)

    result = {}
    if bars.data:
        for sym in symbols:
            if sym in bars.data:
                df = bars.df
                # Multi-index: (symbol, timestamp) — extract this symbol
                try:
                    df_sym = df.xs(sym, level='symbol') if 'symbol' in df.index.names else df.loc[sym]
                    result[sym] = df_sym
                except Exception:
                    pass
    return result


# ── Analyze one stock ─────────────────────────────────────────────────────────
def analyze_stock(symbol, df):
    """
    Returns a score dict for the stock.
    Score 0-5 based on how many buy conditions are met.
    Also returns a 'momentum' value for ranking equal-score stocks.
    """
    if df is None or len(df) < TREND_WINDOW:
        return None

    close = df['close']

    sma20  = close.rolling(SHORT_WINDOW).mean()
    sma50  = close.rolling(LONG_WINDOW).mean()
    sma200 = close.rolling(TREND_WINDOW).mean()
    rsi    = calc_rsi(close, RSI_PERIOD)
    macd_line, signal_line, histogram = calc_macd(close, MACD_FAST, MACD_SLOW, MACD_SIGNAL)
    avg_vol   = df['volume'].rolling(SHORT_WINDOW).mean()
    vol_ratio = df['volume'].iloc[-1] / avg_vol.iloc[-1] if avg_vol.iloc[-1] > 0 else 0

    p   = close.iloc[-1]
    s20 = sma20.iloc[-1]
    s50 = sma50.iloc[-1]
    s200= sma200.iloc[-1]
    r   = rsi.iloc[-1]
    m   = macd_line.iloc[-1]
    sig = signal_line.iloc[-1]
    h   = histogram.iloc[-1]

    signals = {
        "SMA20>SMA50"    : s20 > s50,
        "Price>SMA200"   : p  > s200,
        "RSI 40-65"      : RSI_MIN <= r <= RSI_MAX,
        "Volume>avg"     : vol_ratio >= 1.0,
        "MACD bullish"   : m > sig,
    }

    score    = sum(signals.values())
    # Momentum score: composite of RSI position in range + MACD histogram strength
    rsi_score  = (r - RSI_MIN) / (RSI_MAX - RSI_MIN) if RSI_MIN <= r <= RSI_MAX else 0
    momentum   = (rsi_score * 0.5) + (min(h, 0) * -1 + h) * 0.5  # normalize roughly

    sell_signal = s20 < s50 or r > RSI_OVERBOUGHT

    return {
        "symbol"     : symbol,
        "price"      : p,
        "sma20"      : s20,
        "sma50"      : s50,
        "sma200"     : s200,
        "rsi"        : r,
        "macd"       : m,
        "macd_sig"   : sig,
        "vol_ratio"  : vol_ratio,
        "signals"    : signals,
        "score"      : score,
        "momentum"   : momentum,
        "sell_signal": sell_signal,
    }


# ── Print screening table ─────────────────────────────────────────────────────
def print_screen_report(results):
    logging.info("")
    logging.info("╔══════════════════════════════════════════════════════════════╗")
    logging.info("║           MARKET SCREENER REPORT                            ║")
    logging.info("╠══════╦════════╦═══════╦══════════╦══════════╦══════════════╣")
    logging.info("║ Sym  ║ Price  ║ Score ║ RSI      ║ Vol Ratio║ Decision     ║")
    logging.info("╠══════╬════════╬═══════╬══════════╬══════════╬══════════════╣")
    for r in results:
        decision = "🟢 BUY"   if r['score'] == 5 else \
                   "🟡 WATCH" if r['score'] >= 3 else \
                   "🔴 SKIP"
        logging.info(
            f"║ {r['symbol']:<4} ║ ${r['price']:>6.2f} ║  {r['score']}/5  "
            f"║ {r['rsi']:>6.1f}    ║   {r['vol_ratio']:>5.2f}x  ║ {decision:<12} ║"
        )
    logging.info("╚══════╩════════╩═══════╩══════════╩══════════╩══════════════╝")
    logging.info("")


# ── Risk check for open positions ─────────────────────────────────────────────
def check_risk(position):
    pct = float(position.unrealized_plpc)
    if pct <= -STOP_LOSS_PCT:
        return f"🛑 STOP-LOSS at {pct*100:.2f}%"
    if pct >= TAKE_PROFIT_PCT:
        return f"✅ TAKE-PROFIT at {pct*100:.2f}%"
    return None


# ── Main bot cycle ────────────────────────────────────────────────────────────
def run_bot():
    logging.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    logging.info(" Running market screener cycle")
    logging.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    try:
        # ── 1. Get current positions & account info ───────────────────────────
        positions    = trading_client.get_all_positions()
        position_map = {p.symbol: p for p in positions}
        held_symbols = set(position_map.keys())
        account      = trading_client.get_account()
        buying_power = float(account.buying_power)

        logging.info(f"Positions held: {list(held_symbols) or 'None'} | Buying power: ${buying_power:,.2f}")

        # ── 2. Risk check all open positions first ────────────────────────────
        for sym, pos in position_map.items():
            reason = check_risk(pos)
            if reason:
                price = float(pos.current_price)
                pnl   = float(pos.unrealized_pl)
                logging.info(f"{reason} — Closing {sym} @ ${price:.2f} | P&L: ${pnl:+.2f}")
                trading_client.close_position(sym)
                held_symbols.discard(sym)
                send_telegram(
                    f"*Bot Alert* 🤖\n{reason}\n"
                    f"Symbol: `{sym}` @ `${price:.2f}` | P&L: `${pnl:+.2f}`"
                )

        # ── 3. Fetch all market data in one batch ─────────────────────────────
        all_data = fetch_all_data(WATCHLIST, days=300)

        # ── 4. Analyze every stock ────────────────────────────────────────────
        results = []
        for sym in WATCHLIST:
            r = analyze_stock(sym, all_data.get(sym))
            if r:
                results.append(r)

        # Sort: highest score first, then highest momentum
        results.sort(key=lambda x: (x['score'], x['momentum']), reverse=True)
        print_screen_report(results)

        # ── 5. Sell open positions that flipped to SELL signal ─────────────────
        for sym in list(held_symbols):
            r = next((x for x in results if x['symbol'] == sym), None)
            if r and r['sell_signal']:
                pos   = position_map[sym]
                price = float(pos.current_price)
                pnl   = float(pos.unrealized_pl)
                logging.info(f"SELL signal on {sym} — Closing @ ${price:.2f} | P&L: ${pnl:+.2f}")
                trading_client.close_position(sym)
                held_symbols.discard(sym)
                send_telegram(
                    f"*Bot Alert* 🤖\n📉 *SELL* `{sym}` — signal reversed\n"
                    f"Price: `${price:.2f}` | P&L: `${pnl:+.2f}`"
                )

        # ── 6. Buy top-scoring stocks (score == 5, not already held) ──────────
        slots_available = MAX_POSITIONS - len(held_symbols)
        buy_candidates  = [r for r in results if r['score'] == 5 and r['symbol'] not in held_symbols]

        if not buy_candidates:
            logging.info("No stocks passed all 5 filters this cycle. Waiting for better opportunity...")
        elif slots_available <= 0:
            logging.info(f"Portfolio full ({MAX_POSITIONS} positions). Holding current positions.")
        else:
            for candidate in buy_candidates[:slots_available]:
                sym   = candidate['symbol']
                price = candidate['price']

                # Safety: ensure enough buying power
                if buying_power < price * QTY_PER_TRADE:
                    logging.warning(f"Not enough buying power for {sym} (${price:.2f}). Skipping.")
                    continue

                logging.info(f"🟢 BUY {sym} @ ${price:.2f} | Score: 5/5 | RSI: {candidate['rsi']:.1f}")
                order = MarketOrderRequest(
                    symbol=sym, qty=QTY_PER_TRADE,
                    side=OrderSide.BUY, time_in_force=TimeInForce.GTC
                )
                trading_client.submit_order(order_data=order)
                buying_power -= price * QTY_PER_TRADE
                held_symbols.add(sym)
                send_telegram(
                    f"*Bot Alert* 🤖\n📈 *BUY* `{sym}` — Score 5/5 ✅\n"
                    f"Price: `${price:.2f}` | RSI: `{candidate['rsi']:.1f}`\n"
                    f"Vol: `{candidate['vol_ratio']:.2f}x` avg | MACD bullish ✅"
                )

        # ── 7. Summary ────────────────────────────────────────────────────────
        logging.info(f"Cycle complete. Holding: {list(held_symbols) or 'Nothing'}")
        logging.info("Next run in 5 minutes.")

    except Exception as e:
        logging.error(f"Bot error: {e}", exc_info=True)


# ── Entry ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.info("══════════════════════════════════════════════")
    logging.info("  MULTI-STOCK SCREENER BOT  (Paper Trading)  ")
    logging.info("══════════════════════════════════════════════")
    logging.info(f"Watchlist  : {len(WATCHLIST)} stocks")
    logging.info(f"Max Positions: {MAX_POSITIONS}")
    logging.info(f"Buy Filter : Score must be 5/5")
    logging.info(f"Stop-Loss  : {STOP_LOSS_PCT*100:.0f}%  |  Take-Profit: {TAKE_PROFIT_PCT*100:.0f}%")
    logging.info("══════════════════════════════════════════════")

    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        logging.info("Telegram: ENABLED — testing connection...")
        test_telegram()
    else:
        logging.info("Telegram: DISABLED — set TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID to enable")


    run_bot()

    schedule.every(5).minutes.do(run_bot)
    logging.info("Scheduled every 5 minutes. Running...")

    while True:
        schedule.run_pending()
        time.sleep(60)
