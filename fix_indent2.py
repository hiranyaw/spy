with open('dashboard_server.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if line.strip() == 'total_missed_profit_15m = 0':
        prev_line = lines[i-1]
        indent = len(prev_line) - len(prev_line.lstrip())
        lines[i] = (' ' * indent) + 'total_missed_profit_15m = 0\n'

with open('dashboard_server.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print("Indentation 2 fixed")
