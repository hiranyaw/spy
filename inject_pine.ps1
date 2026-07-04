# Pine Script injector - FINAL VERSION
# Uses exact proven WebSocket pattern + chunk upload + ClipboardEvent paste

param(
    [string]$WsUrl = "ws://127.0.0.1:9222/devtools/page/4123A93186AEEEEDC07E6EA7E533A921"
)

$ct = [System.Threading.CancellationToken]::None

# The EXACT proven receive pattern from original working example
function Recv {
    param($ws)
    $buf = [byte[]]::new(65536)
    $result = $ws.ReceiveAsync([ArraySegment[byte]]$buf, $ct).Result
    return [System.Text.Encoding]::UTF8.GetString($buf, 0, $result.Count)
}

function CDPEval {
    param($ws, $id, [string]$expr)
    $exprJson = $expr | ConvertTo-Json
    $msg = "{`"id`":$id,`"method`":`"Runtime.evaluate`",`"params`":{`"expression`":$exprJson,`"returnByValue`":true}}"
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($msg)
    $ws.SendAsync([ArraySegment[byte]]$bytes, [System.Net.WebSockets.WebSocketMessageType]::Text, $true, $ct).Wait()
    return Recv $ws
}

# ── CONNECT ──────────────────────────────────────────────────────────────────
Write-Host "[0] Connecting..." -ForegroundColor Cyan
$ws = New-Object System.Net.WebSockets.ClientWebSocket
$ws.ConnectAsync([Uri]$WsUrl, $ct).Wait()
Write-Host "    State=$($ws.State)" -ForegroundColor Green

# ── ENSURE PINE EDITOR IS OPEN ───────────────────────────────────────────────
Write-Host "[1] Opening Pine editor..." -ForegroundColor Cyan
$r1 = CDPEval $ws 1 @'
(function(){
  if (document.querySelector(".monaco-editor textarea.inputarea")) return "already-open";
  var btn = document.querySelector('button[aria-label*="Pine"]')
         || document.querySelector('[data-name="pine-editor"]');
  if (btn) { btn.click(); return "clicked-open"; }
  return "not-found";
})()
'@
Write-Host "    $r1" -ForegroundColor Yellow
Start-Sleep -Milliseconds 2000

# ── INIT GLOBAL ACCUMULATOR ───────────────────────────────────────────────────
Write-Host "[2] Initializing code buffer..." -ForegroundColor Cyan
$r2 = CDPEval $ws 2 "window.__pc = ''; 'ok'"
Write-Host "    $r2" -ForegroundColor Yellow

# ── UPLOAD PINE CODE IN SMALL CHUNKS ─────────────────────────────────────────
Write-Host "[3] Uploading Pine code in chunks..." -ForegroundColor Cyan

$pineScript = @'
//@version=6
indicator("Trendlines with Breaks [LuxAlgo] - Count Tracker v1.4", "B Counter v1.4", overlay=true)

//------------------------------------------------------------------------------
//Settings
//-----------------------------------------------------------------------------{
length = input.int(14, 'Swing Detection Lookback')
mult = input.float(1., 'Slope', minval=0, step=.1)
calcMethod = input.string('Atr', 'Slope Calculation Method', options=['Atr','Stdev','Linreg'])
backpaint = input(true, tooltip='Backpainting offset displayed elements in the past. Disable backpainting to see real time information returned by the indicator.')

//Style
upCss = input.color(color.teal, 'Up Trendline Color', group='Style')
dnCss = input.color(color.red, 'Down Trendline Color', group='Style')
showExt = input(true, 'Show Extended Lines')

//Display Settings
group_box    = "BOX SETTINGS"
show_box     = input(true,  "Show Counter Box",     group=group_box)
show_details = input(true,  "Show Details Panel",   group=group_box, tooltip="Shows full break history panel on the left side of the chart.")
box_width    = input.int(70, "Box Cell Width",  group=group_box, minval=10, maxval=150)
box_height   = input.int(30, "Box Cell Height", group=group_box, minval=5,  maxval=60)
box_color_bg  = input.color(color.new(color.blue, 50), "Box Header Color", group=group_box)
box_color_val = input.color(color.new(color.blue, 70), "Box Value Color",  group=group_box)

//Reset Button (toggle ON to reset, then toggle OFF)
group_reset  = "RESET"
manual_reset = input(false, "Reset B Count  (toggle ON to OFF)", group=group_reset, tooltip="Toggle this checkbox ON to instantly clear the B Count and history, then toggle it back OFF.")

//History Settings
group_hist   = "HISTORY SETTINGS"
history_size = input.int(20, "Max Breaks to Show", group=group_hist, minval=5, maxval=50)

//-----------------------------------------------------------------------------}
//Calculations
//-----------------------------------------------------------------------------{
var upper = 0.
var lower = 0.
var slope_ph = 0.
var slope_pl = 0.

var offset = backpaint ? length : 0

n = bar_index
src = close

ph = ta.pivothigh(src, length, length)
pl = ta.pivotlow(src, length, length)

//Slope Calculation Method
slope = switch calcMethod
    'Atr'    => ta.atr(length) / length * mult
    'Stdev'  => ta.stdev(src,length) / length * mult
    'Linreg' => math.abs(ta.sma(src * n, length) - ta.sma(src, length) * ta.sma(n, length)) / ta.variance(n, length) / 2 * mult

//Get slopes and calculate trendlines
if not na(ph)
    slope_ph := slope
if not na(pl)
    slope_pl := slope

if not na(ph)
    upper := ph
else
    upper := upper - slope_ph

if not na(pl)
    lower := pl
else
    lower := lower + slope_pl

var upos = 0
var dnos = 0

if not na(ph)
    upos := 0
else if close > upper - slope_ph * length
    upos := 1

if not na(pl)
    dnos := 0
else if close < lower + slope_pl * length
    dnos := 1

//Break Detection
break_up = upos > upos[1]
break_dn = dnos > dnos[1]

//-----------------------------------------------------------------------------}
//Extended Lines
//-----------------------------------------------------------------------------{
var uptl = line.new(na,na,na,na, color=upCss, style=line.style_dashed, extend=extend.right)
var dntl = line.new(na,na,na,na, color=dnCss, style=line.style_dashed, extend=extend.right)

if not na(ph) and showExt
    uptl.set_xy1(n-offset, backpaint ? ph : upper - slope_ph * length)
    uptl.set_xy2(n-offset+1, backpaint ? ph - slope : upper - slope_ph * (length+1))

if not na(pl) and showExt
    dntl.set_xy1(n-offset, backpaint ? pl : lower + slope_pl * length)
    dntl.set_xy2(n-offset+1, backpaint ? pl + slope : lower + slope_pl * (length+1))

//-----------------------------------------------------------------------------}
//Plots
//-----------------------------------------------------------------------------{
plot(backpaint ? upper : upper - slope_ph * length, 'Upper', color=upCss, offset=-offset)
plot(backpaint ? lower : lower + slope_pl * length, 'Lower', color=dnCss, offset=-offset)

//Breakouts with B labels
plotshape(break_up ? low : na, "Upper Break"
  , shape.labelup
  , location.absolute
  , upCss
  , text="B"
  , textcolor=color.white
  , size=size.tiny)

plotshape(break_dn ? high : na, "Lower Break"
  , shape.labeldown
  , location.absolute
  , dnCss
  , text="B"
  , textcolor=color.white
  , size=size.tiny)

//-----------------------------------------------------------------------------}
//Counter Logic
//-----------------------------------------------------------------------------{
// Time window: 6:25 AM - 9:00 AM (in exchange timezone)
// TradingView hour/minute use exchange time (ET for US markets)
window_start_h = 6
window_start_m = 25
window_end_h   = 9
window_end_m   = 0

current_mins = hour * 60 + minute
window_start_mins = window_start_h * 60 + window_start_m  // 385 mins = 6:25
window_end_mins   = window_end_h   * 60 + window_end_m    // 540 mins = 9:00

in_window = current_mins >= window_start_mins and current_mins < window_end_mins

var int total_count = 0
var int long_count  = 0
var int short_count = 0
var array<string> break_times  = array.new<string>()
var array<string> break_dirs   = array.new<string>()
var array<float>  break_prices = array.new<float>()

// Manual reset via toggle input
if manual_reset
    total_count := 0
    long_count  := 0
    short_count := 0
    array.clear(break_times)
    array.clear(break_dirs)
    array.clear(break_prices)

// Daily reset at 6:25 AM
var bool reset_done = false
if current_mins == window_start_mins
    if not reset_done
        total_count := 0
        long_count  := 0
        short_count := 0
        array.clear(break_times)
        array.clear(break_dirs)
        array.clear(break_prices)
        reset_done := true
else
    reset_done := false

// Only count breaks inside the 6:25 AM - 9:00 AM window
if (break_up or break_dn) and in_window
    total_count += 1

    // Track LONG vs SHORT separately
    if break_up
        long_count  += 1
    else
        short_count += 1

    // Get current time
    hr         = str.tostring(hour)
    mn         = str.tostring(minute, "00")
    break_time = hr + ":" + mn
    break_dir  = break_up ? "LONG" : "SHORT"
    break_price = close

    // Store in arrays (newest first)
    array.unshift(break_times,  break_time)
    array.unshift(break_dirs,   break_dir)
    array.unshift(break_prices, break_price)

    if array.size(break_times) > history_size
        array.pop(break_times)
        array.pop(break_dirs)
        array.pop(break_prices)

//-----------------------------------------------------------------------------}
//Counter Box - TOP RIGHT
//-----------------------------------------------------------------------------{
if show_box
    var table counter_box = na

    if na(counter_box)
        counter_box := table.new(position.top_right, 2, 4,
            bgcolor=color.new(color.black, 25),
            border_color=color.gray,
            border_width=2)

    // Row 0 - Header
    table.cell(counter_box, 0, 0, "B COUNT", text_size=size.small, text_color=color.white,
        bgcolor=box_color_bg, width=box_width, height=box_height)
    table.cell(counter_box, 1, 0, str.tostring(total_count), text_size=size.large, text_color=color.yellow,
        bgcolor=box_color_val, width=box_width, height=box_height)

    // Row 1 - LONG count
    table.cell(counter_box, 0, 1, "LONG", text_size=size.small, text_color=color.white,
        bgcolor=color.new(color.green, 55), width=box_width, height=box_height - 5)
    table.cell(counter_box, 1, 1, str.tostring(long_count), text_size=size.small, text_color=color.lime,
        bgcolor=color.new(color.green, 70), width=box_width, height=box_height - 5)

    // Row 2 - SHORT count
    table.cell(counter_box, 0, 2, "SHORT", text_size=size.small, text_color=color.white,
        bgcolor=color.new(color.red, 55), width=box_width, height=box_height - 5)
    table.cell(counter_box, 1, 2, str.tostring(short_count), text_size=size.small, text_color=color.red,
        bgcolor=color.new(color.red, 70), width=box_width, height=box_height - 5)

    // Row 3 - Last Break direction + time
    last_time  = array.size(break_times) > 0 ? array.get(break_times, 0) : "--:--"
    last_dir   = array.size(break_dirs)  > 0 ? array.get(break_dirs,  0) : "--"
    last_color = last_dir == "LONG" ? color.new(color.green, 55) : (last_dir == "SHORT" ? color.new(color.red, 55) : color.new(color.gray, 55))
    table.cell(counter_box, 0, 3, last_time, text_size=size.tiny, text_color=color.white,
        bgcolor=color.new(color.gray, 50), width=box_width, height=box_height - 8)
    table.cell(counter_box, 1, 3, last_dir,  text_size=size.tiny, text_color=color.white,
        bgcolor=last_color, width=box_width, height=box_height - 8)

//-----------------------------------------------------------------------------}
//Details Panel - BOTTOM LEFT (always visible when show_details = true)
//-----------------------------------------------------------------------------{
if show_details
    var table details = na

    if na(details)
        details := table.new(position.bottom_left, 4, history_size + 2,
            bgcolor=color.new(color.black, 20),
            border_color=color.new(color.gray, 30),
            border_width=1,
            frame_color=color.new(color.blue, 20),
            frame_width=2)

    // Title row
    table.cell(details, 0, 0, "B BREAK HISTORY", text_size=size.small, text_color=color.yellow,
        bgcolor=color.new(color.navy, 20), width=40, height=22, colspan=4)

    // Column headers
    table.cell(details, 0, 1, "#",     text_size=size.tiny, text_color=color.white, bgcolor=color.new(color.blue, 40), width=28,  height=20)
    table.cell(details, 1, 1, "TIME",  text_size=size.tiny, text_color=color.white, bgcolor=color.new(color.blue, 40), width=55,  height=20)
    table.cell(details, 2, 1, "DIR",   text_size=size.tiny, text_color=color.white, bgcolor=color.new(color.blue, 40), width=55,  height=20)
    table.cell(details, 3, 1, "PRICE", text_size=size.tiny, text_color=color.white, bgcolor=color.new(color.blue, 40), width=70,  height=20)

    // Data rows
    n_breaks = array.size(break_times)
    max_rows = math.min(n_breaks, history_size)

    for i = 0 to history_size - 1
        row = i + 2
        if i < max_rows
            dir_str   = array.get(break_dirs,   i)
            time_str  = array.get(break_times,  i)
            price_val = array.get(break_prices, i)
            price_str = str.tostring(math.round(price_val * 100) / 100)
            row_num   = str.tostring(n_breaks - i)

            is_long   = dir_str == "LONG"
            dir_bg    = is_long ? color.new(color.green, 55) : color.new(color.red, 55)
            dir_fg    = is_long ? color.lime                 : color.red
            row_bg    = i == 0 ? color.new(color.white, 75) : color.new(color.gray, 55)

            table.cell(details, 0, row, row_num,    text_size=size.tiny, text_color=color.white, bgcolor=row_bg,   width=28, height=19)
            table.cell(details, 1, row, time_str,   text_size=size.tiny, text_color=color.white, bgcolor=row_bg,   width=55, height=19)
            table.cell(details, 2, row, dir_str,    text_size=size.tiny, text_color=dir_fg,      bgcolor=dir_bg,   width=55, height=19)
            table.cell(details, 3, row, price_str,  text_size=size.tiny, text_color=color.white, bgcolor=row_bg,   width=70, height=19)
        else
            empty_bg = color.new(color.gray, 75)
            table.cell(details, 0, row, "", text_size=size.tiny, text_color=color.white, bgcolor=empty_bg, width=28, height=19)
            table.cell(details, 1, row, "", text_size=size.tiny, text_color=color.white, bgcolor=empty_bg, width=55, height=19)
            table.cell(details, 2, row, "", text_size=size.tiny, text_color=color.white, bgcolor=empty_bg, width=55, height=19)
            table.cell(details, 3, row, "", text_size=size.tiny, text_color=color.white, bgcolor=empty_bg, width=70, height=19)

//-----------------------------------------------------------------------------}
//Alerts
//-----------------------------------------------------------------------------{
alertcondition(break_up, 'Upward Breakout', 'Price broke the down-trendline upward')
alertcondition(break_dn, 'Downward Breakout', 'Price broke the up-trendline downward')

//-----------------------------------------------------------------------------}
'@

$chunkSize = 500
$totalChars = $pineScript.Length
$numChunks = [math]::Ceiling($totalChars / $chunkSize)
Write-Host "    Total $totalChars chars, uploading $numChunks chunks..." -ForegroundColor Gray

for ($i = 0; $i -lt $numChunks; $i++) {
    $start = $i * $chunkSize
    $len = [math]::Min($chunkSize, $totalChars - $start)
    $chunk = $pineScript.Substring($start, $len)
    $chunkJson = $chunk | ConvertTo-Json
    $appendExpr = "window.__pc += $chunkJson; $i"
    $r = CDPEval $ws (200 + $i) $appendExpr
    if ($i % 10 -eq 0) { Write-Host "    Chunk $($i+1)/$numChunks..." -ForegroundColor Gray }
}

# Verify stored length
$r3 = CDPEval $ws 300 "window.__pc.length"
Write-Host "    Stored chars: $r3" -ForegroundColor Yellow

# ── INJECT VIA ClipboardEvent ─────────────────────────────────────────────────
Write-Host "[4] Injecting via ClipboardEvent paste..." -ForegroundColor Cyan
$r4 = CDPEval $ws 400 @'
(function(){
  try {
    var code = window.__pc;
    if (!code || code.length < 50) return "ERROR: no code. len=" + (code||"").length;
    var ta = document.querySelector(".monaco-editor textarea.inputarea")
          || document.querySelector(".monaco-editor textarea");
    if (!ta) return "ERROR: no textarea";
    ta.focus();
    ta.click();
    // Dispatch paste event with DataTransfer
    var dt = new DataTransfer();
    dt.setData("text/plain", code);
    ta.dispatchEvent(new ClipboardEvent("paste", {bubbles:true, cancelable:true, clipboardData:dt}));
    return "paste-dispatched code=" + code.length + " ta.value=" + ta.value.length;
  } catch(e) { return "ERROR: " + e.message; }
})()
'@
Write-Host "    $r4" -ForegroundColor Yellow
Start-Sleep -Milliseconds 500

# ── VERIFY ────────────────────────────────────────────────────────────────────
Write-Host "[5] Verifying..." -ForegroundColor Cyan
$r5 = CDPEval $ws 500 @'
(function(){
  var ta = document.querySelector(".monaco-editor textarea.inputarea")||document.querySelector(".monaco-editor textarea");
  if (!ta) return "no-ta";
  return "ta.value.length=" + ta.value.length + " preview=" + ta.value.substring(0,40);
})()
'@
Write-Host "    $r5" -ForegroundColor Yellow
Start-Sleep -Milliseconds 200

# ── SAVE with Ctrl+S ──────────────────────────────────────────────────────────
Write-Host "[6] Saving..." -ForegroundColor Cyan

# Focus textarea
$r6a = CDPEval $ws 600 @'
(function(){
  var ta = document.querySelector(".monaco-editor textarea.inputarea")||document.querySelector(".monaco-editor textarea");
  if (ta) { ta.focus(); return "focused"; }
  return "no-ta";
})()
'@
Write-Host "    Focus: $r6a" -ForegroundColor Gray

# Send Ctrl+S
$ctrlSDown = "{`"id`":601,`"method`":`"Input.dispatchKeyEvent`",`"params`":{`"type`":`"keyDown`",`"modifiers`":2,`"key`":`"s`",`"code`":`"KeyS`",`"windowsVirtualKeyCode`":83,`"nativeVirtualKeyCode`":83}}"
$b = [System.Text.Encoding]::UTF8.GetBytes($ctrlSDown)
$ws.SendAsync([ArraySegment[byte]]$b, [System.Net.WebSockets.WebSocketMessageType]::Text, $true, $ct).Wait()
$buf = [byte[]]::new(65536)
$r = $ws.ReceiveAsync([ArraySegment[byte]]$buf, $ct).Result
$r6b = [System.Text.Encoding]::UTF8.GetString($buf, 0, $r.Count)
Write-Host "    Ctrl+S down: $r6b" -ForegroundColor Yellow

Start-Sleep -Milliseconds 150

$ctrlSUp = "{`"id`":602,`"method`":`"Input.dispatchKeyEvent`",`"params`":{`"type`":`"keyUp`",`"modifiers`":2,`"key`":`"s`",`"code`":`"KeyS`",`"windowsVirtualKeyCode`":83,`"nativeVirtualKeyCode`":83}}"
$b2 = [System.Text.Encoding]::UTF8.GetBytes($ctrlSUp)
$ws.SendAsync([ArraySegment[byte]]$b2, [System.Net.WebSockets.WebSocketMessageType]::Text, $true, $ct).Wait()
$buf2 = [byte[]]::new(65536)
$r2 = $ws.ReceiveAsync([ArraySegment[byte]]$buf2, $ct).Result
$r6c = [System.Text.Encoding]::UTF8.GetString($buf2, 0, $r2.Count)
Write-Host "    Ctrl+S up: $r6c" -ForegroundColor Yellow
Start-Sleep -Milliseconds 400

Start-Sleep -Milliseconds 1000

# ── CLICK "ADD TO CHART" ──────────────────────────────────────────────────────
Write-Host "[7] Clicking Add to chart..." -ForegroundColor Cyan
$r7 = CDPEval $ws 700 @'
(function() {
  var btns = Array.from(document.querySelectorAll('button, [role="button"], [class*="Button"]'));
  var addBtn = btns.find(function(b) {
    var t = (b.innerText || b.textContent || b.getAttribute("aria-label") || "").toLowerCase();
    return t.includes("add to chart") || t.includes("apply") || t.includes("add to active");
  });
  if (addBtn) { addBtn.click(); return "Clicked: " + (addBtn.innerText || addBtn.getAttribute("aria-label")); }
  
  var ariaBtn = document.querySelector('[aria-label*="Add to chart"], [aria-label*="add to chart"]');
  if (ariaBtn) { ariaBtn.click(); return "Clicked aria: " + ariaBtn.getAttribute("aria-label"); }
  
  return "Add to chart not found. Buttons: " + btns.slice(0,15).map(function(b){return (b.innerText||b.getAttribute("aria-label")||"").trim().substring(0,25);}).join(" | ");
})()
'@
Write-Host "    $r7" -ForegroundColor Yellow
Start-Sleep -Milliseconds 500

$ws.CloseAsync([System.Net.WebSockets.WebSocketCloseStatus]::NormalClosure, "done", $ct).Wait()
Write-Host "`n[DONE]" -ForegroundColor Green
