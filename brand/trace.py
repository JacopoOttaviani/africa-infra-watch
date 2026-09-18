import json, math
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

d = json.load(open('data/africa_basemap.json'))
# bounds
lons=[];lats=[]
rings=[]
for c in d['countries']:
    for poly in c['p']:
        for ring in poly[:1]:  # outer rings only
            rings.append(ring)
            for x,y in ring: lons.append(x); lats.append(y)
minx,maxx,miny,maxy=min(lons),max(lons),min(lats),max(lats)
print('bounds',minx,maxx,miny,maxy)
S=1400
pad=20
W=int((maxx-minx)/(maxy-miny)*S)+2*pad; H=S+2*pad
def proj(x,y):
    return (pad+(x-minx)/(maxx-minx)*(W-2*pad), pad+(maxy-y)/(maxy-miny)*(H-2*pad))
img=Image.new('L',(W,H),0)
dr=ImageDraw.Draw(img)
for ring in rings:
    pts=[proj(x,y) for x,y in ring]
    if len(pts)>=3: dr.polygon(pts,fill=255,outline=255)
# close seams between countries
img=img.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.MinFilter(5))
m=np.array(img)>127
# connected components (BFS) - keep the largest (mainland) and Madagascar (2nd largest)
from collections import deque
lab=np.zeros(m.shape,int); n=0; sizes={}
for y in range(H):
    for x in range(W):
        if m[y,x] and lab[y,x]==0:
            n+=1; q=deque([(y,x)]); lab[y,x]=n; s=0
            while q:
                cy,cx=q.popleft(); s+=1
                for dy,dx in ((1,0),(-1,0),(0,1),(0,-1)):
                    ny,nx=cy+dy,cx+dx
                    if 0<=ny<H and 0<=nx<W and m[ny,nx] and lab[ny,nx]==0:
                        lab[ny,nx]=n; q.append((ny,nx))
            sizes[n]=s
top=sorted(sizes,key=sizes.get,reverse=True)[:2]
print('components',len(sizes),[sizes[t] for t in top])

def trace(mask):
    # Moore-neighbour boundary trace of outer contour
    ys,xs=np.nonzero(mask)
    i=np.argmin(ys*10000+xs); sy,sx=ys[i],xs[i]
    dirs=[(0,1),(1,1),(1,0),(1,-1),(0,-1),(-1,-1),(-1,0),(-1,1)] # clockwise starting east (y down)
    def inside(y,x): return 0<=y<mask.shape[0] and 0<=x<mask.shape[1] and mask[y,x]
    cont=[(sy,sx)]; cy,cx=sy,sx; b=6  # backtrack dir index (came from west/north)
    # standard: start searching from the backtrack direction
    prev=4
    while True:
        found=False
        for k in range(8):
            di=(prev+k)%8
            ny,nx=cy+dirs[di][0],cx+dirs[di][1]
            if inside(ny,nx):
                cont.append((ny,nx)); cy,cx=ny,nx
                prev=(di+5)%8  # backtrack: opposite direction +1
                found=True; break
        if not found: break
        if (cy,cx)==(sy,sx) and len(cont)>2: break
        if len(cont)>200000: break
    return [(x,y) for y,x in cont]

def dp(pts,eps):
    if len(pts)<3: return pts
    def pd(p,a,b):
        ax,ay=a;bx,by=b;px,py=p
        dx,dy=bx-ax,by-ay
        if dx==dy==0: return math.hypot(px-ax,py-ay)
        t=max(0,min(1,((px-ax)*dx+(py-ay)*dy)/(dx*dx+dy*dy)))
        return math.hypot(px-(ax+t*dx),py-(ay+t*dy))
    dmax=0;idx=0
    for i in range(1,len(pts)-1):
        dd=pd(pts[i],pts[0],pts[-1])
        if dd>dmax: dmax=dd;idx=i
    if dmax>eps:
        return dp(pts[:idx+1],eps)[:-1]+dp(pts[idx:],eps)
    return [pts[0],pts[-1]]

def chaikin(pts,it=2):
    for _ in range(it):
        out=[]
        n=len(pts)
        for i in range(n):
            p=pts[i];q=pts[(i+1)%n]
            out.append((0.75*p[0]+0.25*q[0],0.75*p[1]+0.25*q[1]))
            out.append((0.25*p[0]+0.75*q[0],0.25*p[1]+0.75*q[1]))
        pts=out
    return pts

out={}
for name,comp,eps in (('mainland',top[0],9),('madagascar',top[1],7)):
    c=trace(lab==comp)
    s=dp(c,eps)
    print(name,len(c),'->',len(s))
    out[name]=chaikin(s,2)

# max inscribed circle in mainland (erosion)
main=(lab==top[0])
er=Image.fromarray((main*255).astype('uint8'))
r=0;last=er
while True:
    nxt=er.filter(ImageFilter.MinFilter(3))
    if not np.array(nxt).any(): break
    last=nxt; er=nxt; r+=1
ys,xs=np.nonzero(np.array(last)>127)
cx,cy=float(xs.mean()),float(ys.mean())
print('inscribed center',cx,cy,'radius~',r)
ys,xs=np.nonzero(main); print('centroid',xs.mean(),ys.mean())
# normalise everything to a 0..1000 box
allp=[p for v in out.values() for p in v]
bx0=min(p[0] for p in allp);bx1=max(p[0] for p in allp);by0=min(p[1] for p in allp);by1=max(p[1] for p in allp)
sc=1000/max(bx1-bx0,by1-by0)
ox=(1000-(bx1-bx0)*sc)/2; oy=(1000-(by1-by0)*sc)/2
def N(p): return (round((p[0]-bx0)*sc+ox,1),round((p[1]-by0)*sc+oy,1))
res={k:[N(p) for p in v] for k,v in out.items()}
res['circle']={'cx':round((cx-bx0)*sc+ox,1),'cy':round((cy-by0)*sc+oy,1),'r':round(r*sc,1)}
res['size']=1000
json.dump(res,open('brand/africa_shape.json','w'))
print(res['circle'])
