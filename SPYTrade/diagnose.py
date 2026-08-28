#!/usr/bin/env python3
"""
diagnose.py — Run this WITHOUT launching app.py to diagnose the CDP connection.
It prints and logs every step so you can see exactly where things fail.

Usage:
    python diagnose.py
"""
import json
import logging
import pathlib
import sys
import urllib.request

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

# ── logging to both console and file ─────────────────────────────────────────
LOG_FILE = pathlib.Path(__file__).parent / "spytrade.log"
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("diagnose")

log.info("=" * 60)
log.info("SPYTrade DIAGNOSTIC")
log.info("=" * 60)

# ── Step 1: can we reach the CDP endpoint? ───────────────────────────────────
log.info("[1] Checking http://127.0.0.1:9222/json ...")
try:
    with urllib.request.urlopen("http://127.0.0.1:9222/json", timeout=5) as r:
        pages = json.load(r)
    log.info("    OK — %d target(s) found", len(pages))
    for i, p in enumerate(pages):
        log.info("    [%d] type=%-12s  url=%s", i, p.get("type","?"), p.get("url","")[:80])
except Exception as e:
    log.error("    FAIL — %s", e)
    log.error("    >>> Chrome is NOT running with --remote-debugging-port=9222")
    log.error("    >>> Run: launch_tv.bat  (in spy_dashboard folder)")
    sys.exit(1)

# ── Step 2: find a TradingView page target ───────────────────────────────────
log.info("[2] Looking for a TradingView page target ...")
tv_target = None
for p in pages:
    if p.get("type") == "page" and "tradingview" in p.get("url", ""):
        tv_target = p
        break
if not tv_target:
    # fall back to any page
    for p in pages:
        if p.get("type") == "page":
            tv_target = p
            break

if not tv_target:
    log.error("    FAIL — No 'page' type target found at all")
    sys.exit(1)

log.info("    OK — Using target: %s", tv_target.get("url","")[:80])
ws_url = tv_target.get("webSocketDebuggerUrl", "")
log.info("    WS debugger URL: %s", ws_url)

# ── Step 3: open raw TCP socket + WebSocket handshake ───────────────────────
log.info("[3] Opening raw TCP WebSocket to Chrome CDP ...")
import base64, os, socket as _socket

try:
    import urllib.parse
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
    sock = _socket.create_connection(("localhost", 9222), timeout=10)
    sock.sendall(handshake.encode())

    resp = b""
    while b"\r\n\r\n" not in resp:
        chunk = sock.recv(4096)
        if not chunk:
            break
        resp += chunk

    status = resp.split(b"\r\n")[0].decode()
    if "101" not in status:
        log.error("    FAIL — Upgrade rejected: %s", status.strip())
        log.error("    Full response: %s", resp.decode(errors="replace")[:300])
        sys.exit(1)
    log.info("    OK — WebSocket upgrade: %s", status.strip())
except Exception as e:
    log.error("    FAIL — %s", e)
    sys.exit(1)

# ── Step 4: enable Runtime domain ────────────────────────────────────────────
log.info("[4] Sending Runtime.enable ...")

def ws_send(sock, text):
    payload  = text.encode("utf-8")
    mask_key = os.urandom(4)
    masked   = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))
    plen = len(payload)
    header = bytes([0x81, 0x80 | plen]) if plen < 126 else bytes([0x81, 0xFE]) + plen.to_bytes(2,"big")
    sock.sendall(header + mask_key + masked)

def ws_recv(sock):
    def rx(n):
        buf = b""
        while len(buf) < n:
            c = sock.recv(n - len(buf))
            if not c: raise ConnectionError("closed")
            buf += c
        return buf
    h = rx(2)
    plen = h[1] & 0x7F
    if plen == 126: plen = int.from_bytes(rx(2), "big")
    elif plen == 127: plen = int.from_bytes(rx(8), "big")
    return rx(plen).decode("utf-8", errors="replace")

try:
    ws_send(sock, json.dumps({"id": 1, "method": "Runtime.enable", "params": {}}))
    for _ in range(10):
        msg = json.loads(ws_recv(sock))
        if msg.get("id") == 1:
            log.info("    OK — Runtime.enable acknowledged")
            break
    else:
        log.warning("    WARNING — Runtime.enable response not received (may still work)")
except Exception as e:
    log.error("    FAIL — %s", e)
    sys.exit(1)

# ── Step 5: run the extraction JS ────────────────────────────────────────────
log.info("[5] Evaluating bar-extraction JavaScript ...")

PROBE_JS = """
(function() {
    var info = {
        hasTradingViewApi: !!window.TradingViewApi,
        hasActiveChartWV:  !!(window.TradingViewApi && window.TradingViewApi._activeChartWidgetWV),
        hasTvWidget:       !!window.tvWidget,
        hasTVNamespace:    !!window.TradingView,
        pageTitle:         document.title,
        pageUrl:           location.href.substring(0, 80),
    };
    // Try the main data path
    try {
        var chartApi = window.TradingViewApi._activeChartWidgetWV.value();
        var model    = chartApi._chartWidget.model();
        var bars     = model.mainSeries().bars();
        var last     = typeof bars.last === 'function' ? bars.last() : (bars._items ? bars._items[bars._items.length - 1] : null);
        if (last && last.value) {
            var barTime = last.time !== undefined ? last.time : last.value[0];
            info.barData = {
                open:   last.value[1],
                high:   last.value[2],
                low:    last.value[3],
                close:  last.value[4],
                volume: last.value[5] || 0,
                time:   barTime,
                timestamp: new Date(barTime * 1000).toISOString()
            };
            info.totalBars = typeof bars.size === 'function' ? bars.size() : (bars._items ? bars._items.length : 1);
        } else {
            info.barError = "bars array empty or last() unavailable";
        }
    } catch(e) {
        info.barError = e.message;
    }
    return JSON.stringify(info);
})()
"""

try:
    ws_send(sock, json.dumps({
        "id": 2,
        "method": "Runtime.evaluate",
        "params": {"expression": PROBE_JS, "returnByValue": True, "awaitPromise": False},
    }))
    for _ in range(30):
        msg = json.loads(ws_recv(sock))
        if msg.get("id") == 2:
            value = msg.get("result", {}).get("result", {}).get("value")
            if value:
                info = json.loads(value)
                log.info("    Page title : %s", info.get("pageTitle"))
                log.info("    Page URL   : %s", info.get("pageUrl"))
                log.info("    TradingViewApi   present: %s", info.get("hasTradingViewApi"))
                log.info("    _activeChartWidgetWV     : %s", info.get("hasActiveChartWV"))
                log.info("    window.tvWidget  present: %s", info.get("hasTvWidget"))
                log.info("    window.TradingView ns    : %s", info.get("hasTVNamespace"))
                if "barData" in info:
                    bd = info["barData"]
                    log.info("    ✅ BAR DATA OK  — close=%.2f  high=%.2f  low=%.2f  bars=%s",
                             bd["close"], bd["high"], bd["low"], info.get("totalBars"))
                    log.info("    Timestamp: %s", bd.get("timestamp"))
                else:
                    log.error("    ❌ BAR DATA FAILED — %s", info.get("barError"))
            else:
                log.error("    JS returned no value. Full msg: %s", msg)
            break
    else:
        log.error("    FAIL — no response to Runtime.evaluate within 30 frames")
except Exception as e:
    log.error("    FAIL — %s", e)

sock.close()
log.info("=" * 60)
log.info("Diagnostic complete. Full log: %s", LOG_FILE)
log.info("=" * 60)
