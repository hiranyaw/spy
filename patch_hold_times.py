with open('dashboard_server.py', 'r', encoding='utf-8') as f:
    py = f.read()

# 1. Update initialization
py = py.replace('total_missed_profit = 0\n        total_missed_profit_15m = 0', 'total_missed_profit_1m = 0\n        total_missed_profit_2m = 0\n        total_missed_profit_5m = 0')

# Replace the single instances where 15m was used without 5m
py = py.replace('total_missed_profit_15m = 0', 'total_missed_profit_2m = 0') # Safety catch

# 2. Add 1m, 2m, 5m calculations
old_post_exit = '''            # Post exit move (5 minutes and 15 minutes)
            post_exit_dt = exit_dt + timedelta(minutes=5)
            post_exit_idx = int(df.index.get_indexer([post_exit_dt], method='nearest')[0])
            post_df = df.iloc[exit_idx:post_exit_idx+1] if post_exit_idx > exit_idx else pd.DataFrame()
            
            post_15m_dt = exit_dt + timedelta(minutes=15)
            post_15m_idx = int(df.index.get_indexer([post_15m_dt], method='nearest')[0])
            post_15m_df = df.iloc[exit_idx:post_15m_idx+1] if post_15m_idx > exit_idx else pd.DataFrame()
            
            favorable_post_exit_move_15m = 0.0
            if not post_15m_df.empty:
                max_spy_post_15m = float(post_15m_df['High'].max())
                min_spy_post_15m = float(post_15m_df['Low'].min())
                if underlying_dir == "LONG":
                    favorable_post_exit_move_15m = max_spy_post_15m - spy_exit_price
                else:
                    favorable_post_exit_move_15m = spy_exit_price - min_spy_post_15m'''

new_post_exit = '''            # Post exit move (1m, 2m, 5m)
            post_1m_dt = exit_dt + timedelta(minutes=1)
            post_1m_idx = int(df.index.get_indexer([post_1m_dt], method='nearest')[0])
            post_1m_df = df.iloc[exit_idx:post_1m_idx+1] if post_1m_idx > exit_idx else pd.DataFrame()
            
            post_2m_dt = exit_dt + timedelta(minutes=2)
            post_2m_idx = int(df.index.get_indexer([post_2m_dt], method='nearest')[0])
            post_2m_df = df.iloc[exit_idx:post_2m_idx+1] if post_2m_idx > exit_idx else pd.DataFrame()
            
            post_5m_dt = exit_dt + timedelta(minutes=5)
            post_5m_idx = int(df.index.get_indexer([post_5m_dt], method='nearest')[0])
            post_5m_df = df.iloc[exit_idx:post_5m_idx+1] if post_5m_idx > exit_idx else pd.DataFrame()
            
            favorable_post_exit_move_1m = 0.0
            favorable_post_exit_move_2m = 0.0
            favorable_post_exit_move_5m = 0.0
            
            if not post_1m_df.empty:
                favorable_post_exit_move_1m = (float(post_1m_df['High'].max()) - spy_exit_price) if underlying_dir == "LONG" else (spy_exit_price - float(post_1m_df['Low'].min()))
            if not post_2m_df.empty:
                favorable_post_exit_move_2m = (float(post_2m_df['High'].max()) - spy_exit_price) if underlying_dir == "LONG" else (spy_exit_price - float(post_2m_df['Low'].min()))
            if not post_5m_df.empty:
                favorable_post_exit_move_5m = (float(post_5m_df['High'].max()) - spy_exit_price) if underlying_dir == "LONG" else (spy_exit_price - float(post_5m_df['Low'].min()))
            
            # keep legacy var for recommendation
            post_df = post_5m_df
            favorable_post_exit_move = favorable_post_exit_move_5m'''

py = py.replace(old_post_exit, new_post_exit)

# 3. Add to total missed profit 1m, 2m, 5m
old_missed = '''                    total_missed_profit += missed_profit
                    missed_profit_15m = favorable_post_exit_move_15m * trade_qty * 50
                    total_missed_profit_15m += missed_profit_15m'''
new_missed = '''                    total_missed_profit_1m += favorable_post_exit_move_1m * trade_qty * 50
                    total_missed_profit_2m += favorable_post_exit_move_2m * trade_qty * 50
                    total_missed_profit_5m += favorable_post_exit_move_5m * trade_qty * 50
                    total_missed_profit += missed_profit'''
py = py.replace(old_missed, new_missed)

# 4. Add to API response summary
old_summary = '''                    "sim_5m_pnl": round(total_pnl + total_missed_profit, 2),
                    "sim_15m_pnl": round(total_pnl + total_missed_profit_15m, 2),'''
new_summary = '''                    "sim_1m_pnl": round(total_pnl + total_missed_profit_1m, 2),
                    "sim_2m_pnl": round(total_pnl + total_missed_profit_2m, 2),
                    "sim_5m_pnl": round(total_pnl + total_missed_profit_5m, 2),'''
py = py.replace(old_summary, new_summary)

with open('dashboard_server.py', 'w', encoding='utf-8') as f:
    f.write(py)

print("dashboard_server.py updated for 1m, 2m, 5m")
