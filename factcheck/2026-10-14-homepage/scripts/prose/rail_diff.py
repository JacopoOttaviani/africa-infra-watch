import re, sys
def parse(path):
    txt = open(path, encoding='utf-8').read()
    seg = txt.split('All countries',1)[1].split('All sectors',1)[0]
    out = {}
    for m in re.finditer(r'^(.+?) \(([\d,]+)\)$', seg, re.M):
        out[m.group(1).strip()] = int(m.group(2).replace(',',''))
    return out
m = parse(sys.argv[1]); d = parse(sys.argv[2])
alias = {'DR Congo':'Democratic Republic of Congo','The Gambia':'Gambia'}
m2 = {alias.get(k,k):v for k,v in m.items()}
print('map entries', len(m), 'dash entries', len(d), 'sum map', sum(m.values()), 'sum dash', sum(d.values()))
for k in sorted(set(m2)|set(d)):
    if m2.get(k)!=d.get(k): print(f'{k:35s} map={m2.get(k)} dash={d.get(k)} diff={ (d.get(k) or 0)-(m2.get(k) or 0)}')
