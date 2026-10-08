with open('dashboard.html', 'r', encoding='utf-8') as f:
    html = f.read()

# 1. Update grid columns from 5 to 7
html = html.replace('grid-template-columns:repeat(5, 1fr)', 'grid-template-columns:repeat(7, 1fr)')

# 2. Add stat cards HTML
old_stat_card = '''      <div style="background:#161b22;border:1px solid #30363d;border-radius:10px;padding:15px;text-align:center">
        <div style="font-size:0.75rem;color:#8b949e;text-transform:uppercase;letter-spacing:.5px;margin-bottom:5px">Rule 2 P&amp;L (Stop @ 2L)</div>
        <div id="ana-month-stat-sim2l" style="font-size:1.4rem;font-weight:700;color:#e6edf3">--</div>
      </div>
    </div>'''

new_stat_card = '''      <div style="background:#161b22;border:1px solid #30363d;border-radius:10px;padding:15px;text-align:center">
        <div style="font-size:0.75rem;color:#8b949e;text-transform:uppercase;letter-spacing:.5px;margin-bottom:5px">Rule 2 P&amp;L (Stop @ 2L)</div>
        <div id="ana-month-stat-sim2l" style="font-size:1.4rem;font-weight:700;color:#e6edf3">--</div>
      </div>
      <div style="background:#161b22;border:1px solid #30363d;border-radius:10px;padding:15px;text-align:center">
        <div style="font-size:0.75rem;color:#8b949e;text-transform:uppercase;letter-spacing:.5px;margin-bottom:5px">Sim: Hold 5m</div>
        <div id="ana-month-stat-sim5m" style="font-size:1.4rem;font-weight:700;color:#e6edf3">--</div>
      </div>
      <div style="background:#161b22;border:1px solid #30363d;border-radius:10px;padding:15px;text-align:center">
        <div style="font-size:0.75rem;color:#8b949e;text-transform:uppercase;letter-spacing:.5px;margin-bottom:5px">Sim: Hold 15m</div>
        <div id="ana-month-stat-sim15m" style="font-size:1.4rem;font-weight:700;color:#e6edf3">--</div>
      </div>
    </div>'''
html = html.replace(old_stat_card, new_stat_card)

# 3. Add JS arrays and sums
html = html.replace('let sumDirAcc = 0, sumSim3 = 0, sumSim2l = 0, sumActual = 0;',
                    'let sumDirAcc = 0, sumSim3 = 0, sumSim2l = 0, sumActual = 0, sumSim5m = 0, sumSim15m = 0;')

html = html.replace('const dates = [], actualPnlData = [], sim3PnlData = [], sim2lPnlData = [], dirAccData = [], earlyExitsData = [];',
                    'const dates = [], actualPnlData = [], sim3PnlData = [], sim2lPnlData = [], sim5mPnlData = [], sim15mPnlData = [], dirAccData = [], earlyExitsData = [];')

# 4. Push logic
html = html.replace('sumSim2l  += day.sim_2l_pnl;',
                    'sumSim2l  += day.sim_2l_pnl;\n      sumSim5m  += (day.sim_5m_pnl || 0);\n      sumSim15m += (day.sim_15m_pnl || 0);')

html = html.replace('sim2lPnlData.push(Number(sumSim2l.toFixed(2)));',
                    'sim2lPnlData.push(Number(sumSim2l.toFixed(2)));\n      sim5mPnlData.push(Number(sumSim5m.toFixed(2)));\n      sim15mPnlData.push(Number(sumSim15m.toFixed(2)));')

# 5. Populate stat cards
html = html.replace('const sim2lEl = document.getElementById(\'ana-month-stat-sim2l\');',
                    'const sim5mEl = document.getElementById(\'ana-month-stat-sim5m\');\n    if (sim5mEl)  { sim5mEl.textContent  = (sumSim5m  >= 0 ? \'+$\' : \'-$\') + Math.abs(sumSim5m).toFixed(2);  sim5mEl.style.color  = sumSim5m  >= 0 ? \'#3fb950\' : \'#f85149\'; }\n\n    const sim15mEl = document.getElementById(\'ana-month-stat-sim15m\');\n    if (sim15mEl) { sim15mEl.textContent = (sumSim15m >= 0 ? \'+$\' : \'-$\') + Math.abs(sumSim15m).toFixed(2); sim15mEl.style.color = sumSim15m >= 0 ? \'#3fb950\' : \'#f85149\'; }\n\n    const sim2lEl = document.getElementById(\'ana-month-stat-sim2l\');')

# 6. Add chart datasets
old_pnl_chart = '''            { label: 'Actual P&L',              data: actualPnlData, borderColor: '#58a6ff', borderWidth: 2, pointRadius: 4, tension: 0.3, fill: false },
            { label: 'Sim: Stop @ 3 Trades',    data: sim3PnlData,   borderColor: '#3fb950', borderWidth: 2, pointRadius: 4, tension: 0.3, fill: false },
            { label: 'Sim: Stop @ 2 consec L',  data: sim2lPnlData,  borderColor: '#ff9e2c', borderWidth: 2, pointRadius: 4, tension: 0.3, fill: false }'''
new_pnl_chart = '''            { label: 'Actual P&L',              data: actualPnlData, borderColor: '#58a6ff', borderWidth: 2, pointRadius: 4, tension: 0.3, fill: false },
            { label: 'Sim: Stop @ 3 Trades',    data: sim3PnlData,   borderColor: '#3fb950', borderWidth: 2, pointRadius: 4, tension: 0.3, fill: false },
            { label: 'Sim: Stop @ 2 consec L',  data: sim2lPnlData,  borderColor: '#ff9e2c', borderWidth: 2, pointRadius: 4, tension: 0.3, fill: false },
            { label: 'Sim: Hold 5m (No Early Exits)', data: sim5mPnlData, borderColor: '#bc8cff', borderWidth: 2, borderDash: [5, 5], pointRadius: 4, tension: 0.3, fill: false },
            { label: 'Sim: Hold 15m (No Early Exits)', data: sim15mPnlData, borderColor: '#d2a8ff', borderWidth: 2, borderDash: [2, 2], pointRadius: 4, tension: 0.3, fill: false }'''
html = html.replace(old_pnl_chart, new_pnl_chart)

with open('dashboard.html', 'w', encoding='utf-8') as f:
    f.write(html)

print("HTML patch applied for 5m and 15m hold options")
