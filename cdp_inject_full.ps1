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
    param([int]$bufSize = 524288)
    $buf = New-Object byte[] $bufSize
    $seg = New-Object System.ArraySegment[byte] -ArgumentList @(,$buf)
    $result = $ws.ReceiveAsync($seg, $ct).Result
    [System.Text.Encoding]::UTF8.GetString($buf, 0, $result.Count)
}

Write-Output "Connected: $($ws.State)"

# Build injection approach: find monaco via webpack + use textarea + react fiber approach
$pineLines = @(
    '//@version=6',
    'indicator("Trendlines with Breaks [LuxAlgo] - Count Tracker", "B Counter", overlay=true)',
    '',
    '//------------------------------------------------------------------------------',
    '//Settings',
    '//-----------------------------------------------------------------------------{',
    "length = input.int(14, 'Swing Detection Lookback')",
    "mult = input.float(1., 'Slope', minval=0, step=.1)",
    "calcMethod = input.string('Atr', 'Slope Calculation Method', options=['Atr','Stdev','Linreg'])",
    "backpaint = input(true, tooltip='Backpainting offset displayed elements in the past. Disable backpainting to see real time information returned by the indicator.')",
    '',
    '//Style',
    "upCss = input.color(color.teal, 'Up Trendline Color', group='Style')",
    "dnCss = input.color(color.red, 'Down Trendline Color', group='Style')",
    "showExt = input(true, 'Show Extended Lines')",
    '',
    '//Display Settings',
    'group_box = "BOX SETTINGS"',
    'show_box = input(true, "Show Counter Box", group=group_box)',
    'show_history = input(false, "Show Full History", group=group_box)',
    'box_width = input.int(70, "Box Cell Width", group=group_box, minval=10, maxval=150)',
    'box_height = input.int(30, "Box Cell Height", group=group_box, minval=5, maxval=60)',
    'box_color_bg = input.color(color.new(color.blue, 50), "Box Header Color", group=group_box)',
    'box_color_val = input.color(color.new(color.blue, 70), "Box Value Color", group=group_box)',
    '',
    '//History Settings',
    'group_hist = "HISTORY SETTINGS"',
    'history_size = input.int(15, "History Size", group=group_hist, minval=5, maxval=30)',
    '',
    '//-----------------------------------------------------------------------------}',
    '//Calculations',
    '//-----------------------------------------------------------------------------{',
    'var upper = 0.',
    'var lower = 0.',
    'var slope_ph = 0.',
    'var slope_pl = 0.',
    '',
    'var offset = backpaint ? length : 0',
    '',
    'n = bar_index',
    'src = close',
    '',
    'ph = ta.pivothigh(src, length, length)',
    'pl = ta.pivotlow(src, length, length)',
    '',
    '//Slope Calculation Method',
    'slope = switch calcMethod',
    "    'Atr'    => ta.atr(length) / length * mult",
    "    'Stdev'  => ta.stdev(src,length) / length * mult",
    "    'Linreg' => math.abs(ta.sma(src * n, length) - ta.sma(src, length) * ta.sma(n, length)) / ta.variance(n, length) / 2 * mult",
    '',
    '//Get slopes and calculate trendlines',
    'if not na(ph)',
    '    slope_ph := slope',
    'if not na(pl)',
    '    slope_pl := slope',
    '',
    'if not na(ph)',
    '    upper := ph',
    'else',
    '    upper := upper - slope_ph',
    '',
    'if not na(pl)',
    '    lower := pl',
    'else',
    '    lower := lower + slope_pl',
    '',
    'var upos = 0',
    'var dnos = 0',
    '',
    'if not na(ph)',
    '    upos := 0',
    'else if close > upper - slope_ph * length',
    '    upos := 1',
    '',
    'if not na(pl)',
    '    dnos := 0',
    'else if close < lower + slope_pl * length',
    '    dnos := 1',
    '',
    '//Break Detection',
    'break_up = upos > upos[1]',
    'break_dn = dnos > dnos[1]',
    '',
    '//-----------------------------------------------------------------------------}',
    '//Extended Lines',
    '//-----------------------------------------------------------------------------{',
    'var uptl = line.new(na,na,na,na, color=upCss, style=line.style_dashed, extend=extend.right)',
    'var dntl = line.new(na,na,na,na, color=dnCss, style=line.style_dashed, extend=extend.right)',
    '',
    'if not na(ph) and showExt',
    '    uptl.set_xy1(n-offset, backpaint ? ph : upper - slope_ph * length)',
    '    uptl.set_xy2(n-offset+1, backpaint ? ph - slope : upper - slope_ph * (length+1))',
    '',
    'if not na(pl) and showExt',
    '    dntl.set_xy1(n-offset, backpaint ? pl : lower + slope_pl * length)',
    '    dntl.set_xy2(n-offset+1, backpaint ? pl + slope : lower + slope_pl * (length+1))',
    '',
    '//-----------------------------------------------------------------------------}',
    '//Plots',
    '//-----------------------------------------------------------------------------{',
    "plot(backpaint ? upper : upper - slope_ph * length, 'Upper', color=upCss, offset=-offset)",
    "plot(backpaint ? lower : lower + slope_pl * length, 'Lower', color=dnCss, offset=-offset)",
    '',
    '//Breakouts with B labels',
    'plotshape(break_up ? low : na, "Upper Break"',
    '  , shape.labelup',
    '  , location.absolute',
    '  , upCss',
    '  , text="B"',
    '  , textcolor=color.white',
    '  , size=size.tiny)',
    '',
    'plotshape(break_dn ? high : na, "Lower Break"',
    '  , shape.labeldown',
    '  , location.absolute',
    '  , dnCss',
    '  , text="B"',
    '  , textcolor=color.white',
    '  , size=size.tiny)',
    '',
    '//-----------------------------------------------------------------------------}',
    '//Counter Logic',
    '//-----------------------------------------------------------------------------{',
    'var int total_count = 0',
    'var array<string> break_times = array.new<string>()',
    'var array<string> break_dirs = array.new<string>()',
    'var array<float> break_prices = array.new<float>()',
    '',
    'if break_up or break_dn',
    '    total_count += 1',
    '',
    '    // Get current time',
    '    hr = str.tostring(hour)',
    '    mn = str.tostring(minute, "00")',
    '    break_time = hr + ":" + mn',
    '    break_dir = break_up ? "LONG" : "SHORT"',
    '    break_price = close',
    '',
    '    // Store in arrays',
    '    array.unshift(break_times, break_time)',
    '    array.unshift(break_dirs, break_dir)',
    '    array.unshift(break_prices, break_price)',
    '',
    '    if array.size(break_times) > history_size',
    '        array.pop(break_times)',
    '        array.pop(break_dirs)',
    '        array.pop(break_prices)',
    '',
    '// Daily reset',
    'if dayofweek == dayofweek.monday or (hour == 0 and minute == 0)',
    '    total_count := 0',
    '',
    '//-----------------------------------------------------------------------------}',
    '//Counter Box - TOP RIGHT',
    '//-----------------------------------------------------------------------------{',
    'if show_box',
    '    var table counter_box = na',
    '',
    '    if na(counter_box)',
    '        counter_box := table.new(position.top_right, 2, 2,',
    '            bgcolor=color.new(color.black, 30),',
    '            border_color=color.gray,',
    '            border_width=2)',
    '',
    '    // Row 0 - Count',
    '    table.cell(counter_box, 0, 0, "B COUNT", text_size=size.small, text_color=color.white,',
    '        bgcolor=box_color_bg, width=box_width, height=box_height)',
    '',
    '    table.cell(counter_box, 1, 0, str.tostring(total_count), text_size=size.small, text_color=color.yellow,',
    '        bgcolor=box_color_val, width=box_width, height=box_height)',
    '',
    '    // Row 1 - Last Break',
    "    last_time = array.size(break_times) > 0 ? array.get(break_times, 0) : `"\u2014`"",
    "    last_dir = array.size(break_dirs) > 0 ? array.get(break_dirs, 0) : `"\u2014`"",
    '    last_color = last_dir == "LONG" ? color.new(color.green, 70) : (last_dir == "SHORT" ? color.new(color.red, 70) : color.new(color.gray, 70))',
    '',
    '    table.cell(counter_box, 0, 1, last_time, text_size=size.tiny, text_color=color.white,',
    '        bgcolor=color.new(color.gray, 50), width=box_width, height=box_height-5)',
    '',
    '    table.cell(counter_box, 1, 1, last_dir, text_size=size.tiny, text_color=color.white,',
    '        bgcolor=last_color, width=box_width, height=box_height-5)',
    '',
    '//-----------------------------------------------------------------------------}',
    '//History Table - DETAILED',
    '//-----------------------------------------------------------------------------{',
    'if show_history and array.size(break_times) > 0',
    '    var table history_table = na',
    '',
    '    if na(history_table)',
    '        history_table := table.new(position.middle_center, 4, history_size + 1,',
    '            bgcolor=color.new(color.black, 20),',
    '            border_color=color.gray,',
    '            border_width=2)',
    '',
    '    // Header',
    '    table.cell(history_table, 0, 0, "#", text_size=size.small, text_color=color.white, bgcolor=color.new(color.blue, 50), width=40, height=25)',
    '    table.cell(history_table, 1, 0, "TIME", text_size=size.small, text_color=color.white, bgcolor=color.new(color.blue, 50), width=70, height=25)',
    '    table.cell(history_table, 2, 0, "DIR", text_size=size.small, text_color=color.white, bgcolor=color.new(color.blue, 50), width=70, height=25)',
    '    table.cell(history_table, 3, 0, "PRICE", text_size=size.small, text_color=color.white, bgcolor=color.new(color.blue, 50), width=80, height=25)',
    '',
    '    // History rows',
    '    for i = 0 to math.min(array.size(break_times) - 1, history_size - 1)',
    '        idx = i + 1',
    '        time_str = array.get(break_times, i)',
    '        dir_str = array.get(break_dirs, i)',
    '        price_str = str.tostring(math.round(array.get(break_prices, i) * 100) / 100)',
    '',
    '        dir_color = dir_str == "LONG" ? color.new(color.green, 70) : color.new(color.red, 70)',
    '        dir_text = dir_str == "LONG" ? color.lime : color.red',
    '',
    '        // Index column',
    '        table.cell(history_table, 0, idx, str.tostring(idx), text_size=size.tiny, text_color=color.white,',
    '            bgcolor=color.new(color.gray, 40), width=40, height=20)',
    '',
    '        // Time column',
    '        table.cell(history_table, 1, idx, time_str, text_size=size.tiny, text_color=color.white,',
    '            bgcolor=color.new(color.gray, 40), width=70, height=20)',
    '',
    '        // Direction column',
    '        table.cell(history_table, 2, idx, dir_str, text_size=size.tiny, text_color=dir_text,',
    '            bgcolor=dir_color, width=70, height=20)',
    '',
    '        // Price column',
    '        table.cell(history_table, 3, idx, price_str, text_size=size.tiny, text_color=color.white,',
    '            bgcolor=color.new(color.gray, 40), width=80, height=20)',
    '',
    '//-----------------------------------------------------------------------------}',
    '//Alerts',
    '//-----------------------------------------------------------------------------{',
    "alertcondition(break_up, 'Upward Breakout', 'Price broke the down-trendline upward')",
    "alertcondition(break_dn, 'Downward Breakout', 'Price broke the up-trendline downward')",
    '',
    '//-----------------------------------------------------------------------------}'
)

$pineCode = $pineLines -join "`n"
$pineJson = $pineCode | ConvertTo-Json

# Injection via webpack + React approach
$injectJs = @"
(function() {
  var pineCode = $pineJson;
  var out = [];
  
  // APPROACH 1: Try webpack require to get monaco
  try {
    var allChunks = [];
    if (window.webpackChunktradingview) {
      out.push('webpackChunktradingview found, len=' + window.webpackChunktradingview.length);
    }
    
    // Try to get require from webpack
    var wpRequire = null;
    if (window.__webpack_require__) {
      wpRequire = window.__webpack_require__;
      out.push('__webpack_require__ found');
    }
    
    // Scan module cache for monaco
    if (wpRequire && wpRequire.c) {
      var keys = Object.keys(wpRequire.c);
      out.push('Module cache size: ' + keys.length);
      var monacoMod = null;
      for (var i = 0; i < keys.length; i++) {
        var mod = wpRequire.c[keys[i]];
        if (mod && mod.exports && mod.exports.editor && typeof mod.exports.editor.getModels === 'function') {
          monacoMod = mod.exports;
          out.push('Found monaco in module: ' + keys[i]);
          break;
        }
      }
      if (monacoMod) {
        var models = monacoMod.editor.getModels();
        out.push('Models: ' + models.length);
        if (models.length > 0) {
          var model = models[0];
          model.setValue(pineCode);
          out.push('SUCCESS via webpack module: Set ' + pineCode.length + ' chars');
          return out.join(' | ');
        }
      }
    }
  } catch(e) {
    out.push('webpack approach error: ' + e.message);
  }
  
  // APPROACH 2: React fiber to get editor instance
  try {
    var editorContainer = document.querySelector('.monaco-editor.pine-editor-monaco');
    if (editorContainer) {
      var parent = editorContainer.parentElement;
      var fiberKey = Object.keys(parent).find(function(k) { return k.startsWith('__reactFiber'); });
      if (fiberKey) {
        var fiber = parent[fiberKey];
        out.push('React fiber found');
        // Walk fiber tree to find editor instance
        var node = fiber;
        var depth = 0;
        while (node && depth < 30) {
          if (node.stateNode && node.stateNode.editor && typeof node.stateNode.editor.setValue === 'function') {
            node.stateNode.editor.setValue(pineCode);
            out.push('SUCCESS via React fiber stateNode.editor: Set ' + pineCode.length + ' chars');
            return out.join(' | ');
          }
          if (node.memoizedState) {
            var state = node.memoizedState;
            while (state) {
              if (state.memoizedState && state.memoizedState.editor && typeof state.memoizedState.editor.setValue === 'function') {
                state.memoizedState.editor.setValue(pineCode);
                out.push('SUCCESS via React memoizedState.editor');
                return out.join(' | ');
              }
              state = state.next;
            }
          }
          node = node.return;
          depth++;
        }
        out.push('Walked ' + depth + ' fiber nodes, no editor found');
      }
    }
  } catch(e) {
    out.push('React fiber error: ' + e.message);
  }
  
  // APPROACH 3: Use execCommand on focused textarea
  try {
    var editorEl = document.querySelector('.monaco-editor.pine-editor-monaco');
    if (editorEl) {
      var textarea = editorEl.querySelector('textarea');
      if (textarea) {
        textarea.focus();
        textarea.select();
        // Select all and replace
        document.execCommand('selectAll');
        document.execCommand('insertText', false, pineCode);
        out.push('execCommand approach: inserted ' + pineCode.length + ' chars');
        out.push('Textarea value now: ' + textarea.value.substring(0, 50));
        return out.join(' | ');
      }
    }
  } catch(e) {
    out.push('execCommand error: ' + e.message);
  }
  
  return out.join(' | ') + ' | ALL APPROACHES FAILED';
})()
"@

$req = '{"id":7,"method":"Runtime.evaluate","params":{"expression":' + ($injectJs | ConvertTo-Json) + ',"returnByValue":true}}'
Send-CDP $req
Start-Sleep -Milliseconds 5000
$resp = Recv-CDP
Write-Output "INJECT_RESULT: $resp"

# STEP 3: Save via Ctrl+S
$saveJs = @'
(function() {
  // Try Add to Chart button first
  var btns = document.querySelectorAll('button');
  var saveBtn = null;
  for (var b of btns) {
    var txt = (b.textContent || b.innerText || '').trim().toLowerCase();
    var title = (b.title || '').toLowerCase();
    var ariaLabel = (b.getAttribute('aria-label') || '').toLowerCase();
    if (txt === 'save' || txt === 'add to chart' || title.includes('save') || title.includes('add to chart') || ariaLabel.includes('save') || ariaLabel.includes('add to chart')) {
      saveBtn = b;
      break;
    }
  }
  if (saveBtn) {
    saveBtn.click();
    return 'Clicked button: ' + (saveBtn.textContent || saveBtn.title);
  }
  // Send Ctrl+S to focused element
  var focused = document.activeElement || document.body;
  focused.dispatchEvent(new KeyboardEvent('keydown', {key: 's', code: 'KeyS', ctrlKey: true, bubbles: true, cancelable: true}));
  document.dispatchEvent(new KeyboardEvent('keydown', {key: 's', code: 'KeyS', ctrlKey: true, bubbles: true, cancelable: true}));
  return 'Sent Ctrl+S to focused + document';
})()
'@

$req2 = '{"id":8,"method":"Runtime.evaluate","params":{"expression":' + ($saveJs | ConvertTo-Json) + ',"returnByValue":true}}'
Send-CDP $req2
Start-Sleep -Milliseconds 2000
$resp2 = Recv-CDP
Write-Output "SAVE_RESULT: $resp2"

$ws.CloseAsync([System.Net.WebSockets.WebSocketCloseStatus]::NormalClosure, "done", $ct).Wait()
Write-Output "DONE"
