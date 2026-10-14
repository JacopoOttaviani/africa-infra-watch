import json, sys
for f in sys.argv[1:]:
    d = json.load(open(f))["result"]
    keys = {k: d.get(k) for k in ("name", "title", "license_id", "license_title", "license_url", "publisher_licence", "license_id", "publisher_iati_id", "publisher_first_publish_date")}
    print(f.split("/")[-1], keys)
    for k, v in d.items():
        if "lic" in k.lower(): print("   ", k, v)
