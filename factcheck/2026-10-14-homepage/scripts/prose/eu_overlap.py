import json, sys, collections
m = json.load(open(sys.argv[1] + '/docs/data/map.json', encoding='utf-8'))
v = m['eu']; rows = [dict(zip(v['cols'], r)) for r in v['rows']]
ec_eib = [r for r in rows if r['pub'] != 'EIB' and r.get('impl') and 'european investment bank' in r['impl'].lower()]
eib_grant = [r for r in rows if r['pub'] == 'EIB' and (r.get('instr') or '').lower() == 'grant']
tot = lambda L: sum(r.get('eur_m') or 0 for r in L)
print('EC records implemented by the EIB:', len(ec_eib), 'EUR m', round(tot(ec_eib), 1))
print('EIB grant records:', len(eib_grant), 'EUR m', round(tot(eib_grant), 1))
print('EC total EUR bn', round(tot([r for r in rows if r['pub'] != 'EIB'])/1000, 2), 'EIB total EUR bn', round(tot([r for r in rows if r['pub'] == 'EIB'])/1000, 2))
for r in ec_eib[:8]: print('  EC->EIB', r['iso'], (r['name'] or '')[:70], r.get('eur_m'))
for r in eib_grant[:8]: print('  EIB grant', r['iso'], (r['name'] or '')[:70], r.get('eur_m'))
f = m['finance']; fr = [dict(zip(f['cols'], r)) for r in f['rows']]
print('finance AfDB bn', round(sum(r['usd_m'] or 0 for r in fr if r['ln']=='AfDB')/1000,1), 'WB bn', round(sum(r['usd_m'] or 0 for r in fr if r['ln']=='WB')/1000,1))
