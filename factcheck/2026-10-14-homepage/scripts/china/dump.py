import sys, json, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from xlsxread import read_xlsx_sheet
import zipfile, xml.etree.ElementTree as ET
src, out = sys.argv[1], sys.argv[2]
z = zipfile.ZipFile(src)
ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
print([s.get("name") for s in ET.fromstring(z.read("xl/workbook.xml")).iter(ns+"sheet")])
rows = read_xlsx_sheet(src, "GCDF_3.0")
hdr = [str(h) for h in next(rows)]
for i,h in enumerate(hdr): print(i, h)
data = [dict(zip(hdr, r + [None]*(len(hdr)-len(r)))) for r in rows if r and r[0] is not None]
print("rows", len(data))
json.dump({"hdr":hdr, "rows":data}, open(out,"w"))
