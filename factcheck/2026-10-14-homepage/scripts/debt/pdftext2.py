"""Better crude PDF text: tokenise inflated content streams; keep string
literals that feed Tj/TJ/'/\" (skip marked-content dicts); newline on
Td/TD/T*/ET. python3 -I pdftext2.py <pdf> <out.txt>"""
import re, sys, zlib
data = open(sys.argv[1], "rb").read()
ESC = {b"n": "\n", b"r": "", b"t": " ", b"b": "", b"f": "", b"(": "(", b")": ")", b"\\": "\\"}

def strings(s):
    i, n = 0, len(s)
    toks = []
    while i < n:
        c = s[i:i+1]
        if c == b"(":
            depth, j, buf = 1, i + 1, []
            while j < n and depth:
                ch = s[j:j+1]
                if ch == b"\\":
                    nx = s[j+1:j+2]
                    if nx in ESC:
                        buf.append(ESC[nx]); j += 2; continue
                    m = re.match(rb"[0-7]{1,3}", s[j+1:j+4])
                    if m:
                        buf.append(bytes([int(m.group(), 8)]).decode("cp1252", "replace")); j += 1 + len(m.group()); continue
                    j += 2; continue
                if ch == b"(": depth += 1
                elif ch == b")":
                    depth -= 1
                    if not depth: break
                buf.append(ch.decode("cp1252", "replace")); j += 1
            toks.append(("S", "".join(buf))); i = j + 1
        elif c == b"<" and s[i:i+2] == b"<<":
            toks.append(("O", "<<")); i += 2
        elif c == b">" and s[i:i+2] == b">>":
            toks.append(("O", ">>")); i += 2
        elif c in b"[]":
            toks.append(("O", c.decode())); i += 1
        elif c.isspace():
            i += 1
        else:
            m = re.match(rb"[^\s()\[\]<>/]+|/[^\s()\[\]<>/]*|<[0-9A-Fa-f\s]*>", s[i:])
            if not m:
                i += 1; continue
            toks.append(("O", m.group().decode("latin-1"))); i += m.end()
    return toks

out = []
for m in re.finditer(rb"stream\r?\n", data):
    start = m.end(); end = data.find(b"endstream", start)
    try:
        s = zlib.decompress(data[start:end])
    except Exception:
        continue
    if b"BT" not in s:
        continue
    pend, line, dict_depth = [], [], 0
    for kind, v in strings(s):
        if kind == "O" and v == "<<": dict_depth += 1; continue
        if kind == "O" and v == ">>": dict_depth -= 1; pend = []; continue
        if dict_depth: continue
        if kind == "S":
            pend.append(v)
        elif v in ("Tj", "TJ", "'", '"'):
            line.extend(pend); pend = []
        elif v in ("Td", "TD", "T*", "ET"):
            if line: out.append("".join(line)); line = []
            pend = []
        elif v in ("[",):
            pass
        elif v == "]":
            pass
        elif re.match(r"^-?\d+\.?\d*$", v):
            if float(v) < -250 and pend: pend.append(" ")
        else:
            pend = [] if v not in ("[", "]") else pend
    if line: out.append("".join(line))
open(sys.argv[2], "w", encoding="utf-8").write("\n".join(out))
print(len(out), "lines")
