with open('dashboard.html', 'r', encoding='utf-8') as f:
    html = f.read()

# Add to table header
html = html.replace('<th style="padding:8px;text-align:center">Dir. Accuracy</th>',
                    '<th style="padding:8px;text-align:center">Dir. Accuracy</th>\n            <th style="padding:8px;text-align:center">Early Exits</th>')

# Add to table body row
html = html.replace('<td style="padding:8px;text-align:center;color:#3fb950;font-weight:700"></td>',
                    '<td style="padding:8px;text-align:center;color:#3fb950;font-weight:700"></td>\n          <td style="padding:8px;text-align:center;color:#e6edf3"></td>')

# Fix colspans
html = html.replace('colspan="8"', 'colspan="9"')

with open('dashboard.html', 'w', encoding='utf-8') as f:
    f.write(html)

with open('dashboard_server.py', 'r', encoding='utf-8') as f:
    py = f.read()

# Change from 30 minutes to 5 minutes
py = py.replace('pd.Timedelta(minutes=30)', 'pd.Timedelta(minutes=5)')

# Update recommendation text
old_rec = 'recommendations.append(f"Implement a 2-stage exit: sell 50% at your initial target, and trail the remainder using the 1-minute 9 EMA to capture extended runs (SPY ran up to +\\ post-exit today).")'
new_rec = 'recommendations.append(f"You sold {early_exits_count} winning trade(s) too early! The price continued in your favor over the next 5 minutes. Suggestion: Hold for at least 5 more minutes or trail using the 9 EMA (SPY ran up to +\\ post-exit today).")'
py = py.replace(old_rec, new_rec)

with open('dashboard_server.py', 'w', encoding='utf-8') as f:
    f.write(py)

print("Patch applied")
