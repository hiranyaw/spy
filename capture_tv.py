# capture_tv.py
"""Utility to capture a TradingView chart screenshot using Chrome DevTools Protocol (CDP).
Requires Chrome to be started with `--remote-debugging-port=9222`.
"""
import os
import json
import base64
import time
import requests
import websocket

CHROME_DEBUG_PORT = int(os.getenv('CHROME_DEBUG_PORT', '9222'))

def _get_ws_url():
    """Retrieve the WebSocket debugging URL for the first open Chrome tab."""
    resp = requests.get(f'http://127.0.0.1:{CHROME_DEBUG_PORT}/json')
    tabs = resp.json()
    if not tabs:
        raise RuntimeError('No open Chrome tabs found')
    return tabs[0]['webSocketDebuggerUrl']

def _send_cmd(ws, method, params=None, id_=None):
    if params is None:
        params = {}
    if id_ is None:
        id_ = int(time.time() * 1000)
    ws.send(json.dumps({"id": id_, "method": method, "params": params}))
    while True:
        resp = json.loads(ws.recv())
        if resp.get('id') == id_:
            return resp

def capture_tradingview():
    """Capture a screenshot of the active tab (expected to be TradingView). Returns PNG bytes."""
    ws_url = _get_ws_url()
    ws = websocket.create_connection(ws_url)
    try:
        _send_cmd(ws, 'Page.enable')
        result = _send_cmd(ws, 'Page.captureScreenshot', {"format": "png", "quality": 100})
        data = result.get('result', {}).get('data')
        if not data:
            raise RuntimeError('No screenshot data returned')
        return base64.b64decode(data)
    finally:
        ws.close()

def save_image(image_bytes, path):
    """Save PNG bytes to a file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(image_bytes)

if __name__ == '__main__':
    img = capture_tradingview()
    save_image(img, os.path.join('snapshots', f'tv_{int(time.time())}.png'))
    print('Screenshot saved')
