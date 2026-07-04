Add-Type -AssemblyName System.Net.WebSockets
Add-Type -AssemblyName System.Threading

$wsUri = [System.Uri]"ws://localhost:9222/devtools/page/13215480F0305EE1EAA533B2A7ED681A"
$ct = [System.Threading.CancellationToken]::None

$ws = New-Object System.Net.WebSockets.ClientWebSocket
$ws.ConnectAsync($wsUri, $ct).Wait()

function Send-CDP {
    param([string]$json)
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($json)
    $seg = New-Object System.ArraySegment[byte] -ArgumentList @(,$bytes)
    $ws.SendAsync($seg, [System.Net.WebSockets.WebSocketMessageType]::Text, $true, $ct).Wait()
}

function Recv-CDP {
    param([int]$bufSize = 262144)
    $buf = New-Object byte[] $bufSize
    $seg = New-Object System.ArraySegment[byte] -ArgumentList @(,$buf)
    $result = $ws.ReceiveAsync($seg, $ct).Result
    [System.Text.Encoding]::UTF8.GetString($buf, 0, $result.Count)
}

Write-Output "Connected: $($ws.State)"

# Try to get Monaco via webpack modules or DOM editor instance
$monacoFind = @'
(function() {
  var out = [];
  
  // Try to find monaco via webpack require
  try {
    if (typeof require !== 'undefined') {
      var monaco = require('vs/editor/editor.main');
      if (monaco) { out.push('Found via require: vs/editor/editor.main'); window.__monaco = monaco; }
    }
  } catch(e) { out.push('require failed: ' + e.message); }
  
  // Try webpack chunk modules
  try {
    var wk = window.webpackChunktradingview || window.webpackChunks || window.__webpack_require__;
    if (wk) out.push('webpack: ' + typeof wk);
  } catch(e) {}
  
  // Try getting editor instance from DOM element
  var editorEl = document.querySelector('.monaco-editor.pine-editor-monaco');
  if (editorEl) {
    out.push('Found pine-editor-monaco DOM element');
    // Try to get editor instance from various properties
    var keys = Object.keys(editorEl).filter(function(k) { return k.startsWith('__') || k.includes('editor') || k.includes('monaco'); });
    out.push('Editor element props: ' + keys.slice(0, 10).join(', '));
    
    // Try _editorWidget
    if (editorEl._editorWidget) out.push('Has _editorWidget');
    
    // Look through all enumerable properties for editor-like objects
    for (var k in editorEl) {
      try {
        var v = editorEl[k];
        if (v && typeof v === 'object' && typeof v.getValue === 'function') {
          out.push('Found getValue() on property: ' + k);
          out.push('Current value (100 chars): ' + v.getValue().substring(0, 100));
        }
      } catch(e) {}
    }
  }
  
  // Try module exports via global
  var monacoKeys = Object.keys(window).filter(function(k) { 
    try { return window[k] && typeof window[k] === 'object' && window[k].editor && typeof window[k].editor.getModels === 'function'; } 
    catch(e) { return false; }
  });
  out.push('Monaco-like globals: ' + monacoKeys.join(', '));
  
  return out.join('\n');
})()
'@

$req = '{"id":5,"method":"Runtime.evaluate","params":{"expression":' + ($monacoFind | ConvertTo-Json) + ',"returnByValue":true}}'
Send-CDP $req
Start-Sleep -Milliseconds 3000
$resp = Recv-CDP
Write-Output "MONACO_FIND: $resp"

# Try accessing via the editor element's internal __reactFiber or similar
$reactFind = @'
(function() {
  var out = [];
  var editorEl = document.querySelector('.monaco-editor.pine-editor-monaco');
  if (!editorEl) { return 'No pine-editor-monaco found'; }
  
  // Get all property names including non-enumerable
  var allKeys = [];
  var proto = editorEl;
  while (proto && proto !== HTMLElement.prototype) {
    Object.getOwnPropertyNames(proto).forEach(function(k) { allKeys.push(k); });
    proto = Object.getPrototypeOf(proto);
    if (allKeys.length > 200) break;
  }
  out.push('Total own keys: ' + allKeys.length);
  
  // Filter interesting keys
  var interesting = allKeys.filter(function(k) { 
    return k.includes('editor') || k.includes('monaco') || k.includes('model') || k.startsWith('__') || k.includes('fiber') || k.includes('react');
  });
  out.push('Interesting keys: ' + interesting.slice(0, 20).join(', '));
  
  // Try editor container approach
  var container = editorEl.parentElement;
  if (container) {
    var cKeys = Object.keys(container).filter(function(k) { return k.includes('editor') || k.startsWith('__'); });
    out.push('Container keys: ' + cKeys.slice(0, 10).join(', '));
  }
  
  // Check textarea value inside editor
  var ta = editorEl.querySelector('textarea');
  if (ta) {
    out.push('Textarea found, value length: ' + ta.value.length);
    if (ta.value.length > 0) out.push('Textarea content: ' + ta.value.substring(0, 200));
  }
  
  return out.join('\n');
})()
'@

$req2 = '{"id":6,"method":"Runtime.evaluate","params":{"expression":' + ($reactFind | ConvertTo-Json) + ',"returnByValue":true}}'
Send-CDP $req2
Start-Sleep -Milliseconds 3000
$resp2 = Recv-CDP
Write-Output "REACT_FIND: $resp2"

$ws.CloseAsync([System.Net.WebSockets.WebSocketCloseStatus]::NormalClosure, "done", $ct).Wait()
