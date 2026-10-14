import json, sys
AF = "DZ AO BJ BW BF BI CM CV CF TD KM CG CD DJ EG GQ ER SZ ET GA GM GH GN GW CI KE LS LR LY MG MW ML MR MU MA MZ NA NE NG RW ST SN SC SL SO ZA SS SD TZ TG TN UG ZM ZW".lower().split()
intpa = json.load(open(sys.argv[1]))['result']['results']
near = json.load(open(sys.argv[2]))['result']['results']
fi = AF + ["289", "298"]; fn = ["dz","eg","ly","ma","tn","189"]
ki = [p for p in intpa if p['name'].rsplit('-',1)[-1].lower() in fi]
kn = [p for p in near if p['name'].rsplit('-',1)[-1].lower() in fn]
print("INTPA kept", len(ki), "NEAR kept", len(kn), "total", len(ki)+len(kn))
print("Africa ISO missing in both:", [c for c in AF if c not in [p['name'].rsplit('-',1)[-1] for p in intpa+near]])
for p in intpa:
    s = p['name'].rsplit('-',1)[-1]
    if s in ("1027","1028","1029","1030","1031","289","298","189","589","998","89","sh"):
        ex = {e['key']: e['value'] for e in p.get('extras',[])}
        print(p['name'], p['title'], ex.get('activity_count'), ex.get('recipient_region') , p.get('license_id'))
print({p['license_id'] for p in intpa+near}, {p.get('license_title') for p in intpa+near})
print(intpa[0].get('license_id'), intpa[0].get('license_title'), intpa[0].get('license_url'))
