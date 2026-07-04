# Check what page/tabs are available on CDP and what's on the current page
$ct = [System.Threading.CancellationToken]::None

# First: list all CDP targets
Write-Host "=== All CDP Targets ===" -ForegroundColor Cyan
try {
    $targets = Invoke-RestMethod -Uri "http://127.0.0.1:9222/json" -Method Get
    $targets | ForEach-Object {
        Write-Host ("ID={0} type={1} title={2}" -f $_.id, $_.type, $_.title)
        Write-Host ("  url={0}" -f $_.url)
    }
} catch {
    Write-Host "Error: $_"
}

Write-Host "`n=== Page Content Check on target 4123A93186AEEEEDC07E6EA7E533A921 ===" -ForegroundColor Cyan
$wsUrl = "ws://127.0.0.1:9222/devtools/page/4123A93186AEEEEDC07E6EA7E533A921"
$ws = New-Object System.Net.WebSockets.ClientWebSocket
$ws.ConnectAsync([Uri]$wsUrl, $ct).Wait()

function Eval-JS2 {
    param($id, $expr)
    $msg = @{id=$id; method="Runtime.evaluate"; params=@{expression=$expr; returnByValue=$true}} | ConvertTo-Json -Depth 5 -Compress
    $b = [System.Text.Encoding]::UTF8.GetBytes($msg)
    $ws.SendAsync([ArraySegment[byte]]$b, [System.Net.WebSockets.WebSocketMessageType]::Text, $true, $ct).Wait()
    $buf = [byte[]]::new(2097152)
    $r = $ws.ReceiveAsync([ArraySegment[byte]]$buf, $ct).Result
    return [System.Text.Encoding]::UTF8.GetString($buf, 0, $r.Count)
}

# Get URL and title
$urlResult = Eval-JS2 -id 1 -expr "JSON.stringify({url: location.href, title: document.title, readyState: document.readyState})"
Write-Host "Page info: $urlResult"

# Get all elements with class containing 'pine' or 'editor' or 'script'
$elemResult = Eval-JS2 -id 2 -expr @'
(function(){
  var all = Array.from(document.querySelectorAll("*"));
  var interesting = all.filter(function(el){
    var cls = el.className || "";
    if (typeof cls !== "string") return false;
    return cls.match(/pine|editor|script|code-editor|ace_|cm-/i);
  }).map(function(el){
    return {tag: el.tagName, cls: (el.className+"").substring(0,80), id: el.id};
  }).slice(0, 20);
  return JSON.stringify(interesting);
})()
'@
Write-Host "Interesting elements: $elemResult"

$ws.CloseAsync([System.Net.WebSockets.WebSocketCloseStatus]::NormalClosure, "done", $ct).Wait()
