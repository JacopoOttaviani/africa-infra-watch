import json, sys, collections
d = json.load(open(sys.argv[1]))
F = [f['properties'] for f in d['features']]
def show(p):
    print(f"{(p['commitment'] or 0)/1e6:10.1f}M  {p['source']:9} {p['kind']:9} {p['iati_id']:45} {p['country']} {p['raw_status']} {p['instrument']} | {(p['name'] or '')[:70]} | {p.get('sector_label') or p.get('sector_codes')}")
print("TOP 20 overall")
for p in sorted(F, key=lambda p: -(p['commitment'] or 0))[:20]: show(p)
print("TOP 12 EIB")
eib=[p for p in F if p['source']=='EIB']
for p in sorted(eib, key=lambda p: -(p['commitment'] or 0))[:12]: show(p)
print("EIB equity")
for p in sorted([p for p in eib if p['instrument']=='equity'], key=lambda p: -(p['commitment'] or 0)): show(p)
print(collections.Counter(p['instrument'] for p in eib))
print("EIB with no commitment", sum(1 for p in eib if not p['commitment']))
print("sum EIB", sum(p['commitment'] or 0 for p in eib)/1e9, "sum EC", sum(p['commitment'] or 0 for p in F if p['source']!='EIB')/1e9)
