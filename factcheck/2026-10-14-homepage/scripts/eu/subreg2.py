import json, sys
A = json.load(open(sys.argv[1]))
ec = [a for a in A if a["pub"] != "EIB"]
parents = {p for a in ec if a["hier"] == "2" for p in a["parents"]}
kept = [a for a in A if a["pub"] == "EIB" or a["hier"] == "2" or a["id"] not in parents]
sub = {"XI-IATI-EC_INTPA_C_1027.xml","XI-IATI-EC_INTPA_C_1028.xml","XI-IATI-EC_INTPA_C_1029.xml","XI-IATI-EC_INTPA_C_1030.xml"}
ks = [a for a in kept if a["file"] in sub]
print("total kept", len(kept), "from subregional files", len(ks), "EURbn", round(sum(a['commit'] for a in ks)/1e9, 3))
# also: do any of the 57-file kept decisions lose status because a subregional contract points to them?
base = json.load(open(sys.argv[2]))
ecb = [a for a in base if a["pub"] != "EIB"]
pb = {p for a in ecb if a["hier"] == "2" for p in a["parents"]}
keptb = {a["id"] for a in base if a["pub"] == "EIB" or a["hier"] == "2" or a["id"] not in pb}
lost = [a for a in base if a["id"] in keptb and a["id"] not in {k["id"] for k in kept}]
print("base decisions newly folded:", len(lost))
