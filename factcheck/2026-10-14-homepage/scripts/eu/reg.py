import json, sys
for f in sys.argv[1:]:
    d = json.load(open(f))
    r = d['result']
    print(f, "count", r['count'], "returned", len(r['results']))
    for pk in r['results']:
        lic = pk.get('license_id'), pk.get('license_title')
        for res in pk['resources']:
            print(" ", pk['name'], lic, res['url'], [e.get('value') for e in pk.get('extras',[]) if e.get('key') in ('activity_count','data_updated')])
