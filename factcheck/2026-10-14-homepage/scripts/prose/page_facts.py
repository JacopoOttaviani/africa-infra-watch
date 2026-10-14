import json, sys, collections
m = json.load(open(sys.argv[1] + '/docs/data/map.json', encoding='utf-8'))
T = lambda k: [dict(zip(m[k]['cols'], r)) for r in m[k]['rows']]
fin = T('finance')
afdb = [r for r in fin if r['ln'] == 'AfDB']
print('AfDB prec values:', collections.Counter(r['prec'] for r in afdb))
print('status by lender:', {ln: dict(collections.Counter(r['status'] for r in fin if r['ln'] == ln)) for ln in ('AfDB', 'WB')})
water = collections.Counter()
for k in ('finance', 'eu', 'china', 'mattei', 'ground'):
    for r in T(k):
        if r.get('sector') == 'water': water[k if k != 'finance' else r['ln']] += 1
print('water-sector records by layer/lender:', dict(water), sum(water.values()))
osm = collections.Counter(r['sector'] for r in T('ground')); print('OSM sectors:', dict(osm))
a = T('assets'); st = collections.Counter(r['status'] for r in a); print('power status:', dict(st), 'pipeline share', round((st['announced'] + st['approved'] + st['under_construction']) / len(a), 3))
