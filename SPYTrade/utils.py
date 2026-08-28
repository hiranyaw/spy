import datetime
import pytz

def utc_to_local(utc_dt_str, tz_name='America/Los_Angeles'):
    """Convert an ISO UTC timestamp string to a localized string (e.g., UTC-7).
    Returns a formatted string like '2026-08-20 13:45:00'.
    """
    utc_dt = datetime.datetime.fromisoformat(utc_dt_str.replace('Z', '+00:00'))
    local_tz = pytz.timezone(tz_name)
    local_dt = utc_dt.astimezone(local_tz)
    return local_dt.strftime('%Y-%m-%d %H:%M:%S')

def pct_change(open_price, close_price):
    """Return percentage change from open to close.
    Positive for bullish, negative for bearish.
    """
    if open_price == 0:
        return 0.0
    return ((close_price - open_price) / open_price) * 100
