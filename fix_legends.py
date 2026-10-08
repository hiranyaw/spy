import sys
with open('c:/Users/Hiranya/spy/spy_trader_bot.py', 'r', encoding='utf-8') as f:
    t = f.read()
t = t.replace("t.includes('AK MACD') || t.includes('SIG_DIR')", "t.length > 5")
with open('c:/Users/Hiranya/spy/spy_trader_bot.py', 'w', encoding='utf-8') as f:
    f.write(t)
print('Replaced')
