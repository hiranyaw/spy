with open('dashboard_server.py', 'r', encoding='utf-8') as f:
    py = f.read()

# 1. Update initialization
py = py.replace('total_missed_profit = 0', 'total_missed_profit = 0\n        total_missed_profit_15m = 0')

# 2. Add 15m calculation
old_post_exit = '''            # Post exit move (5 minutes)
            post_exit_dt = exit_dt + timedelta(minutes=5)
            post_exit_idx = int(df.index.get_indexer([post_exit_dt], method='nearest')[0])
            post_df = df.iloc[exit_idx:post_exit_idx+1] if post_exit_idx > exit_idx else pd.DataFrame()'''
            
new_post_exit = '''            # Post exit move (5 minutes and 15 minutes)
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
                    
py = py.replace(old_post_exit, new_post_exit)

# 3. Add to total missed profit 15m
old_missed = '''                    total_missed_profit += missed_profit'''
new_missed = '''                    total_missed_profit += missed_profit
                    missed_profit_15m = favorable_post_exit_move_15m * trade_qty * 50
                    total_missed_profit_15m += missed_profit_15m'''
py = py.replace(old_missed, new_missed)

# 4. Add to API response summary
old_summary = '''                    "sim_2l_losses": sim_2l_losses,
                    "sim_2l_pnl": round(sim_2l_pnl, 2),'''
new_summary = '''                    "sim_2l_losses": sim_2l_losses,
                    "sim_2l_pnl": round(sim_2l_pnl, 2),
                    "sim_5m_pnl": round(total_pnl + total_missed_profit, 2),
                    "sim_15m_pnl": round(total_pnl + total_missed_profit_15m, 2),'''
py = py.replace(old_summary, new_summary)

with open('dashboard_server.py', 'w', encoding='utf-8') as f:
    f.write(py)

print("15m patch applied to dashboard_server.py")
