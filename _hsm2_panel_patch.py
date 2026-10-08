import json, hashlib
P = json.loads(open(r'C:\Users\Hiranya\spy\_hsm2_parts.json', encoding='utf-8').read())
f = r'C:\Users\Hiranya\spy\Hiranya_Signal_Monitor_v2.0.pine'
s = open(f, encoding='utf-8').read().replace('\r\n', '\n')
a, b = s.index('posIn     = input.string('), s.index('// ---------- Time ----------')
s = s[:a] + P['p1'] + s[b:]
c, d = s.index('var table panel'), s.index('// ---------- Alerts ----------')
s = s[:c] + P['p2'] + s[d:]
open(f, 'w', encoding='utf-8', newline='\n').write(s)
print(hashlib.sha256(s.encode('utf-8')).hexdigest()[:16], len(s.split('\n')))
