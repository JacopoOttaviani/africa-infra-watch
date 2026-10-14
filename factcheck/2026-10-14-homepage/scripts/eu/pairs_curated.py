"""Hand-checked pairs: an EIB 'grant' funded by MS-EC (the Commission's blending money) and the Commission contract delegating the same grant to the EIB. Both are in the layer and in the headline sum."""
import sys, json
A = {a["id"]: a for a in json.load(open(sys.argv[1]))}
E, C = "XM-DAC-918-3-", "XI-IATI-EC_"
P = [("20150219-89907", ["INTPA-2017-PCC-389842"]), ("20160754-89804", ["INTPA-2017-PCC-389999", "INTPA-2017-PCC-391054"]),
     ("20140373-90949", ["INTPA-2017-PCC-391676"]), ("20210433-98860", ["INTPA-2024-PC-27253"]), ("20200097-96259", ["INTPA-2023-PC-27289"]),
     ("20170197-92614", ["INTPA-2020-PCC-415840"]), ("20140271-92390", ["INTPA-2019-PCC-412366"]), ("20170305-94030", ["INTPA-2019-PCC-404234"]),
     ("20170305-90872", ["INTPA-2018-PCC-402372"]), ("20220821-98450", ["INTPA-2024-PC-36493"]), ("20210403-97607", ["INTPA-2023-PC-28209"]),
     ("20170089-94084", ["NEAR-2019-PCC-413055"]), ("20170090-91507", ["NEAR-2018-PCC-403228"]), ("20110416-89760", ["NEAR-2015-PCC-370413"]),
     ("20110416-89764", ["NEAR-2014-PCC-353967"]), ("20150491-89274", ["INTPA-2017-PCC-391352"]), ("20100217-89254", ["NEAR-2014-PCC-353950", "NEAR-2014-PCC-355439"]),
     ("20200039-96262", ["INTPA-2022-PC-23588"]), ("20200935-96017", ["INTPA-2023-PC-27905"]), ("20190920-94329", ["INTPA-2021-PCC-429116"])]
te = tc = tm = 0.0
for e, cs in P:
    a = A[E + e]; cc = [A[C + c] for c in cs]
    ce = sum(c["commit"] for c in cc); m = min(a["commit"], ce)
    te += a["commit"]; tc += ce; tm += m
    print(f"EIB {a['commit']/1e6:6.1f}M {a['title'][:40]:40} | EC {ce/1e6:6.1f}M {' + '.join(c['title'][:38] for c in cc)}")
print(f"{len(P)} pairs: EIB side EUR {te/1e6:.1f}M, Commission side EUR {tc/1e6:.1f}M, counted twice (min of each pair) EUR {tm/1e6:.1f}M")
