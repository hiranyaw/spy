# Probe TradingView Pine editor state
$wsUrl = "ws://127.0.0.1:9222/devtools/page/4123A93186AEEEEDC07E6EA7E533A921"
$ct = [System.Threading.CancellationToken]::None
$ws = New-Object System.Net.WebSockets.ClientWebSocket
$ws.ConnectAsync([Uri]$wsUrl, $ct).Wait()

function Eval-JS {
    param($id, $expr)
    $msg = @{id=$id; method="Runtime.evaluate"; params=@{expression=$expr; returnByValue=$true}} | ConvertTo-Json -Depth 5 -Compress
    $b = [System.Text.Encoding]::UTF8.GetBytes($msg)
    $ws.SendAsync([ArraySegment[byte]]$b, [System.Net.WebSockets.WebSocketMessageType]::Text, $true, $ct).Wait()
    $buf = [byte[]]::new(2097152)
    $r = $ws.ReceiveAsync([ArraySegment[byte]]$buf, $ct).Result
    return [System.Text.Encoding]::UTF8.GetString($buf, 0, $r.Count)
}

$probe = @'
(function() {
  var info = {};
  info.hasMonaco = typeof monaco !== "undefined";
  if (info.hasMonaco) {
    info.editorCount = monaco.editor.getEditors().length;
    info.modelCount  = monaco.editor.getModels().length;
    info.models = monaco.editor.getModels().map(function(m){
      return {uri: m.uri.toString(), len: m.getValue().length, preview: m.getValue().substring(0,80)};
    });
  }
  info.tvPine  = typeof window.pine !== "undefined";
  info.tvEditor = typeof window.__editor !== "undefined";
  info.iframeCount = document.querySelectorAll("iframe").length;
  info.textareaCount = document.querySelectorAll(".monaco-editor textarea").length;
  info.allTextareas = Array.from(document.querySelectorAll("textarea")).map(function(t){
    return {display: getComputedStyle(t).display, len: t.value.length, cls: t.className.substring(0,60)};
  });
  // Look for React fibers or TV editor instances
  var editorEl = document.querySelector(".monaco-editor");
  if (editorEl) {
    var fiberKey = Object.keys(editorEl).find(function(k){return k.startsWith("__reactFiber") || k.startsWith("__reactInternalInstance");});
    info.hasEditorElement = true;
    info.editorFiberKey = fiberKey || "none";
  } else {
    info.hasEditorElement = false;
  }
  return JSON.stringify(info, null, 2);
})()
'@

$result = Eval-JS -id 1 -expr $probe
Write-Host $result

# Also try getting Monaco models via a different path
$probe2 = @'
(function(){
  // TV Pine editor is sometimes in an iframe - get iframe src list
  var iframes = Array.from(document.querySelectorAll("iframe"));
  return JSON.stringify(iframes.map(function(f){return {src: f.src, id: f.id, cls: f.className.substring(0,50)};}));
})()
'@
$result2 = Eval-JS -id 2 -expr $probe2
Write-Host "Iframes: $result2"

$ws.CloseAsync([System.Net.WebSockets.WebSocketCloseStatus]::NormalClosure, "done", $ct).Wait()
