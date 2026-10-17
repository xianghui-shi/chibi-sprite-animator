"""示例线稿生成器：用代码画一张米黄纸、深灰抖动线、红橙蓝点缀的无文字线稿（奇奇松鼠故事）。
输出路径见文件末尾；正式项目线稿建议用生图模型（须符合：无文字、纸色 #F5EBD7、少量点缀色）。"""
import math, random, cairosvg
random.seed(7)
W,H=1672,941
INK="#4a4a4a"; OR="#EFA24E"; RD="#D8574B"; BL="#6FA3D8"
out=[]
def j(p,a=2.2): return (p[0]+random.uniform(-a,a),p[1]+random.uniform(-a,a))
def smooth(pts,closed=False):
    pts=[j(p) for p in pts]
    n=len(pts)
    if closed:
        mid=[((pts[i][0]+pts[(i+1)%n][0])/2,(pts[i][1]+pts[(i+1)%n][1])/2) for i in range(n)]
        d=f"M{mid[-1][0]:.1f},{mid[-1][1]:.1f} "
        for i in range(n):
            d+=f"Q{pts[i][0]:.1f},{pts[i][1]:.1f} {mid[i][0]:.1f},{mid[i][1]:.1f} "
        return d+"Z"
    d=f"M{pts[0][0]:.1f},{pts[0][1]:.1f} "
    for i in range(1,n-1):
        mx=(pts[i][0]+pts[i+1][0])/2; my=(pts[i][1]+pts[i+1][1])/2
        d+=f"Q{pts[i][0]:.1f},{pts[i][1]:.1f} {mx:.1f},{my:.1f} "
    d+=f"L{pts[-1][0]:.1f},{pts[-1][1]:.1f}"
    return d
def path(pts,closed=False,fill="none",sw=5,col=INK):
    out.append(f'<path d="{smooth(pts,closed)}" fill="{fill}" stroke="{col}" stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round"/>')
def ell(cx,cy,rx,ry,fill="none",n=14,rot=0,sw=5):
    pts=[]
    for i in range(n):
        t=2*math.pi*i/n
        x=rx*math.cos(t); y=ry*math.sin(t)
        c,s=math.cos(rot),math.sin(rot)
        pts.append((cx+x*c-y*s,cy+x*s+y*c))
    path(pts,True,fill,sw)
def blob(cx,cy,r,fill="none",bumps=7,amp=0.18,sw=5,sx=1.0):
    pts=[]
    n=bumps*4
    for i in range(n):
        t=2*math.pi*i/n
        rr=r*(1+amp*math.sin(bumps*t))
        pts.append((cx+rr*math.cos(t)*sx,cy+rr*math.sin(t)))
    path(pts,True,fill,sw)
def dot(x,y,r=5,col=INK): out.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{col}"/>')
def squirrel(cx,cy,s=1.0,rot=0,tail_up=True):
    out.append(f'<g transform="translate({cx},{cy}) rotate({rot}) scale({s})">')
    # tail
    path([(30,10),(85,-10),(105,-70),(80,-125),(40,-110),(55,-70),(30,-30)],True,OR,5)
    path([(70,-95),(90,-60)],sw=3)
    ell(0,10,42,52,"#fff8ea")              # body
    ell(0,25,22,30,"#F5EBD7",sw=3)         # belly
    ell(-5,-55,34,30,"#fff8ea")            # head
    path([(-30,-72),(-42,-110),(-12,-84)],True,OR,5)  # ear
    path([(8,-82),(24,-116),(30,-76)],True,OR,5)
    dot(-14,-58,4.5); dot(8,-58,4.5)
    path([(-6,-46),(-2,-42),(2,-46)],sw=3)
    ell(-26,-46,6,5,RD,8,sw=2)
    path([(-20,20),(-45,45),(-30,60)],sw=4)  # arm
    path([(-18,55),(-30,80),(-5,82)],sw=4)
    out.append('</g>')
def cloud(cx,cy,sc=1.0,fill="none"):
    pts=[(-150,40),(-165,0),(-120,-30),(-85,-60),(-30,-80),(20,-55),(60,-85),(125,-55),(150,-15),(175,25),(130,45),(60,55),(-30,52),(-100,55)]
    path([(cx+x*sc,cy+y*sc) for x,y in pts],True,fill,5)
def pine(cx,cy,sc=1.0):
    path([(cx,cy-50*sc),(cx-28*sc,cy-15*sc),(cx-22*sc,cy+30*sc),(cx,cy+52*sc),(cx+22*sc,cy+30*sc),(cx+28*sc,cy-15*sc)],True,"#F2C14E",5)
    for k in (-20,0,22):
        path([(cx-24*sc,cy+k*sc),(cx,cy+(k+14)*sc),(cx+24*sc,cy+k*sc)],sw=3)
    path([(cx,cy-50*sc),(cx+4*sc,cy-72*sc)],sw=5)
def tree(x,base,top,w,canopy_r):
    path([(x-w,base),(x-w*0.7,(base+top)/2),(x-w*0.45,top+canopy_r*0.6)])
    path([(x+w,base),(x+w*0.7,(base+top)/2),(x+w*0.45,top+canopy_r*0.6)])
    blob(x,top,canopy_r,bumps=6,amp=0.14)
def swirl(cx,cy,sc,col=BL):
    pts=[]
    for i in range(30):
        t=i/29*5.2
        r=8+18*t
        pts.append((cx+sc*r*math.cos(t),cy+sc*r*math.sin(t)*0.8))
    path(pts,sw=5,col=col)

# ground
path([(20,880),(200,872),(420,884),(600,876)],sw=4)
# LEFT: forest
tree(130,880,420,34,120)
tree(470,880,540,22,85)
tree(330,880,430,18,60)
# tall tree with pinecone
tree(250,880,150,26,100)
pine(250,70,0.8)
path([(215,35),(235,10)],sw=3,col=OR); path([(285,35),(268,12)],sw=3,col=OR)
squirrel(180,800,0.62,0)
path([(60,880),(52,850),(70,856),(78,880)],sw=3)
# CENTER: wind + falling squirrel
for (x,y,s) in [(640,250,1.0),(900,170,1.2),(1020,420,0.9)]:
    swirl(x,y,s)
path([(620,330),(760,300),(880,320),(1010,280)],sw=5,col=BL)
path([(640,640),(780,610),(910,630),(1050,590)],sw=5,col=BL)
# leaves
for (x,y,a) in [(700,430,-30),(980,520,40),(850,720,10)]:
    out.append(f'<g transform="translate({x},{y}) rotate({a})">')
    path([(-22,0),(0,-14),(24,0),(0,14)],True,RD,4); path([(-22,0),(26,0)],sw=3)
    out.append('</g>')
squirrel(820,480,0.95,rot=-65)
# motion marks
for (x,y) in [(900,330),(930,380),(960,350)]:
    path([(x,y),(x-22,y+40)],sw=4)
# RIGHT: cloud + sky castle
cloud(1400,720,1.15,"#fff8ea")
cloud(1210,560,0.55,"#fff8ea")
cloud(1590,520,0.5,"#fff8ea")
# castle
def rect(x,y,w,h,fill="none"): path([(x,y),(x+w,y),(x+w,y+h),(x,y+h)],True,fill,5)
rect(1300,350,200,170,"#fff8ea")
rect(1260,300,70,220,"#fff8ea"); rect(1470,300,70,220,"#fff8ea")
path([(1250,300),(1295,230),(1340,300)],True,BL,5); path([(1460,300),(1505,230),(1550,300)],True,BL,5)
path([(1295,230),(1295,190)],sw=4); path([(1295,190),(1330,200),(1295,212)],True,RD,3)
path([(1370,520),(1370,440),(1400,415),(1430,440),(1430,520)],True,"#F5EBD7",4)
for x in (1285,1495): rect(x,350,20,34)
# small clouds + stars-ish
cloud(1260,200,0.4); cloud(1580,200,0.35)
squirrel(1400,580,0.5,rot=8)

svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}"><rect width="{W}" height="{H}" fill="#F5EBD7"/>'+"".join(out)+'</svg>'
open("scene-01-squirrel.svg","w").write(svg)
cairosvg.svg2png(bytestring=svg.encode(),write_to="scene-01-squirrel.png")
