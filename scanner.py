import json
import time
import urllib.request
from datetime import datetime

TELEGRAM_BOT_TOKEN = "8969458120:AAHPn7fb95a8wDDD4XYlpkLcIe5lWoXhumo"
TELEGRAM_CHAT_ID = "8333484358"

MIN_STOCK_PRICE = 350.0
MAX_CPR_WIDTH_PCT = 0.22
MAX_3DAY_RANGE_PCT = 2.5
MIN_RVOL = 1.30

NIFTY_150_UNIVERSE = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS",
    "BHARTIARTL.NS", "LT.NS", "SBIN.NS", "AXISBANK.NS", "KOTAKBANK.NS",
    "TATAMOTORS.NS", "M&M.NS", "BAJFINANCE.NS", "MARUTI.NS", "SUNPHARMA.NS",
    "TITAN.NS", "TRENT.NS", "HCLTECH.NS", "WIPRO.NS", "TECHM.NS",
    "ASIANPAINT.NS", "HINDUNILVR.NS", "NTPC.NS", "POWERGRID.NS", "ADANIENT.NS",
    "EICHERMOT.NS", "HEROMOTOCO.NS", "BAJAJ-AUTO.NS", "TATASTEEL.NS", "JSWSTEEL.NS",
    "LTIM.NS", "NESTLEIND.NS", "BRITANNIA.NS", "DABUR.NS", "GODREJCP.NS",
    "TATACONSUM.NS", "DLF.NS", "LODHA.NS", "GODREJPROP.NS", "INDUSINDBK.NS",
    "BANKBARODA.NS", "PNB.NS", "ADANIPORTS.NS", "ONGC.NS", "COALINDIA.NS",
    "HINDALCO.NS", "GRASIM.NS", "DRREDDY.NS", "CIPLA.NS", "DIVISLAB.NS",
    "APOLLOHOSP.NS", "BAJAJFINSV.NS", "SBICARD.NS", "SHREECEM.NS", "ULTRACEMCO.NS",
    "AMBUJACEM.NS", "CHOLAFIN.NS", "GAIL.NS", "HAVELLS.NS", "ICICIGI.NS",
    "ICICIPRULI.NS", "INDIGO.NS", "JINDALSTEL.NS", "MUTHOOTFIN.NS", "PIDILITIND.NS",
    "SRF.NS", "SIEMENS.NS", "TORNTPHARM.NS", "TVSMOTOR.NS", "HAL.NS",
    "BEL.NS", "BOSCHLTD.NS", "COLPAL.NS", "CUMMINSIND.NS", "ESCORTS.NS",
    "NAUKRI.NS", "PAGEIND.NS", "PIIND.NS", "POLYCAB.NS", "RECLTD.NS",
    "PFC.NS", "TATACHEM.NS", "TATACOMM.NS", "VOLTAS.NS", "PERSISTENT.NS",
    "DIXON.NS", "KAYNES.NS", "MAXHEALTH.NS", "ZYDUSLIFE.NS", "LUPIN.NS"
]

def fetch_live_ohlcv(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=1mo"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            res = data['chart']['result'][0]
            quote = res['indicators']['quote'][0]
            timestamps = res['timestamp']
            bars = []
            for i in range(len(timestamps)):
                o, h, l, c, v = quote['open'][i], quote['high'][i], quote['low'][i], quote['close'][i], quote['volume'][i]
                if None not in (o, h, l, c, v) and v > 0:
                    bars.append({
                        "open": float(o), "high": float(h), "low": float(l),
                        "close": float(c), "volume": int(v)
                    })
            return bars
    except Exception:
        return []

def calculate_cpr(high, low, close):
    pivot = (high + low + close) / 3.0
    bc = (high + low) / 2.0
    tc = (pivot - bc) + pivot
    tc_act, bc_act = max(tc, bc), min(tc, bc)
    width_pct = ((tc_act - bc_act) / pivot) * 100.0
    return {"pivot": round(pivot, 2), "tc": round(tc_act, 2), "bc": round(bc_act, 2), "width_pct": round(width_pct, 3)}

def analyze_setup(bars):
    if len(bars) < 10:
        return None

    today = bars[-1]
    cmp = today["close"]
    if cmp < MIN_STOCK_PRICE:
        return None

    prev_day = bars[-2]
    cpr = calculate_cpr(prev_day["high"], prev_day["low"], prev_day["close"])

    prior_3 = bars[-4:-1]
    b_high = max(b["high"] for b in prior_3)
    b_low = min(b["low"] for b in prior_3)
    b_range = round(((b_high - b_low) / b_low) * 100.0, 2)
    if b_range > MAX_3DAY_RANGE_PCT:
        return None

    prior_vols = [b["volume"] for b in bars[-20:-1]]
    avg_vol = sum(prior_vols) / len(prior_vols) if prior_vols else 1
    rvol = round(today["volume"] / avg_vol, 2) if avg_vol > 0 else 1.0

    breakout_up = cmp > b_high and cmp > cpr["tc"]
    if breakout_up:
        entry = cmp
        sl = round(max(cpr["pivot"], b_high * 0.993), 2)
        risk = entry - sl
        t1 = round(entry + (risk * 1.5), 2)
        t2 = round(entry + (risk * 2.0), 2)
        return {
            "cmp": cmp, "cpr": cpr, "box_high": round(b_high, 2), "box_low": round(b_low, 2),
            "range": b_range, "rvol": rvol, "entry": entry, "sl": sl, "t1": t1, "t2": t2
        }
    return None

def send_telegram(html_msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = json.dumps({"chat_id": TELEGRAM_CHAT_ID, "text": html_msg, "parse_mode": "HTML"}).encode('utf-8')
        req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception:
        return False

def main():
    signals = []
    for sym in list(set(NIFTY_150_UNIVERSE)):
        bars = fetch_live_ohlcv(sym)
        if not bars:
            continue
        res = analyze_setup(bars)
        if res:
            signals.append((sym, res))
            msg = (
                f"⚡ <b>CLOUD INTRADAY CPR SQUEEZE — {sym}</b> ⚡\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📈 <b>Action:</b> INTRADAY LONG BREAKOUT\n"
                f"📊 <b>CMP:</b> ₹{res['cmp']:,.2f} | <b>RVOL:</b> {res['rvol']}x\n"
                f"• <b>3-Day Box:</b> ₹{res['box_low']} - ₹{res['box_high']} ({res['range']}% Squeeze)\n"
                f"• <b>CPR Width:</b> {res['cpr']['width_pct']}%\n\n"
                f"🎯 <b>EXECUTION SETUP</b>\n"
                f"• <b>Entry:</b> ₹{res['entry']:,.2f}\n"
                f"• <b>Target 1:</b> ₹{res['t1']:,.2f}\n"
                f"• <b>Target 2:</b> ₹{res['t2']:,.2f}\n"
                f"• <b>Stop Loss:</b> ₹{res['sl']:,.2f}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━"
            )
            send_telegram(msg)
            time.sleep(0.3)

    if signals:
        send_telegram(f"📊 Cloud Scan: {len(signals)} Active Breakout Signal(s) Pushed.")

if __name__ == "__main__":
    main()
