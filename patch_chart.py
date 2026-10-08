with open('dashboard.html', 'r', encoding='utf-8') as f:
    html = f.read()

# Add earlyExitsData array
html = html.replace('const dates = [], actualPnlData = [], sim3PnlData = [], sim2lPnlData = [], dirAccData = [];',
                    'const dates = [], actualPnlData = [], sim3PnlData = [], sim2lPnlData = [], dirAccData = [], earlyExitsData = [];')

# Push data to earlyExitsData
html = html.replace('dirAccData.push(Number(dirAcc.toFixed(1)));',
                    'dirAccData.push(Number(dirAcc.toFixed(1)));\n      earlyExitsData.push(day.early_exits || 0);')

# Add bar dataset to the Direction Accuracy chart
old_datasets = '''          datasets: [{ label: 'Direction Accuracy (%)', data: dirAccData, borderColor: '#3fb950', backgroundColor: 'rgba(63,185,80,0.1)', borderWidth: 2, pointRadius: 4, tension: 0.3, fill: true }]'''
new_datasets = '''          datasets: [
              { label: 'Direction Accuracy (%)', type: 'line', data: dirAccData, yAxisID: 'y', borderColor: '#3fb950', backgroundColor: 'rgba(63,185,80,0.1)', borderWidth: 2, pointRadius: 4, tension: 0.3, fill: true },
              { label: 'Early Exits', type: 'bar', data: earlyExitsData, yAxisID: 'y1', backgroundColor: 'rgba(255,158,44,0.7)', barThickness: 10 }
            ]'''
html = html.replace(old_datasets, new_datasets)

# Add secondary y-axis to the chart options
old_scales = '''            scales: {
              x: { ticks: { color: '#8b949e', font: { size: 10 }, maxRotation: 45 }, grid: { color: '#21262d' } },
              y: { min: 0, max: 100, ticks: { color: '#8b949e', font: { size: 10 }, callback: v => v + '%' }, grid: { color: '#21262d' } }
            }'''
new_scales = '''            scales: {
              x: { ticks: { color: '#8b949e', font: { size: 10 }, maxRotation: 45 }, grid: { color: '#21262d' } },
              y: { min: 0, max: 100, position: 'left', ticks: { color: '#8b949e', font: { size: 10 }, callback: v => v + '%' }, grid: { color: '#21262d' } },
              y1: { type: 'linear', position: 'right', min: 0, suggestedMax: 5, ticks: { color: '#ff9e2c', font: { size: 10 }, stepSize: 1 }, grid: { drawOnChartArea: false } }
            }'''
html = html.replace(old_scales, new_scales)

# Enable legend on this chart
old_legend = '''plugins: { legend: { display: false } },'''
new_legend = '''plugins: { legend: { display: true, labels: { color: '#c9d1d9', font: { size: 10 } } } },'''
html = html.replace(old_legend, new_legend)

with open('dashboard.html', 'w', encoding='utf-8') as f:
    f.write(html)

print("Chart patch applied")
