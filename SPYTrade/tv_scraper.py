"""
tv_scraper.py — Runs the full SCRAPE_JS from spy_trader_bot.py via CDP,
                plus TradingView Scanner REST API for live SPY/QQQ/ADD prices.

Returns a rich dict with:
  spy_price, qqq_price, add_value,
  spy_open, spy_high, spy_low, spy_close,     (real OHLC from Scanner API)
  qqq_open, qqq_high, qqq_low, qqq_close,
  adx_value, macd_dir, signal_tv, conf_tv, status_tv,
  qqq_dir, add_dir, spy5_dir, spy1_dir,
  tl_break, st_flip, div_signal, vwap_pct, engulf,
  resist, support, st_level, timestamp, title
"""
import json, base64, os, socket, urllib.request, urllib.parse, logging, re, pathlib
import datetime

log = logging.getLogger(__name__)

CDP_HOST = "127.0.0.1"
CDP_PORT = 9222


# ── TradingView Scanner REST API (always returns real-time prices) ────────────

def fetch_live_prices() -> dict | None:
    """Fetch real-time SPY, QQQ, and ADD prices from the TradingView Scanner API.

    This endpoint requires NO authentication and returns live market data
    including pre-market / after-hours prices.

    Returns a dict like::

        {
            "spy_price": 765.72, "spy_open": 766.05, "spy_high": 767.85, "spy_low": 764.17,
            "spy_change_pct": 0.41, "spy_volume": 39188355,
            "qqq_price": 713.44, "qqq_open": 715.23, "qqq_high": 715.67, "qqq_low": 709.20,
            "qqq_change_pct": 0.35, "qqq_volume": 33399334,
            "add_value": -879.0,
        }

    or ``None`` on failure.
    """
    try:
        body = json.dumps({
            "symbols": {
                "tickers": ["AMEX:SPY", "NASDAQ:QQQ", "USI:ADD"],
                "query": {"types": []},
            },
            "columns": [
                "close", "open", "high", "low",
                "change", "change_abs", "volume",
            ],
        }).encode()
        req = urllib.request.Request(
            "https://scanner.tradingview.com/america/scan",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Origin": "https://www.tradingview.com",
            },
        )
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.load(r)

        result: dict = {}
        for item in data.get("data", []):
            sym = item["s"]           # e.g. "AMEX:SPY"
            d = item["d"]             # [close, open, high, low, chg%, chg_abs, vol]
            close, opn, high, low = d[0], d[1], d[2], d[3]
            chg_pct, vol = d[4], d[6]

            if "SPY" in sym:
                result["spy_price"]      = close
                result["spy_open"]       = opn
                result["spy_high"]       = high
                result["spy_low"]        = low
                result["spy_change_pct"] = round(chg_pct, 2) if chg_pct else 0.0
                result["spy_volume"]     = int(vol) if vol else 0
            elif "QQQ" in sym:
                result["qqq_price"]      = close
                result["qqq_open"]       = opn
                result["qqq_high"]       = high
                result["qqq_low"]        = low
                result["qqq_change_pct"] = round(chg_pct, 2) if chg_pct else 0.0
                result["qqq_volume"]     = int(vol) if vol else 0
            elif "ADD" in sym:
                result["add_value"]      = close

        log.info(
            "fetch_live_prices: SPY=%.2f  QQQ=%.2f  ADD=%s",
            result.get("spy_price", 0),
            result.get("qqq_price", 0),
            result.get("add_value"),
        )
        return result

    except Exception as e:
        log.error("fetch_live_prices failed: %s", e)
        return None

# ── Load SCRAPE_JS once from spy_trader_bot.py ────────────────────────────────
_BOT_PATH = pathlib.Path(__file__).parent.parent / "spy_trader_bot.py"
_SCRAPE_JS: str | None = None

def _load_scrape_js() -> str | None:
    global _SCRAPE_JS
    if _SCRAPE_JS is not None:
        return _SCRAPE_JS
    try:
        src = _BOT_PATH.read_text(encoding="utf-8")
        m = re.search(r'SCRAPE_JS = r"""(.*?)"""', src, re.DOTALL)
        if m:
            raw = m.group(1).strip()
            _SCRAPE_JS = "(" + raw + ")()"
            log.info("tv_scraper: SCRAPE_JS loaded (%d chars)", len(_SCRAPE_JS))
            return _SCRAPE_JS
    except Exception as e:
        log.error("tv_scraper: could not load SCRAPE_JS from %s: %s", _BOT_PATH, e)
    return None


# ── WebSocket helpers (same pattern as tradingview_client.py) ─────────────────

def _ws_send(sock: socket.socket, text: str) -> None:
    payload  = text.encode("utf-8")
    mask_key = os.urandom(4)
    masked   = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))
    plen = len(payload)
    if plen < 126:
        header = bytes([0x81, 0x80 | plen])
    elif plen < 65536:
        header = bytes([0x81, 0xFE]) + plen.to_bytes(2, "big")
    else:
        header = bytes([0x81, 0xFF]) + plen.to_bytes(8, "big")
    sock.sendall(header + mask_key + masked)


def _ws_recv(sock: socket.socket, timeout: int = 20) -> str:
    sock.settimeout(timeout)
    def rx(n):
        buf = b""
        while len(buf) < n:
            chunk = sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("Socket closed")
            buf += chunk
        return buf
    header      = rx(2)
    payload_len = header[1] & 0x7F
    if payload_len == 126:
        payload_len = int.from_bytes(rx(2), "big")
    elif payload_len == 127:
        payload_len = int.from_bytes(rx(8), "big")
    return rx(payload_len).decode("utf-8", errors="replace")


def _get_tv_ws_url() -> str | None:
    try:
        with urllib.request.urlopen(
            f"http://{CDP_HOST}:{CDP_PORT}/json", timeout=5
        ) as r:
            pages = json.load(r)
        for p in pages:
            if p.get("type") == "page" and "tradingview" in p.get("url", "").lower():
                return p.get("webSocketDebuggerUrl")
        for p in pages:
            if p.get("type") == "page":
                return p.get("webSocketDebuggerUrl")
    except Exception as e:
        log.error("tv_scraper: CDP endpoint error: %s", e)
    return None


def _open_ws(ws_url: str, timeout: int = 10) -> socket.socket:
    parsed = urllib.parse.urlparse(ws_url)
    path = parsed.path
    if not path:
        path = "/"
    if parsed.query:
        path += f"?{parsed.query}"
    key  = base64.b64encode(os.urandom(16)).decode()
    handshake = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: localhost\r\n"
        f"Origin: http://localhost\r\n"
        f"Upgrade: websocket\r\n"
        f"Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        f"Sec-WebSocket-Version: 13\r\n"
        f"\r\n"
    )
    port = parsed.port or CDP_PORT
    host = parsed.hostname or CDP_HOST
    sock = socket.create_connection((host, port), timeout=timeout)
    sock.sendall(handshake.encode())
    resp = b""
    while b"\r\n\r\n" not in resp:
        chunk = sock.recv(4096)
        if not chunk:
            break
        resp += chunk
    status_line = resp.split(b"\r\n")[0].decode()
    if "101" not in status_line:
        sock.close()
        raise ConnectionError(
            f"WebSocket upgrade failed: {status_line.strip()} | "
            f"{resp.decode(errors='replace')[:200]}"
        )
    return sock


# ── Public API ────────────────────────────────────────────────────────────────

def _fetch_cdp_indicators() -> dict | None:
    """Run SCRAPE_JS on the open TradingView tab and return raw indicator dict.

    Returns ``None`` on any failure.
    """
    js = _load_scrape_js()
    if not js:
        log.warning("tv_scraper: SCRAPE_JS unavailable — skipping indicator fetch")
        return None

    ws_url = _get_tv_ws_url()
    if not ws_url:
        log.info("tv_scraper: no TradingView tab found")
        return None

    try:
        sock = _open_ws(ws_url)
    except Exception as e:
        log.error("tv_scraper: WS open failed: %s", e)
        return None

    try:
        # Enable Runtime
        _ws_send(sock, json.dumps({"id": 1, "method": "Runtime.enable", "params": {}}))
        for _ in range(10):
            try:
                m = json.loads(_ws_recv(sock, timeout=5))
                if m.get("id") == 1:
                    break
            except Exception:
                break

        # Evaluate SCRAPE_JS
        _ws_send(sock, json.dumps({
            "id": 2, "method": "Runtime.evaluate",
            "params": {"expression": js, "returnByValue": True, "awaitPromise": False},
        }))

        for _ in range(40):
            try:
                m = json.loads(_ws_recv(sock, timeout=15))
            except Exception as e:
                log.error("tv_scraper: recv error: %s", e)
                return None
            if m.get("id") == 2:
                value = m.get("result", {}).get("result", {}).get("value")
                if not value:
                    log.warning("tv_scraper: JS returned no value")
                    return None
                data = json.loads(value)
                # Clean up: convert string prices to floats
                for key in ("spy_price", "qqq_price"):
                    if isinstance(data.get(key), str):
                        try:
                            data[key] = float(data[key].replace(",", ""))
                        except Exception:
                            data[key] = None
                log.info(
                    "tv_scraper CDP: spy=%.2f  qqq=%.2f  adx=%s  signal=%s  conf=%s  addir=%s  tl=%s",
                    data.get("spy_price") or 0,
                    data.get("qqq_price") or 0,
                    data.get("adx_value"),
                    data.get("signal_tv"),
                    data.get("conf_tv"),
                    data.get("add_dir"),
                    data.get("tl_break"),
                )
                return data

    except Exception as e:
        log.error("tv_scraper: unexpected error: %s", e)
        return None
    finally:
        try:
            sock.close()
        except Exception:
            pass

    log.warning("tv_scraper: no CDP response within frame limit")
    return None


def fetch_indicators() -> dict | None:
    """Fetch indicators from CDP + real-time prices from TradingView Scanner API.

    The CDP scraper provides trading signals (ADX, MACD direction, signal,
    confluence, trendline breaks, Supertrend flips, etc.).
    The Scanner API provides always-fresh SPY/QQQ/ADD prices with OHLC.

    Prices from the Scanner API **override** any stale DOM-scraped prices.

    Returns a merged dict with all indicator and price fields, or ``None``
    if both sources fail.
    """
    # 1. Fetch real-time prices from Scanner API (always reliable)
    live = fetch_live_prices()

    # 2. Fetch indicator signals from CDP DOM scrape
    cdp = _fetch_cdp_indicators()

    if not live and not cdp:
        log.warning("tv_scraper: both Scanner API and CDP failed")
        return None

    # Start with CDP data (contains all indicator signals)
    merged: dict = cdp if cdp else {}

    # Override/add live prices from Scanner API (always more accurate)
    if live:
        # SPY prices
        merged["spy_price"]      = live.get("spy_price", merged.get("spy_price"))
        merged["spy_open"]       = live.get("spy_open")
        merged["spy_high"]       = live.get("spy_high")
        merged["spy_low"]        = live.get("spy_low")
        merged["spy_change_pct"] = live.get("spy_change_pct")
        merged["spy_volume"]     = live.get("spy_volume")

        # QQQ prices
        merged["qqq_price"]      = live.get("qqq_price", merged.get("qqq_price"))
        merged["qqq_open"]       = live.get("qqq_open")
        merged["qqq_high"]       = live.get("qqq_high")
        merged["qqq_low"]        = live.get("qqq_low")
        merged["qqq_change_pct"] = live.get("qqq_change_pct")
        merged["qqq_volume"]     = live.get("qqq_volume")

        # ADD (breadth)
        if live.get("add_value") is not None:
            merged["add_value"]  = live["add_value"]

    # Ensure timestamp
    if "timestamp" not in merged:
        merged["timestamp"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

    log.info(
        "fetch_indicators MERGED: SPY=$%.2f  QQQ=$%.2f  ADD=%s  adx=%s  signal=%s",
        merged.get("spy_price") or 0,
        merged.get("qqq_price") or 0,
        merged.get("add_value"),
        merged.get("adx_value"),
        merged.get("signal_tv"),
    )
    return merged

