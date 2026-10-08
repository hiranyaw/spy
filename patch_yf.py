import sys

with open('c:/Users/Hiranya/spy/dashboard_server.py', 'r', encoding='utf-8') as f:
    content = f.read()

helper = '''
def get_spy_history(start=None, end=None, period=None):
    import pandas as pd, os, json, pytz
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
            if start and end:
                s_dt = pd.to_datetime(start)
                if s_dt.tz is None: s_dt = tz.localize(s_dt)
                e_dt = pd.to_datetime(end)
                if e_dt.tz is None: e_dt = tz.localize(e_dt)
                df = df[(df.index >= s_dt) & (df.index <= e_dt)]
            if not df.empty:
                return df
    except Exception as e:
        print("spy_history fallback error:", e)
    
    import yfinance as yf
    if period:
        return yf.Ticker("SPY").history(period=period, interval="1m", prepost=True)
    return yf.Ticker("SPY").history(start=start, end=end, interval="1m", prepost=True)
'''

if 'def get_spy_history' not in content:
    content = content.replace('app = Flask(__name__)', helper + '\napp = Flask(__name__)')

content = content.replace('yf.Ticker("SPY").history(period="3d", interval="1m", prepost=True)', 'get_spy_history(period="3d")')
content = content.replace('yf.Ticker("SPY").history(start=start_date, end=end_date, interval="1m", prepost=True)', 'get_spy_history(start=start_date, end=end_date)')
content = content.replace('yf.Ticker("SPY").history(start=d_str, end=next_dt.strftime("%Y-%m-%d"), interval="1m", prepost=True)', 'get_spy_history(start=d_str, end=next_dt.strftime("%Y-%m-%d"))')
content = content.replace('ticker.history(start=date_str, end=next_date_str, interval="1m", prepost=True)', 'get_spy_history(start=date_str, end=next_date_str)')

with open('c:/Users/Hiranya/spy/dashboard_server.py', 'w', encoding='utf-8') as f:
    f.write(content)
