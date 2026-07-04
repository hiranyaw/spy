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
    param([int]$bufSize = 131072)
    $buf = New-Object byte[] $bufSize
    $seg = New-Object System.ArraySegment[byte] -ArgumentList @(,$buf)
    $result = $ws.ReceiveAsync($seg, $ct).Result
    [System.Text.Encoding]::UTF8.GetString($buf, 0, $result.Count)
}

Write-Output "Connected: $($ws.State)"

# Deep diagnostic - find Monaco in iframes, check for pine editor classes
$deepDiag = @'
(function() {
  var out = [];
  
  // Check all iframes
  var iframes = document.querySelectorAll('iframe');
  out.push('Iframes: ' + iframes.length);
  for (var i = 0; i < iframes.length; i++) {
    try {
      var iw = iframes[i].contentWindow;
      if (iw && iw.monaco) {
        out.push('Monaco in iframe[' + i + ']: YES src=' + iframes[i].src.substring(0,60));
      } else {
        out.push('iframe[' + i + ']: no monaco, src=' + iframes[i].src.substring(0,60));
      }
    } catch(e) {
      out.push('iframe[' + i + ']: cross-origin error');
    }
  }
  
  // Look for editor DOM elements
  var editorDivs = document.querySelectorAll('.monaco-editor, .view-lines, [class*="pine-editor"], [class*="pineEditor"], [data-mode-id], .cm-editor');
  out.push('Monaco/CM editor divs: ' + editorDivs.length);
  if (editorDivs.length > 0) {
    out.push('First editor class: ' + editorDivs[0].className.substring(0, 100));
  }
  
  // Check for CodeMirror
  if (window.CodeMirror) out.push('CodeMirror: YES');
  
  // Check for ace editor
  if (window.ace) out.push('Ace: YES');
  
  // Check in frames for CodeMirror
  for (var f = 0; f < frames.length; f++) {
    try {
      if (frames[f].CodeMirror) out.push('CodeMirror in frame[' + f + ']');
      if (frames[f].monaco) out.push('Monaco in frame[' + f + ']');
    } catch(e) {}
  }
  
  // Look for textarea with pine code
  var textareas = document.querySelectorAll('textarea');
  out.push('Textareas: ' + textareas.length);
  
  // Get pine-related class names
  var allEls = document.querySelectorAll('[class*="Script"], [class*="script"], [class*="Pine"], [class*="pine"], [class*="code"], [class*="Code"]');
  out.push('Script/Pine/Code elements: ' + allEls.length);
  if (allEls.length > 0 && allEls.length < 20) {
    for (var e = 0; e < Math.min(5, allEls.length); e++) {
      out.push('  el[' + e + ']: ' + allEls[e].tagName + ' class=' + allEls[e].className.substring(0,80));
    }
  }
  
  return out.join('\n');
})()
'@

$req = '{"id":4,"method":"Runtime.evaluate","params":{"expression":' + ($deepDiag | ConvertTo-Json) + ',"returnByValue":true}}'
Send-CDP $req
Start-Sleep -Milliseconds 3000
$resp = Recv-CDP
Write-Output "DEEP_DIAG: $resp"

$ws.CloseAsync([System.Net.WebSockets.WebSocketCloseStatus]::NormalClosure, "done", $ct).Wait()
