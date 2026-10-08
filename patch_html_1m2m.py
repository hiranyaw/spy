with open('dashboard.html', 'r', encoding='utf-8') as f:
    html = f.read()

# 1. Update grid columns from 7 to 8
html = html.replace('grid-template-columns:repeat(7, 1fr)', 'grid-template-columns:repeat(8, 1fr)')

# 2. Add stat cards HTML
old_stat_card = '''      <div style="background:#161b22;border:1px solid #30363d;border-radius:10px;padding:15px;text-align:center">
        <div style="font-size:0.75rem;color:#8b949e;text-transform:uppercase;letter-spacing:.5px;margin-bottom:5px">Sim: Hold 5m</div>
        <div id="ana-month-stat-sim5m" style="font-size:1.4rem;font-weight:700;color:#e6edf3">--</div>
      </div>
      <div style="background:#161b22;border:1px solid #30363d;border-radius:10px;padding:15px;text-align:center">
        <div style="font-size:0.75rem;color:#8b949e;text-transform:uppercase;letter-spacing:.5px;margin-bottom:5px">Sim: Hold 15m</div>
        <div id="ana-month-stat-sim15m" style="font-size:1.4rem;font-weight:700;color:#e6edf3">--</div>
      </div>'''

new_stat_card = '''      <div style="background:#161b22;border:1px solid #30363d;border-radius:10px;padding:15px;text-align:center">
        <div style="font-size:0.75rem;color:#8b949e;text-transform:uppercase;letter-spacing:.5px;margin-bottom:5px">Sim: Hold 1m</div>
        <div id="ana-month-stat-sim1m" style="font-size:1.4rem;font-weight:700;color:#e6edf3">--</div>
      </div>
      <div style="background:#161b22;border:1px solid #30363d;border-radius:10px;padding:15px;text-align:center">
        <div style="font-size:0.75rem;color:#8b949e;text-transform:uppercase;letter-spacing:.5px;margin-bottom:5px">Sim: Hold 2m</div>
        <div id="ana-month-stat-sim2m" style="font-size:1.4rem;font-weight:700;color:#e6edf3">--</div>
      </div>
      <div style="background:#161b22;border:1px solid #30363d;border-radius:10px;padding:15px;text-align:center">
        <div style="font-size:0.75rem;color:#8b949e;text-transform:uppercase;letter-spacing:.5px;margin-bottom:5px">Sim: Hold 5m</div>
        <div id="ana-month-stat-sim5m" style="font-size:1.4rem;font-weight:700;color:#e6edf3">--</div>
      </div>'''
html = html.replace(old_stat_card, new_stat_card)

# 3. Add JS arrays and sums
html = html.replace('let sumDirAcc = 0, sumSim3 = 0, sumSim2l = 0, sumActual = 0, sumSim5m = 0, sumSim15m = 0;',
                    'let sumDirAcc = 0, sumSim3 = 0, sumSim2l = 0, sumActual = 0, sumSim1m = 0, sumSim2m = 0, sumSim5m = 0;')

html = html.replace('const dates = [], actualPnlData = [], sim3PnlData = [], sim2lPnlData = [], sim5mPnlData = [], sim15mPnlData = [], dirAccData = [], earlyExitsData = [];',
                    'const dates = [], actualPnlData = [], sim3PnlData = [], sim2lPnlData = [], sim1mPnlData = [], sim2mPnlData = [], sim5mPnlData = [], dirAccData = [], earlyExitsData = [];')

# 4. Push logic
html = html.replace('sumSim2l  += day.sim_2l_pnl;\n      sumSim5m  += (day.sim_5m_pnl || 0);\n      sumSim15m += (day.sim_15m_pnl || 0);',
                    'sumSim2l  += day.sim_2l_pnl;\n      sumSim1m  += (day.sim_1m_pnl || 0);\n      sumSim2m  += (day.sim_2m_pnl || 0);\n      sumSim5m  += (day.sim_5m_pnl || 0);')

html = html.replace('sim2lPnlData.push(Number(sumSim2l.toFixed(2)));\n      sim5mPnlData.push(Number(sumSim5m.toFixed(2)));\n      sim15mPnlData.push(Number(sumSim15m.toFixed(2)));',
                    'sim2lPnlData.push(Number(sumSim2l.toFixed(2)));\n      sim1mPnlData.push(Number(sumSim1m.toFixed(2)));\n      sim2mPnlData.push(Number(sumSim2m.toFixed(2)));\n      sim5mPnlData.push(Number(sumSim5m.toFixed(2)));')

# 5. Populate stat cards
old_pop = '''    const sim5mEl = document.getElementById('ana-month-stat-sim5m');
    if (sim5mEl)  { sim5mEl.textContent  = (sumSim5m  >= 0 ? '+$' : '-$') + Math.abs(sumSim5m).toFixed(2);  sim5mEl.style.color  = sumSim5m  >= 0 ? '#3fb950' : '#f85149'; }

    const sim15mEl = document.getElementById('ana-month-stat-sim15m');
    if (sim15mEl) { sim15mEl.textContent = (sumSim15m >= 0 ? '+$' : '-$') + Math.abs(sumSim15m).toFixed(2); sim15mEl.style.color = sumSim15m >= 0 ? '#3fb950' : '#f85149'; }

    const sim2lEl = document.getElementById('ana-month-stat-sim2l');'''

new_pop = '''    const sim1mEl = document.getElementById('ana-month-stat-sim1m');
    if (sim1mEl)  { sim1mEl.textContent  = (sumSim1m  >= 0 ? '+$' : '-$') + Math.abs(sumSim1m).toFixed(2);  sim1mEl.style.color  = sumSim1m  >= 0 ? '#3fb950' : '#f85149'; }

    const sim2mEl = document.getElementById('ana-month-stat-sim2m');
    if (sim2mEl)  { sim2mEl.textContent  = (sumSim2m  >= 0 ? '+$' : '-$') + Math.abs(sumSim2m).toFixed(2);  sim2mEl.style.color  = sumSim2m  >= 0 ? '#3fb950' : '#f85149'; }

    const sim5mEl = document.getElementById('ana-month-stat-sim5m');
    if (sim5mEl)  { sim5mEl.textContent  = (sumSim5m  >= 0 ? '+$' : '-$') + Math.abs(sumSim5m).toFixed(2);  sim5mEl.style.color  = sumSim5m  >= 0 ? '#3fb950' : '#f85149'; }

    const sim2lEl = document.getElementById('ana-month-stat-sim2l');'''
html = html.replace(old_pop, new_pop)

# 6. Add chart datasets
old_pnl_chart = '''            { label: 'Sim: Hold 5m (No Early Exits)', data: sim5mPnlData, borderColor: '#bc8cff', borderWidth: 2, borderDash: [5, 5], pointRadius: 4, tension: 0.3, fill: false },
            { label: 'Sim: Hold 15m (No Early Exits)', data: sim15mPnlData, borderColor: '#d2a8ff', borderWidth: 2, borderDash: [2, 2], pointRadius: 4, tension: 0.3, fill: false }'''
new_pnl_chart = '''            { label: 'Sim: Hold 1m', data: sim1mPnlData, borderColor: '#ff7b72', borderWidth: 2, borderDash: [2, 2], pointRadius: 4, tension: 0.3, fill: false },
            { label: 'Sim: Hold 2m', data: sim2mPnlData, borderColor: '#ffa657', borderWidth: 2, borderDash: [3, 3], pointRadius: 4, tension: 0.3, fill: false },
            { label: 'Sim: Hold 5m', data: sim5mPnlData, borderColor: '#bc8cff', borderWidth: 2, borderDash: [5, 5], pointRadius: 4, tension: 0.3, fill: false }'''
html = html.replace(old_pnl_chart, new_pnl_chart)

with open('dashboard.html', 'w', encoding='utf-8') as f:
    f.write(html)

print("HTML patch applied for 1m, 2m, 5m hold options")
