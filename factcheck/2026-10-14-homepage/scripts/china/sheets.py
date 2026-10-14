import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from xlsxread import read_xlsx_sheet
src = sys.argv[1]
for sh in sys.argv[2:]:
    print("=====", sh)
    for r in read_xlsx_sheet(src, sh):
        cells = [str(c) for c in r if c is not None]
        if cells: print(" | ".join(cells))
