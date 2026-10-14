"""Crude text pull from a PDF: inflate every FlateDecode stream and keep
literal strings inside Tj/TJ operators. python3 -I pdftext.py <pdf> <out.txt>"""
import re, sys, zlib
data = open(sys.argv[1], "rb").read()
out = []
for m in re.finditer(rb"stream\r?\n", data):
    start = m.end()
    end = data.find(b"endstream", start)
    if end < 0:
        continue
    try:
        s = zlib.decompress(data[start:end])
    except Exception:
        continue
    if b"BT" not in s:
        continue
    line = []
    for t in re.finditer(rb"\[(.*?)\]\s*TJ|\((.*?)(?<!\\)\)\s*Tj|(T\*|Td|TD|ET)", s, re.S):
        if t.group(3):
            if line:
                out.append("".join(line)); line = []
            continue
        if t.group(1) is not None:
            parts = re.findall(rb"\((.*?)(?<!\\)\)|(-?\d+\.?\d*)", t.group(1), re.S)
            for txt, num in parts:
                if txt:
                    line.append(txt.decode("latin-1"))
                elif num and float(num) < -200:
                    line.append(" ")
        else:
            line.append(t.group(2).decode("latin-1"))
    if line:
        out.append("".join(line))
open(sys.argv[2], "w").write("\n".join(out))
print(len(out), "lines")
