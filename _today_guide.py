import json, sys, datetime
sys.path.insert(0, r'C:\Users\Hiranya\spy')

with open(r'C:\Users\Hiranya\spy\signals.json') as f:
    d = json.load(f)

print("=== SIGNAL ===")
print("signal:", d.get('signal'))
print("last_update:", d.get('last_update'))
print("details:", d.get('details'))
print("prices:", d.get('prices'))
print("levels:", d.get('levels'))

print("=== PAPER STATS ===")
print(d.get('paper_stats'))

print("=== OPEN POSITION ===")
print(d.get('open_position'))

try:
    from market_context import get_full_context
    ctx = get_full_context()
    print("=== MARKET CONTEXT ===")
    print("VIX:", ctx.get('vix'), ctx.get('vix_regime'))
    print("Events:", ctx.get('events'))
    print("Gap:", ctx.get('gap'))
except Exception as e:
    print("MARKET CONTEXT ERROR:", e)
