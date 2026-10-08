import sys

with open('c:/Users/Hiranya/spy/dashboard_server.py', 'r', encoding='utf-8') as f:
    content = f.read()

import re

# Find the start and end of get_spy_history
start_idx = content.find('def get_spy_history')
if start_idx == -1:
    print('Could not find get_spy_history')
    sys.exit(1)

# Find where get_spy_history ends (it ends before 'app = Flask(__name__)')
end_idx = content.find('app = Flask(__name__)', start_idx)

new_func = '''def get_spy_history(start=None, end=None, period=None):
    import pandas as pd, os, json, pytz, requests
    
    # 1. Try static JSON cache first
    try:
        if os.path.exists("spy_history.json"):
            with open("spy_history.json", "r") as f:
                data = json.load(f)
            df = pd.DataFrame.from_dict(data, orient="index")
            df.index = pd.to_datetime(df.index)
            tz = pytz.timezone("US/Pacific")
            if df.index.tz is None:
                df.index = df.index.tz_localize(tz)
            else:
                df.index = df.index.tz_convert(tz)
            
            # Ensure volume column exists for VWAP
            if 'Volume' not in df.columns:
                df['Volume'] = 0
                
            if start and end:
                s_dt = pd.to_datetime(start)
                if s_dt.tz is None: s_dt = tz.localize(s_dt)
                e_dt = pd.to_datetime(end)
                if e_dt.tz is None: e_dt = tz.localize(e_dt)
                df_filtered = df[(df.index >= s_dt) & (df.index <= e_dt)]
                if not df_filtered.empty:
                    return df_filtered
    except Exception as e:
        print("spy_history fallback error:", e)

    # 2. Try Alpaca API dynamically
    alpaca_key = os.getenv("ALPACA_API_KEY")
    alpaca_secret = os.getenv("ALPACA_SECRET_KEY")
    if alpaca_key and alpaca_secret and start and end:
        try:
            # For dynamic historical data, Alpaca requires RFC3339 timestamps
            # We use IEX feed which is included in the free tier
            s_dt = pd.to_datetime(start).tz_localize('US/Pacific') if pd.to_datetime(start).tz is None else pd.to_datetime(start)
            e_dt = pd.to_datetime(end).tz_localize('US/Pacific') if pd.to_datetime(end).tz is None else pd.to_datetime(end)
            
            s_str = s_dt.tz_convert('UTC').strftime('%Y-%m-%dT%H:%M:%SZ')
            e_str = e_dt.tz_convert('UTC').strftime('%Y-%m-%dT%H:%M:%SZ')
            
            headers = {
                "APCA-API-KEY-ID": alpaca_key,
                "APCA-API-SECRET-KEY": alpaca_secret
            }
            url = f"https://data.alpaca.markets/v2/stocks/SPY/bars?timeframe=1Min&start={s_str}&end={e_str}&feed=iex"
            res = requests.get(url, headers=headers).json()
            if 'bars' in res and res['bars']:
                df_alpaca = pd.DataFrame(res['bars'])
                df_alpaca['t'] = pd.to_datetime(df_alpaca['t'])
                df_alpaca.set_index('t', inplace=True)
                df_alpaca.index = df_alpaca.index.tz_convert('US/Pacific')
                df_alpaca.rename(columns={'o': 'Open', 'h': 'High', 'l': 'Low', 'c': 'Close', 'v': 'Volume'}, inplace=True)
                return df_alpaca
        except Exception as e:
            print("Alpaca dynamic fetch error:", e)

    # 3. Fallback to yfinance (Will likely fail on Railway but good for local)
    import yfinance as yf
    if period:
        return yf.Ticker("SPY").history(period=period, interval="1m", prepost=True)
    return yf.Ticker("SPY").history(start=start, end=end, interval="1m", prepost=True)
'''

content = content[:start_idx] + new_func + '\n' + content[end_idx:]

with open('c:/Users/Hiranya/spy/dashboard_server.py', 'w', encoding='utf-8') as f:
    f.write(content)
