import sys
sys.path.append(sys.argv[1])
import pypdf
r = pypdf.PdfReader(sys.argv[2])
out = open(sys.argv[3], "w")
for i, p in enumerate(r.pages):
    out.write(f"\n=== PAGE {i+1}\n" + (p.extract_text() or ""))
print(len(r.pages))
