import json
import base64
import os
import socket
import urllib.request
import urllib.parse
import logging
from collections import deque
from threading import Lock

# Chrome Remote Debugging must be running on localhost:9222
# Launch Chrome with: chrome.exe --remote-debugging-port=9222
CDP_HOST = "127.0.0.1"
CDP_PORT = 9222
CDP_JSON_ENDPOINT = f"http://{CDP_HOST}:{CDP_PORT}/json"

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

# ── Rolling bar history buffer ─────────────────────────────────────────────────
# Accumulates bars as the app runs (Option A: in-memory accumulation).
# Holds up to 10 bars (oldest first, newest last).
_BAR_HISTORY: deque = deque(maxlen=10)
_BAR_HISTORY_LOCK = Lock()
_LAST_BAR_TIMESTAMP = None   # deduplicate repeated fetches of same bar


def get_bar_history():
    """Return a copy of the recent bar history list (oldest first, newest last).

    Does NOT include the bar currently being fetched — call this before
    ``fetch_latest_bar`` to get the context for signal analysis.
    """
    with _BAR_HISTORY_LOCK:
        return list(_BAR_HISTORY)


def _push_history(bar):
    """Push ``bar`` into the rolling history buffer, deduplicating by timestamp."""
    global _LAST_BAR_TIMESTAMP
    with _BAR_HISTORY_LOCK:
        if bar.get("timestamp") != _LAST_BAR_TIMESTAMP:
            _BAR_HISTORY.append(bar)
            _LAST_BAR_TIMESTAMP = bar.get("timestamp")
            log.debug("History buffer updated — %d bar(s) stored.", len(_BAR_HISTORY))



# ---------------------------------------------------------------------------
# JavaScript injected into the TradingView page via CDP Runtime.evaluate.
# Strategy order: proven tradingview.com internal API first, then fallbacks.
# ---------------------------------------------------------------------------
_EXTRACT_JS = """
(function () {
    'use strict';
    try {
        var result = null;

        // ── Strategy 1: TradingViewApi._activeChartWidgetWV (tradingview.com) ──
        // Confirmed working path discovered in spy_dashboard project.
        // Bar values: value[1]=open, [2]=high, [3]=low, [4]=close, [5]=volume
        // Bar time: Unix seconds (last.time or last.value[0]).
        if (!result) {
            try {
                var chartApi = window.TradingViewApi._activeChartWidgetWV.value();
                var model    = chartApi._chartWidget.model();
                var bars     = model.mainSeries().bars();
                var last     = null;
                if (typeof bars.last === 'function') {
                    last = bars.last();
                } else if (bars._items && bars._items.length > 0) {
                    last = bars._items[bars._items.length - 1];
                } else if (typeof bars.items === 'function') {
                    var bArr = bars.items();
                    if (bArr && bArr.length > 0) last = bArr[bArr.length - 1];
                }
                if (last && last.value) {
                    var barTime = last.time !== undefined ? last.time : last.value[0];
                    result = {
                        open:      last.value[1],
                        high:      last.value[2],
                        low:       last.value[3],
                        close:     last.value[4],
                        volume:    last.value[5] || 0,
                        timestamp: new Date(barTime * 1000).toISOString()
                    };
                }
            } catch (e1) {}
        }

        // ── Strategy 2: window.tvWidget (Charting Library / Widget API) ──
        if (!result) {
            try {
                if (window.tvWidget && typeof window.tvWidget.activeChart === 'function') {
                    var chart = window.tvWidget.activeChart();
                    var ms = (typeof chart.mainSeries === 'function') ? chart.mainSeries()
                           : (typeof chart.getSeries   === 'function') ? chart.getSeries()
                           : null;
                    if (ms) {
                        var rawBars = typeof ms.bars === 'function' ? ms.bars()
                                    : typeof ms.data === 'function' ? ms.data()
                                    : null;
                        if (rawBars) {
                            var arr = typeof rawBars.toArray === 'function' ? rawBars.toArray()
                                    : Array.isArray(rawBars) ? rawBars : null;
                            if (arr && arr.length) {
                                var b = arr[arr.length - 1];
                                result = {
                                    open:      b.open  !== undefined ? b.open  : b[1],
                                    high:      b.high  !== undefined ? b.high  : b[2],
                                    low:       b.low   !== undefined ? b.low   : b[3],
                                    close:     b.close !== undefined ? b.close : b[4],
                                    volume:    0,
                                    timestamp: new Date((b.time !== undefined ? b.time : b[0]) * 1000).toISOString()
                                };
                            }
                        }
                    }
                }
            } catch (e2) {}
        }

        // ── Strategy 3: TradingView.chartWidgetCollection ──
        if (!result && window.TradingView && window.TradingView.chartWidgetCollection) {
            try {
                var wc   = window.TradingView.chartWidgetCollection;
                var keys = Object.keys(wc);
                for (var i = 0; i < keys.length && !result; i++) {
                    var w = wc[keys[i]];
                    if (!w || !w._ready) continue;
                    try {
                        var chart3 = w.activeChart ? w.activeChart() : null;
                        if (!chart3) continue;
                        var ms3 = chart3.mainSeries ? chart3.mainSeries() : null;
                        if (!ms3) continue;
                        var bars3 = ms3.bars ? ms3.bars() : null;
                        if (!bars3) continue;
                        var arr3 = bars3.toArray ? bars3.toArray() : Array.from(bars3);
                        if (arr3 && arr3.length) {
                            var b3 = arr3[arr3.length - 1];
                            result = {
                                open:      b3.open,
                                high:      b3.high,
                                low:       b3.low,
                                close:     b3.close,
                                volume:    0,
                                timestamp: new Date(b3.time * 1000).toISOString()
                            };
                        }
                    } catch (inner) {}
                }
            } catch (e3) {}
        }

        return result ? JSON.stringify(result) : null;
    } catch (e) {
        return null;
    }
})();
"""


def _get_target_page_ws_url():
    """Retrieve the WebSocket debugger URL for the TradingView tab (or first active page target).
    Returns ``None`` if Chrome remote debugging is not available.
    """
    try:
        with urllib.request.urlopen(CDP_JSON_ENDPOINT, timeout=5) as resp:
            pages = json.load(resp)
        if not pages:
            log.warning("No pages reported by Chrome remote debugging endpoint.")
            return None
        # Prefer pages whose type is 'page' and URL contains tradingview
        for p in pages:
            if p.get("type") == "page" and "tradingview" in p.get("url", "").lower():
                return p.get("webSocketDebuggerUrl")
        # Fallback to any page target
        page_targets = [p for p in pages if p.get("type") == "page"]
        target = page_targets[0] if page_targets else pages[0]
        return target.get("webSocketDebuggerUrl")
    except Exception as e:
        log.error("Failed to contact Chrome remote debugging endpoint: %s", e)
        return None


def _ws_send_frame(sock: socket.socket, text: str) -> None:
    """Send a masked WebSocket text frame over a raw socket (client → server)."""
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


def _ws_recv_frame(sock: socket.socket) -> str:
    """Read one complete WebSocket text frame from a raw socket."""
    def recv_exact(n):
        buf = b""
        while len(buf) < n:
            chunk = sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("Socket closed")
            buf += chunk
        return buf

    header     = recv_exact(2)
    payload_len = header[1] & 0x7F
    if payload_len == 126:
        payload_len = int.from_bytes(recv_exact(2), "big")
    elif payload_len == 127:
        payload_len = int.from_bytes(recv_exact(8), "big")
    return recv_exact(payload_len).decode("utf-8", errors="replace")


def _cdp_recv_by_id(sock: socket.socket, target_id: int, max_messages: int = 30) -> dict | None:
    """Read WS frames until we get the CDP response whose id == target_id.

    Skips domain-event frames (no ``id`` field) that Chrome emits after
    Runtime.enable — those would corrupt the result if not filtered out.
    """
    for _ in range(max_messages):
        try:
            raw = _ws_recv_frame(sock)
        except Exception as e:
            log.error("WebSocket recv error: %s", e)
            return None
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if msg.get("id") == target_id:
            return msg
    log.warning("No CDP response for id=%d within %d messages.", target_id, max_messages)
    return None


def _open_cdp_socket(ws_url: str, timeout: int = 10) -> socket.socket:
    """Open a raw TCP socket and perform the WebSocket upgrade handshake.

    Sets ``Host: localhost`` and ``Origin: http://localhost`` (bare, no port).
    Chrome's CDP rejects connections from any other Origin value (including
    the default ``http://127.0.0.1:9222`` that websocket-client sends).

    Ported directly from spy_dashboard/mcp_client.py which is confirmed working.
    """
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

    # Read until end of HTTP response headers
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


def fetch_latest_bar() -> dict | None:
    """Connect to Chrome via CDP, extract the latest 1-minute SPY bar.

    Returns a dict with keys: ``open``, ``high``, ``low``, ``close``,
    ``timestamp`` (ISO-8601 UTC string), ``volume``.
    Returns ``None`` on any failure (Chrome not running, JS error, etc.).
    """
    ws_url = _get_target_page_ws_url()
    if not ws_url:
        log.info("Chrome remote debugging not detected – returning no data.")
        return None

    try:
        sock = _open_cdp_socket(ws_url)
    except Exception as e:
        log.error("CDP connection failed: %s", e)
        return None

    try:
        # Enable the Runtime domain (id=1)
        _ws_send_frame(sock, json.dumps({"id": 1, "method": "Runtime.enable", "params": {}}))
        _cdp_recv_by_id(sock, 1)

        # Evaluate the extraction script (id=2)
        _ws_send_frame(sock, json.dumps({
            "id": 2,
            "method": "Runtime.evaluate",
            "params": {
                "expression":   _EXTRACT_JS,
                "returnByValue": True,
                "awaitPromise":  False,
            },
        }))
        resp = _cdp_recv_by_id(sock, 2)
        if resp is None:
            log.warning("No response received for Runtime.evaluate.")
            return None

        value = resp.get("result", {}).get("result", {}).get("value")
        if not value:
            log.warning(
                "JavaScript evaluation returned no bar data – "
                "ensure TradingView is open and the chart is loaded."
            )
            return None

        bar = json.loads(value)
        required = {"open", "high", "low", "close", "timestamp"}
        if not required.issubset(bar.keys()):
            log.warning("Bar data missing expected fields: %s", bar)
            return None
        _push_history(bar)
        return bar


    except Exception as e:
        log.error("Unexpected error during CDP session: %s", e)
        return None
    finally:
        try:
            sock.close()
        except Exception:
            pass
