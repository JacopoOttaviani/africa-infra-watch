import json, math, re
S=json.load(open('brand/africa_shape.json'))
def path(pts):
    return 'M'+' L'.join(f'{x:.1f} {y:.1f}' for x,y in pts)+'Z'
AFRICA = path(S['mainland'])+' '+path(S['madagascar'])
c=S['circle']; CX,CY=c['cx'],c['cy']; R=c['r']*0.98   # compass fits inside the mainland with margin

GREEN='#1F5F4B'; INK='#16211C'; PAPER='#F8FAF6'; MINT='#5FB495'; AMBER='#B7810F'

def star(cx,cy,r_long,r_short,rot=0,n=4):
    pts=[]
    for i in range(n*2):
        a=math.radians(rot-90+i*180/n)
        r=r_long if i%2==0 else r_short
        pts.append((cx+r*math.cos(a),cy+r*math.sin(a)))
    return path(pts)

def needle(cx,cy,r,w):
    # north half and south half as separate paths
    n=path([(cx,cy-r),(cx+w,cy),(cx-w,cy)])
    s=path([(cx,cy+r),(cx-w,cy),(cx+w,cy)])
    return n,s

def ticks(cx,cy,r_out,r_in,n,stroke,sw,skip_cardinal=False):
    out=[]
    for i in range(n):
        if skip_cardinal and i%(n//4)==0: continue
        a=math.radians(i*360/n-90)
        out.append(f'<line x1="{cx+r_in*math.cos(a):.1f}" y1="{cy+r_in*math.sin(a):.1f}" x2="{cx+r_out*math.cos(a):.1f}" y2="{cy+r_out*math.sin(a):.1f}" stroke="{stroke}" stroke-width="{sw}" stroke-linecap="round"/>')
    return '\n'.join(out)

def svg(body,bg=None,size=1000):
    bgrect=f'<rect width="{size}" height="{size}" fill="{bg}"/>' if bg else ''
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" width="{size}" height="{size}">\n{bgrect}\n{body}\n</svg>\n'

# ---------- Option A: Cut-out compass rose (solid continent, negative-space rose) ----------
def option_a(fill=GREEN):
    r=R
    ring_o, ring_i = r*0.98, r*0.86
    rose=star(CX,CY,r*0.78,r*0.22)          # N-E-S-W
    rose2=star(CX,CY,r*0.46,r*0.14,rot=45)  # diagonals, smaller
    body=f'''<defs>
  <mask id="cut">
    <rect width="1000" height="1000" fill="white"/>
    <circle cx="{CX}" cy="{CY}" r="{ring_o:.1f}" fill="black"/>
    <circle cx="{CX}" cy="{CY}" r="{ring_i:.1f}" fill="white"/>
    <path d="{rose}" fill="black"/>
    <path d="{rose2}" fill="black"/>
    <circle cx="{CX}" cy="{CY}" r="{r*0.07:.1f}" fill="white"/>
  </mask>
</defs>
<path d="{AFRICA}" fill="{fill}" mask="url(#cut)" fill-rule="evenodd"/>'''
    return svg(body)

# ---------- Option B: Outline continent, two-tone needle ----------
def option_b(stroke=INK, north=GREEN, south='#A8B4AC'):
    r=R*0.95
    n,s=needle(CX,CY,r*0.78,r*0.16)
    body=f'''<path d="{AFRICA}" fill="none" stroke="{stroke}" stroke-width="22" stroke-linejoin="round"/>
<circle cx="{CX}" cy="{CY}" r="{r:.1f}" fill="none" stroke="{stroke}" stroke-width="14"/>
{ticks(CX,CY,r*0.88,r*0.74,4,stroke,14)}
<path d="{n}" fill="{north}"/>
<path d="{s}" fill="{south}"/>
<circle cx="{CX}" cy="{CY}" r="{r*0.09:.1f}" fill="{stroke}"/>'''
    return svg(body)

# ---------- Option C: Solid continent, fine-line compass with dotted bearing ring ----------
def option_c(fill=INK, line=PAPER, accent=MINT):
    r=R*0.96
    n,s=needle(CX,CY,r*0.62,r*0.11)
    body=f'''<path d="{AFRICA}" fill="{fill}"/>
<circle cx="{CX}" cy="{CY}" r="{r:.1f}" fill="none" stroke="{line}" stroke-width="10"/>
{ticks(CX,CY,r*0.98,r*0.80,4,line,10)}
{ticks(CX,CY,r*0.98,r*0.90,24,line,6,skip_cardinal=True)}
<path d="{n}" fill="{accent}"/>
<path d="{s}" fill="{line}"/>
<circle cx="{CX}" cy="{CY}" r="{r*0.07:.1f}" fill="{fill}" stroke="{line}" stroke-width="8"/>'''
    return svg(body)

opts={
 'option-a-cutout-rose': option_a(),
 'option-b-outline-needle': option_b(),
 'option-c-solid-fineline': option_c(),
}
# mono / inverse variants for sheet
opts['option-a-cutout-rose-mono']=option_a(fill=INK)
opts['option-a-cutout-rose-inverse']=option_a(fill=PAPER)
opts['option-b-outline-needle-inverse']=option_b(stroke=PAPER,north=MINT,south='#6E7A75')
opts['option-c-solid-fineline-inverse']=option_c(fill=PAPER,line=INK,accent=GREEN)

for k,v in opts.items():
    open(f'brand/{k}.svg','w').write(v)

# ---------- Site assets (option A is the chosen mark) ----------
def compact(svg_text):
    # round coordinates to integers so the data URI / inline markup stays small
    return re.sub(r'(\d+)\.\d+', r'\1', svg_text)

# Header mark: option A in currentColor, so CSS decides the colour (accent, dark mode).
mark = compact(option_a(fill='currentColor')).replace('width="1000" height="1000"','width="1em" height="1em"',1)
mark = mark.replace('id="cut"','id="aiw-cut"').replace('url(#cut)','url(#aiw-cut)')
open('brand/mark.svg','w').write(mark)

# Favicon: rounded green tile, paper continent, simplified four-point rose (no ring,
# no diagonals) so it still reads at 16 px.
def favicon():
    r=R
    rose=star(CX,CY,r*0.92,r*0.30)
    body=f'''<defs>
  <mask id="f">
    <rect width="1000" height="1000" fill="white"/>
    <path d="{rose}" fill="black"/>
    <circle cx="{CX}" cy="{CY}" r="{r*0.09:.1f}" fill="white"/>
  </mask>
</defs>
<rect width="1000" height="1000" rx="180" fill="{GREEN}"/>
<g transform="translate(60 60) scale(.88)"><path d="{AFRICA}" fill="{PAPER}" mask="url(#f)"/></g>'''
    return svg(body)
fav=compact(favicon())
# mask must not be scaled with the group: recompute — simpler to put the mask on the group
fav=fav.replace('mask="url(#f)"/></g>','/></g>').replace('<g transform="translate(60 60) scale(.88)">','<g transform="translate(60 60) scale(.88)" mask="url(#f)">')
open('brand/favicon.svg','w').write(fav)

# ---------- Preview sheet ----------
def inline(k,w=220):
    return opts[k].replace('width="1000" height="1000"',f'width="{w}" height="{w}"',1)
def lockup(k,color,name='Africa Infra Watch',sub='Infrastructure, mapped from open data'):
    return f'''<div class="lockup"><div class="mark">{inline(k,96)}</div>
<div><div class="wm" style="color:{color}">{name}</div><div class="sub" style="color:{color};opacity:.6">{sub}</div></div></div>'''

card=lambda title,desc,light,dark,lk_l,lk_d: f'''
<section class="card">
  <h2>{title}</h2><p>{desc}</p>
  <div class="row">
    <div class="tile light">{inline(light)}{lockup(lk_l,INK)}</div>
    <div class="tile dark">{inline(dark)}{lockup(lk_d,PAPER)}</div>
    <div class="tile light small">{inline(light,64)}{inline(light,32)}{inline(light,16)}<span>64 / 32 / 16 px</span></div>
  </div>
</section>'''

html=f'''<!doctype html><html><head><meta charset="utf-8"><title>Africa Infra Watch logo options</title>
<style>
:root{{--paper:#EDF0EC;--ink:#16211C;--rule:#C6D0C8;--display:"Archivo","Helvetica Neue",Arial,sans-serif;--mono:"IBM Plex Mono",ui-monospace,Menlo,monospace}}
body{{margin:0;background:var(--paper);color:var(--ink);font-family:var(--display);padding:40px 24px}}
h1{{font-size:22px;margin:0 0 6px}} .lead{{color:#586760;margin:0 0 32px;font-size:14px}}
.card{{border-top:1px solid var(--rule);padding:24px 0 32px}}
h2{{font-size:16px;margin:0 0 4px;font-family:var(--mono);font-weight:500}} .card p{{margin:0 0 18px;font-size:14px;color:#3E4B44;max-width:70ch}}
.row{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px}}
.tile{{border-radius:8px;padding:28px;display:flex;flex-direction:column;align-items:center;gap:22px;min-height:340px;justify-content:center}}
.light{{background:#F8FAF6;border:1px solid var(--rule)}} .dark{{background:#0F1512}}
.small{{flex-direction:row;align-items:flex-end;gap:20px;flex-wrap:wrap}} .small span{{font-family:var(--mono);font-size:11px;color:#586760;width:100%;text-align:center}}
.lockup{{display:flex;align-items:center;gap:14px}} .wm{{font-weight:700;font-size:20px;letter-spacing:-.01em}} .sub{{font-size:12px;font-family:var(--mono)}}
</style></head><body>
<h1>Africa Infra Watch — logo options</h1>
<p class="lead">Compass inside the African continent. The outline is traced from the project's own Natural Earth basemap; the compass sits at the largest circle that fits inside the mainland. Three directions, each shown on light and dark, with wordmark lockup and small-size check.</p>
{card('A — Cut-out compass rose','Solid continent in the project green with an eight-point compass rose cut out as negative space. One colour, one shape: works as a favicon, a stamp, or a knocked-out mark on photos.','option-a-cutout-rose','option-a-cutout-rose-inverse','option-a-cutout-rose','option-a-cutout-rose-inverse')}
{card('B — Outline with two-tone needle','Continent drawn as a thick outline, with a bezel ring and a needle inside. North needle in green, south in grey. Lighter, more editorial; reads as a map instrument rather than a badge.','option-b-outline-needle','option-b-outline-needle-inverse','option-b-outline-needle','option-b-outline-needle-inverse')}
{card('C — Solid continent, fine-line bearing ring','Dark silhouette with a thin bearing ring, 24 tick marks and a mint north needle: the dashboard&apos;s dark-mode palette. Most instrument-like of the three; the tick ring drops away cleanly at small sizes.','option-c-solid-fineline','option-c-solid-fineline-inverse','option-c-solid-fineline','option-c-solid-fineline-inverse')}
</body></html>'''
open('brand/logo-options.html','w').write(html)
print('\n'.join(sorted(opts)))
