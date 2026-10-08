with open('dashboard_server.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if line.strip() == 'total_missed_profit = 0':
        prev_line = lines[i-1]
        indent = len(prev_line) - len(prev_line.lstrip())
        lines[i] = (' ' * indent) + 'total_missed_profit = 0\n'
    elif line.strip() == 'total_missed_profit += missed_profit':
        prev_line = lines[i-1]
        indent = len(prev_line) - len(prev_line.lstrip())
        lines[i] = (' ' * indent) + 'total_missed_profit += missed_profit\n'

with open('dashboard_server.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print("Indentation fixed")
