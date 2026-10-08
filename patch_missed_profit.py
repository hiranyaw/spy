with open('dashboard_server.py', 'r', encoding='utf-8') as f:
    py = f.read()

# 1. Initialize missed profit var
if 'total_missed_profit = 0' not in py:
    py = py.replace('early_exits_count = 0', 'early_exits_count = 0\n        total_missed_profit = 0')

# 2. Add to total missed profit
if 'total_missed_profit += missed_profit' not in py:
    old_early_exit_append = '''                    early_exits_count += 1
                    early_exit_moves.append(favorable_post_exit_move)'''
    
    new_early_exit_append = '''                    early_exits_count += 1
                    early_exit_moves.append(favorable_post_exit_move)
                    trade_qty = sum(e.get("qty", 1) for e in t.get("entries", [])) if t.get("entries") else 1
                    missed_profit = favorable_post_exit_move * trade_qty * 50
                    total_missed_profit += missed_profit'''
    
    py = py.replace(old_early_exit_append, new_early_exit_append)

# 3. Update the recommendation string
old_rec = '''                    recommendations.append(f"You sold {early_exits_count} winning trade(s) too early! The price continued in your favor over the next 5 minutes. Suggestion: Hold for at least 5 more minutes or trail using the 9 EMA (SPY ran up to +\\ post-exit).")'''
new_rec = '''                    recommendations.append(f"You sold {early_exits_count} winning trade(s) too early, leaving roughly \\ of potential profit on the table. Suggestion: The next time you are in profit, DO NOT sell your entire position. Sell half at your initial target to secure a win, and strictly trail the remaining half using the 1-minute 9 EMA to capture the rest of the trend. (SPY pushed up to +\\ points higher post-exit).")'''

py = py.replace(old_rec, new_rec)

with open('dashboard_server.py', 'w', encoding='utf-8') as f:
    f.write(py)

print("Missed profit patch applied")
