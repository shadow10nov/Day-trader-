import os
import time
import datetime
import pytz
import yfinance as yf
import pandas as pd
import requests

# ----------------- CONFIGURATION & CONSTANTS -----------------
IST = pytz.timezone('Asia/Kolkata')
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
RISK_AMOUNT = 400.0  # Fixed ₹400 risk per trade

# Top Liquid Indian Stocks for Intraday Breakouts
WATCHLIST = [
    "RELIANCE.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS", "TCS.NS",
    "BHARATFORG.NS", "SBIN.NS", "TATAMOTORS.NS", "AXISBANK.NS", "KOTAKBANK.NS",
    "LT.NS", "BAJFINANCE.NS", "MARUTI.NS", "SUNPHARMA.NS", "ITC.NS"
]

INDEX_TICKER = "^NSEI"

# State tracking to avoid duplicate alerts
radar_triggered = set()
execution_triggered = set()
target1_achieved = set()
active_trades = {}  # Store trade details: {sym: {'type': 'LONG'/'SHORT', 'entry': price, 't1': t1, 'sl': sl}}

# ----------------- HELPER FUNCTIONS -----------------
def send_telegram_msg(msg: str):
    """Send formatted markdown message to Telegram."""
    if not BOT_TOKEN or not CHAT_ID:
        print("Telegram tokens not configured!")
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": msg,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Error sending Telegram message: {e}")

def get_cpr_and_levels(ticker_symbol: str):
    """Calculate PDH, PDL, Pivot, BC, TC and CPR width from daily data."""
    try:
        t = yf.Ticker(ticker_symbol)
        df_daily = t.history(period="5d", interval="1d")
        if len(df_daily) < 2:
            return None
        prev_day = df_daily.iloc[-2]
        high = prev_day['High']
        low = prev_day['Low']
        close = prev_day['Close']
        
        pivot = (high + low + close) / 3.0
        bc = (high + low) / 2.0
        tc = (pivot - bc) + pivot
        
        cpr_width = abs(tc - bc) / close * 100.0
        return {
            "pdh": high,
            "pdl": low,
            "cpr_width": cpr_width,
            "is_narrow": cpr_width <= 0.38
        }
    except Exception:
        return None

def get_intraday_data(ticker_symbol: str):
    """Fetch 5-minute intraday candle data and calculate VWAP."""
    try:
        t = yf.Ticker(ticker_symbol)
        df = t.history(period="1d", interval="5m")
        if df.empty or len(df) < 2:
            return None
        
        # Calculate intraday VWAP
        df['Typical_Price'] = (df['High'] + df['Low'] + df['Close']) / 3.0
        df['Vol_Price'] = df['Typical_Price'] * df['Volume']
        df['Cum_Vol_Price'] = df['Vol_Price'].cumsum()
        df['Cum_Vol'] = df['Volume'].cumsum()
        df['VWAP'] = df['Cum_Vol_Price'] / df['Cum_Vol']
        
        current_candle = df.iloc[-1]
        prev_candle = df.iloc[-2]
        
        return {
            "close": current_candle['Close'],
            "high": current_candle['High'],
            "low": current_candle['Low'],
            "vwap": current_candle['VWAP'],
            "prev_close": prev_candle['Close']
        }
    except Exception:
        return None

def get_nifty_trend():
    """Determine Nifty intraday trend against VWAP."""
    data = get_intraday_data(INDEX_TICKER)
    if not data:
        return "NEUTRAL"
    if data['close'] > data['vwap']:
        return "BULLISH"
    elif data['close'] < data['vwap']:
        return "BEARISH"
    return "NEUTRAL"

# ----------------- MAIN ENGINE -----------------
def main():
    print("Initializing Ron Weasley System...")
    startup_msg = (
        "🟢 *Ron Weasley System Activated*\n"
        "Real-time monitoring online for Narrow CPR + PDH/PDL breakouts (09:15 AM - 03:15 PM IST)."
    )
    send_telegram_msg(startup_msg)

    # Pre-calculate Daily Levels & Narrow CPR Filter
    cpr_cache = {}
    for sym in WATCHLIST:
        levels = get_cpr_and_levels(sym)
        if levels:
            cpr_cache[sym] = levels
            print(f"[{sym}] Narrow CPR: {levels['is_narrow']} (Width: {levels['cpr_width']:.2f}%)")

    while True:
        now = datetime.datetime.now(IST)
        curr_min = now.hour * 60 + now.minute

        # 1. Clean Exit after Market Close (03:15 PM IST = 915 mins)
        if curr_min > 915:
            print("Market closed (03:15 PM IST). Exiting scanner cleanly.")
            send_telegram_msg("🔴 *Ron Weasley System Closed* for the trading session.")
            break

        # 2. Wait if before Market Opening (09:15 AM IST = 555 mins)
        if curr_min < 555:
            print("Waiting for market opening (09:15 AM IST)...")
            time.sleep(30)
            continue

        nifty_trend = get_nifty_trend()

        for sym in WATCHLIST:
            stock_name = sym.replace(".NS", "")
            levels = cpr_cache.get(sym)
            if not levels or not levels['is_narrow']:
                continue

            intra = get_intraday_data(sym)
            if not intra:
                continue

            price = intra['close']
            vwap = intra['vwap']
            pdh = levels['pdh']
            pdl = levels['pdl']

            # ----------------- 1. PRE-BREAKOUT RADAR ALERT (09:45 AM - 02:45 PM) -----------------
            if 585 <= curr_min <= 885:
                # Bullish radar (within 0.25% of PDH)
                if 0 <= (pdh - price) / pdh <= 0.0025 and nifty_trend == "BULLISH":
                    if f"{sym}_RADAR_LONG" not in radar_triggered:
                        radar_msg = (
                            f"📡 *PRE-BREAKOUT RADAR: LONG WATCH*\n"
                            f"🔹 *Stock:* {stock_name}\n"
                            f"💵 *Current Price:* ₹{price:.2f}\n"
                            f"🎯 *PDH Level:* ₹{pdh:.2f} (Within 0.25%)\n"
                            f"📊 *VWAP:* ₹{vwap:.2f}\n"
                            f"📈 *Nifty Trend:* BULLISH\n"
                            f"⚡ *Action:* Get chart ready for 5m breakout."
                        )
                        send_telegram_msg(radar_msg)
                        radar_triggered.add(f"{sym}_RADAR_LONG")

                # Bearish radar (within 0.25% of PDL)
                if 0 <= (price - pdl) / pdl <= 0.0025 and nifty_trend == "BEARISH":
                    if f"{sym}_RADAR_SHORT" not in radar_triggered:
                        radar_msg = (
                            f"📡 *PRE-BREAKOUT RADAR: SHORT WATCH*\n"
                            f"🔹 *Stock:* {stock_name}\n"
                            f"💵 *Current Price:* ₹{price:.2f}\n"
                            f"🎯 *PDL Level:* ₹{pdl:.2f} (Within 0.25%)\n"
                            f"📊 *VWAP:* ₹{vwap:.2f}\n"
                            f"📉 *Nifty Trend:* BEARISH\n"
                            f"⚡ *Action:* Get chart ready for 5m breakdown."
                        )
                        send_telegram_msg(radar_msg)
                        radar_triggered.add(f"{sym}_RADAR_SHORT")

            # ----------------- 2. CONFIRMED EXECUTION ALERT (10:00 AM - 02:45 PM) -----------------
            if 600 <= curr_min <= 885:
                # BUY TRIGGER: Price > PDH + Price > VWAP + Nifty Bullish
                if price > pdh and price > vwap and nifty_trend == "BULLISH":
                    if f"{sym}_EXEC_LONG" not in execution_triggered:
                        sl = min(vwap, intra['low'])
                        risk_dist = max(price - sl, price * 0.002)
                        qty = max(1, int(RISK_AMOUNT / risk_dist))
                        t1 = price + (1.0 * risk_dist)
                        t2 = price + (2.0 * risk_dist)

                        exec_msg = (
                            f"🚀 *RON WEASLEY EXECUTION: BUY TRIGGERED*\n"
                            f"🔹 *Stock:* {stock_name} (LONG)\n"
                            f"💵 *Entry Price:* ₹{price:.2f}\n"
                            f"🛑 *Initial Stop-Loss:* ₹{sl:.2f} (Risk: ₹{risk_dist:.2f})\n"
                            f"📦 *Position Size:* {qty} Shares (₹400 Fixed Risk)\n"
                            f"🎯 *Target 1 (+1.0R):* ₹{t1:.2f} (Book 50% Quantity)\n"
                            f"🎯 *Target 2 (+2.0R):* ₹{t2:.2f} (Final Target)"
                        )
                        send_telegram_msg(exec_msg)
                        execution_triggered.add(f"{sym}_EXEC_LONG")
                        active_trades[sym] = {'type': 'LONG', 'entry': price, 't1': t1, 'sl': sl}

                # SELL TRIGGER: Price < PDL + Price < VWAP + Nifty Bearish
                if price < pdl and price < vwap and nifty_trend == "BEARISH":
                    if f"{sym}_EXEC_SHORT" not in execution_triggered:
                        sl = max(vwap, intra['high'])
                        risk_dist = max(sl - price, price * 0.002)
                        qty = max(1, int(RISK_AMOUNT / risk_dist))
                        t1 = price - (1.0 * risk_dist)
                        t2 = price - (2.0 * risk_dist)

                        exec_msg = (
                            f"🚀 *RON WEASLEY EXECUTION: SELL TRIGGERED*\n"
                            f"🔹 *Stock:* {stock_name} (SHORT)\n"
                            f"💵 *Entry Price:* ₹{price:.2f}\n"
                            f"🛑 *Initial Stop-Loss:* ₹{sl:.2f} (Risk: ₹{risk_dist:.2f})\n"
                            f"📦 *Position Size:* {qty} Shares (₹400 Fixed Risk)\n"
                            f"🎯 *Target 1 (+1.0R):* ₹{t1:.2f} (Book 50% Quantity)\n"
                            f"🎯 *Target 2 (+2.0R):* ₹{t2:.2f} (Final Target)"
                        )
                        send_telegram_msg(exec_msg)
                        execution_triggered.add(f"{sym}_EXEC_SHORT")
                        active_trades[sym] = {'type': 'SHORT', 'entry': price, 't1': t1, 'sl': sl}

            # ----------------- 3. TARGET 1 (+1.0R) HIT & TRAIL SL ALERT -----------------
            if sym in active_trades and sym not in target1_achieved:
                trade = active_trades[sym]
                t1_hit = False
                if trade['type'] == 'LONG' and price >= trade['t1']:
                    t1_hit = True
                elif trade['type'] == 'SHORT' and price <= trade['t1']:
                    t1_hit = True

                if t1_hit:
                    trail_msg = (
                        f"🎯 *TARGET 1 (+1.0R) ACHIEVED: {stock_name}*\n"
                        f"✅ *Action 1:* Book 50% Profit at ₹{price:.2f}\n"
                        f"🔒 *Action 2:* Move Stop-Loss to Cost (₹{trade['entry']:.2f})\n"
                        f"🚀 *Status:* Trade is now 100% Risk-Free. Let remaining 50% ride till Target 2."
                    )
                    send_telegram_msg(trail_msg)
                    target1_achieved.add(sym)

        # Sleep between scans (60 seconds)
        time.sleep(60)

if __name__ == "__main__":
    main()
