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

# Top High-Beta & High-Momentum Stocks for Intraday Breakouts
WATCHLIST = [
    "ADANIENT.NS", "BHARATFORG.NS", "TATAMOTORS.NS", "BAJFINANCE.NS",
    "TATASTEEL.NS", "INDUSINDBK.NS", "JSWSTEEL.NS", "SBIN.NS",
    "ICICIBANK.NS", "AXISBANK.NS", "VOLTAS.NS", "JUBLFOOD.NS",
    "DLF.NS", "HINDALCO.NS", "RELIANCE.NS"
]

INDEX_TICKER = "NIFTYBEES.NS"  # Highly liquid ETF with live volume for flawless VWAP

# State tracking to avoid duplicate alerts and manage lifecycle
radar_triggered = set()
execution_triggered = set()
active_trades = {}  # Format: {sym: {'type': 'LONG'/'SHORT', 'entry': float, 'sl': float, 't1': float, 't2': float, 't1_hit': bool}}

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
    """Calculate PDH, PDL, Pivot, BC, TC accurately by filtering completed prior trading day."""
    try:
        t = yf.Ticker(ticker_symbol)
        df_daily = t.history(period="10d", interval="1d")
        if df_daily.empty or len(df_daily) < 2:
            return None
        
        today_date = datetime.datetime.now(IST).date()
        
        # Filter out current running day's incomplete bar if present
        completed_days = df_daily[df_daily.index.date < today_date]
        if completed_days.empty:
            prev_day = df_daily.iloc[-2]
        else:
            prev_day = completed_days.iloc[-1]
            
        high = float(prev_day['High'])
        low = float(prev_day['Low'])
        close = float(prev_day['Close'])
        
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
    """Fetch 5m candle data, calculate VWAP, and return completed & running candle metrics."""
    try:
        t = yf.Ticker(ticker_symbol)
        df = t.history(period="1d", interval="5m")
        if df.empty or len(df) < 3:
            return None
        
        # VWAP calculation
        df['Typical_Price'] = (df['High'] + df['Low'] + df['Close']) / 3.0
        df['Vol_Price'] = df['Typical_Price'] * df['Volume']
        df['Cum_Vol_Price'] = df['Vol_Price'].cumsum()
        df['Cum_Vol'] = df['Volume'].cumsum()
        
        df['VWAP'] = df['Cum_Vol_Price'] / df['Cum_Vol'].replace(0, pd.NA)
        df['VWAP'] = df['VWAP'].bfill().ffill()
        
        current_candle = df.iloc[-1]   # Running candle (Live price)
        completed_candle = df.iloc[-2] # Completed 5m candle (Confirmed breakout)
        
        return {
            "live_price": float(current_candle['Close']),
            "live_high": float(current_candle['High']),
            "live_low": float(current_candle['Low']),
            "live_vwap": float(current_candle['VWAP']),
            "closed_close": float(completed_candle['Close']),
            "closed_high": float(completed_candle['High']),
            "closed_low": float(completed_candle['Low']),
            "closed_vwap": float(completed_candle['VWAP'])
        }
    except Exception:
        return None

def get_nifty_trend():
    """Determine Nifty intraday trend using NIFTYBEES real-volume VWAP."""
    data = get_intraday_data(INDEX_TICKER)
    if not data:
        return "NEUTRAL"
    if data['closed_close'] > data['closed_vwap']:
        return "BULLISH"
    elif data['closed_close'] < data['closed_vwap']:
        return "BEARISH"
    return "NEUTRAL"

# ----------------- MAIN ENGINE -----------------
def main():
    print("Initializing Ron Weasley System...")
    startup_msg = (
        "🟢 *Ron Weasley System Activated*\n"
        "Real-time monitoring online for High-Beta Narrow CPR + PDH/PDL breakouts (09:15 AM - 03:15 PM IST)."
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

            live_price = intra['live_price']
            live_vwap = intra['live_vwap']
            closed_close = intra['closed_close']
            closed_low = intra['closed_low']
            closed_high = intra['closed_high']
            closed_vwap = intra['closed_vwap']
            pdh = levels['pdh']
            pdl = levels['pdl']

            # ----------------- 1. ACTIVE TRADE LIFECYCLE MONITORING -----------------
            if sym in active_trades:
                trade = active_trades[sym]
                trade_type = trade['type']

                if trade_type == 'LONG':
                    # Target 1 Achieved (+1.0R)
                    if not trade['t1_hit'] and live_price >= trade['t1']:
                        trail_msg = (
                            f"🎯 *TARGET 1 (+1.0R) ACHIEVED: {stock_name}*\n"
                            f"✅ *Action 1:* Book 50% Profit at ₹{live_price:.2f}\n"
                            f"🔒 *Action 2:* Move Stop-Loss to Cost (₹{trade['entry']:.2f})\n"
                            f"🚀 *Status:* Trade is Risk-Free. Trailing remaining 50% for T2."
                        )
                        send_telegram_msg(trail_msg)
                        trade['t1_hit'] = True
                        trade['sl'] = trade['entry']

                    # Target 2 Achieved (+2.0R Full Exit)
                    elif live_price >= trade['t2']:
                        t2_msg = (
                            f"🏆 *FINAL TARGET 2 (+2.0R) ACHIEVED: {stock_name}*\n"
                            f"💰 *Action:* Book remaining 50% Profit at ₹{live_price:.2f}\n"
                            f"🏁 *Trade Complete:* Successfully closed full position."
                        )
                        send_telegram_msg(t2_msg)
                        del active_trades[sym]
                        continue

                    # Stop-Loss Hit Exit
                    elif live_price <= trade['sl']:
                        sl_status = "Cost Trailing Stop-Loss Hit (0 Loss)" if trade['t1_hit'] else "Initial Stop-Loss Hit"
                        sl_msg = (
                            f"🛑 *STOP-LOSS TRIGGERED: {stock_name} (LONG)*\n"
                            f"📉 *Exit Price:* ₹{live_price:.2f}\n"
                            f"📌 *Status:* {sl_status}. Position Closed."
                        )
                        send_telegram_msg(sl_msg)
                        del active_trades[sym]
                        continue

                elif trade_type == 'SHORT':
                    # Target 1 Achieved (+1.0R)
                    if not trade['t1_hit'] and live_price <= trade['t1']:
                        trail_msg = (
                            f"🎯 *TARGET 1 (+1.0R) ACHIEVED: {stock_name}*\n"
                            f"✅ *Action 1:* Book 50% Profit at ₹{live_price:.2f}\n"
                            f"🔒 *Action 2:* Move Stop-Loss to Cost (₹{trade['entry']:.2f})\n"
                            f"🚀 *Status:* Trade is Risk-Free. Trailing remaining 50% for T2."
                        )
                        send_telegram_msg(trail_msg)
                        trade['t1_hit'] = True
                        trade['sl'] = trade['entry']

                    # Target 2 Achieved (+2.0R Full Exit)
                    elif live_price <= trade['t2']:
                        t2_msg = (
                            f"🏆 *FINAL TARGET 2 (+2.0R) ACHIEVED: {stock_name}*\n"
                            f"💰 *Action:* Book remaining 50% Profit at ₹{live_price:.2f}\n"
                            f"🏁 *Trade Complete:* Successfully closed full position."
                        )
                        send_telegram_msg(t2_msg)
                        del active_trades[sym]
                        continue

                    # Stop-Loss Hit Exit
                    elif live_price >= trade['sl']:
                        sl_status = "Cost Trailing Stop-Loss Hit (0 Loss)" if trade['t1_hit'] else "Initial Stop-Loss Hit"
                        sl_msg = (
                            f"🛑 *STOP-LOSS TRIGGERED: {stock_name} (SHORT)*\n"
                            f"📈 *Exit Price:* ₹{live_price:.2f}\n"
                            f"📌 *Status:* {sl_status}. Position Closed."
                        )
                        send_telegram_msg(sl_msg)
                        del active_trades[sym]
                        continue

            # ----------------- 2. PRE-BREAKOUT RADAR ALERT (09:45 AM - 02:45 PM) -----------------
            if 585 <= curr_min <= 885 and sym not in active_trades:
                # Bullish radar (within 0.25% of PDH)
                if 0 <= (pdh - live_price) / pdh <= 0.0025 and nifty_trend == "BULLISH":
                    if f"{sym}_RADAR_LONG" not in radar_triggered:
                        radar_msg = (
                            f"📡 *PRE-BREAKOUT RADAR: LONG WATCH*\n"
                            f"🔹 *Stock:* {stock_name}\n"
                            f"💵 *Current Price:* ₹{live_price:.2f}\n"
                            f"🎯 *PDH Level:* ₹{pdh:.2f} (Within 0.25%)\n"
                            f"📊 *VWAP:* ₹{live_vwap:.2f}\n"
                            f"📈 *Nifty Trend:* BULLISH\n"
                            f"⚡ *Action:* Get chart ready for 5m candle close breakout."
                        )
                        send_telegram_msg(radar_msg)
                        radar_triggered.add(f"{sym}_RADAR_LONG")

                # Bearish radar (within 0.25% of PDL)
                if 0 <= (live_price - pdl) / pdl <= 0.0025 and nifty_trend == "BEARISH":
                    if f"{sym}_RADAR_SHORT" not in radar_triggered:
                        radar_msg = (
                            f"📡 *PRE-BREAKOUT RADAR: SHORT WATCH*\n"
                            f"🔹 *Stock:* {stock_name}\n"
                            f"💵 *Current Price:* ₹{live_price:.2f}\n"
                            f"🎯 *PDL Level:* ₹{pdl:.2f} (Within 0.25%)\n"
                            f"📊 *VWAP:* ₹{live_vwap:.2f}\n"
                            f"📉 *Nifty Trend:* BEARISH\n"
                            f"⚡ *Action:* Get chart ready for 5m candle close breakdown."
                        )
                        send_telegram_msg(radar_msg)
                        radar_triggered.add(f"{sym}_RADAR_SHORT")

            # ----------------- 3. CONFIRMED EXECUTION ALERT (10:00 AM - 02:45 PM) -----------------
            if 600 <= curr_min <= 885 and sym not in active_trades:
                # BUY TRIGGER: Completed 5m Candle Close > PDH + Closed Price > Closed VWAP + Nifty Bullish
                if closed_close > pdh and closed_close > closed_vwap and nifty_trend == "BULLISH":
                    if f"{sym}_EXEC_LONG" not in execution_triggered:
                        entry = live_price
                        sl = min(closed_vwap, closed_low)
                        risk_dist = max(entry - sl, entry * 0.002)
                        qty = max(1, int(RISK_AMOUNT / risk_dist))
                        t1 = entry + (1.0 * risk_dist)
                        t2 = entry + (2.0 * risk_dist)

                        exec_msg = (
                            f"🚀 *RON WEASLEY EXECUTION: BUY TRIGGERED*\n"
                            f"🔹 *Stock:* {stock_name} (LONG)\n"
                            f"💵 *Entry Price:* ₹{entry:.2f} (5m Closed > PDH)\n"
                            f"🛑 *Initial Stop-Loss:* ₹{sl:.2f} (Risk: ₹{risk_dist:.2f})\n"
                            f"📦 *Position Size:* {qty} Shares (₹400 Fixed Risk)\n"
                            f"🎯 *Target 1 (+1.0R):* ₹{t1:.2f} (Book 50% Quantity)\n"
                            f"🎯 *Target 2 (+2.0R):* ₹{t2:.2f} (Final Exit)"
                        )
                        send_telegram_msg(exec_msg)
                        execution_triggered.add(f"{sym}_EXEC_LONG")
                        active_trades[sym] = {
                            'type': 'LONG',
                            'entry': entry,
                            'sl': sl,
                            't1': t1,
                            't2': t2,
                            't1_hit': False
                        }

                # SELL TRIGGER: Completed 5m Candle Close < PDL + Closed Price < Closed VWAP + Nifty Bearish
                if closed_close < pdl and closed_close < closed_vwap and nifty_trend == "BEARISH":
                    if f"{sym}_EXEC_SHORT" not in execution_triggered:
                        entry = live_price
                        sl = max(closed_vwap, closed_high)
                        risk_dist = max(sl - entry, entry * 0.002)
                        qty = max(1, int(RISK_AMOUNT / risk_dist))
                        t1 = entry - (1.0 * risk_dist)
                        t2 = entry - (2.0 * risk_dist)

                        exec_msg = (
                            f"🚀 *RON WEASLEY EXECUTION: SELL TRIGGERED*\n"
                            f"🔹 *Stock:* {stock_name} (SHORT)\n"
                            f"💵 *Entry Price:* ₹{entry:.2f} (5m Closed < PDL)\n"
                            f"🛑 *Initial Stop-Loss:* ₹{sl:.2f} (Risk: ₹{risk_dist:.2f})\n"
                            f"📦 *Position Size:* {qty} Shares (₹400 Fixed Risk)\n"
                            f"🎯 *Target 1 (+1.0R):* ₹{t1:.2f} (Book 50% Quantity)\n"
                            f"🎯 *Target 2 (+2.0R):* ₹{t2:.2f} (Final Exit)"
                        )
                        send_telegram_msg(exec_msg)
                        execution_triggered.add(f"{sym}_EXEC_SHORT")
                        active_trades[sym] = {
                            'type': 'SHORT',
                            'entry': entry,
                            'sl': sl,
                            't1': t1,
                            't2': t2,
                            't1_hit': False
                        }

        # Sleep 90 seconds between scan intervals (Prevents Yahoo rate limits)
        time.sleep(90)

if __name__ == "__main__":
    main()
