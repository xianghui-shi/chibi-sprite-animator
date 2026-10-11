# 矢量轨迹引擎：用"画在背景图上的轨迹线 + 几处车的大小"控制位置、方向和压弯
# 轨迹 JSON（traj_*.json）：
#   path   : [[x, y], ...]   车轮接地点路线（画面像素坐标），按行驶方向排列
#   size   : [[u, h], ...]   在轨迹进度 u(0~1) 处，车（含人）的像素高度；≥2 个
#   frames : 镜头总帧数；enter / exit：车在第几帧到达 u=0 / u=1
#   speed  : 车速 km/h（用于压弯角度）；focal：等效焦距像素（默认=画面宽）
# 原理：近大远小 → 深度 Z = f·Hb / h，横向 X = (x - cx)·Hb / h（Hb = 车高 1.2 m）。
#       在 (X, Z) 地面坐标里按真实距离匀速前进；切线 = 行进方向矢量；曲率 κ → 压弯角 atan(v²κ/g)。
#       方向矢量与镜头的夹角 yaw：0° 朝镜头来，±90° 横穿，±180° 远离 → 选用 车头3/4 / 侧面 / 车尾3/4 视图，左右自动镜像。
import numpy as np, json, math
from scipy.interpolate import PchipInterpolator, CubicSpline

HB = 1.2   # 车+人高度（米）

class Trajectory:
    def __init__(self, spec, W=1280, H=720):
        if isinstance(spec, str): spec = json.load(open(spec))
        self.spec = spec; self.W, self.H = W, H
        P = np.array(spec['path'], float)
        # 过所有点的平滑曲线（按弦长参数化的三次样条）
        d = np.r_[0, np.cumsum(np.hypot(*np.diff(P, axis=0).T))]; d /= d[-1]
        self.sx, self.sy = CubicSpline(d, P[:, 0], bc_type='natural'), CubicSpline(d, P[:, 1], bc_type='natural')
        su = np.array(spec['size'], float)
        self.sh = PchipInterpolator(su[:, 0], np.log(su[:, 1]), extrapolate=True)
        self.f = spec.get('focal', W); cx = W / 2
        # 稠密采样 → 地面坐标 (X, Z) → 真实弧长
        u = np.linspace(0, 1, 4001); x, y, h = self.sx(u), self.sy(u), np.exp(self.sh(u))
        X, Z = (x - cx) * HB / h, self.f * HB / h
        if spec.get('metric', 'ground') == 'screen':
            # 画面度量：每帧移动的像素 ∝ 车的大小（远处慢、近处快），不让纵深的透视放大把时间全吃掉
            hm = (h[1:] + h[:-1]) / 2; ds = np.hypot(np.diff(x), np.diff(y)) / hm * HB
        else:
            ds = np.hypot(np.diff(X), np.diff(Z))
        S = np.r_[0, np.cumsum(ds)]
        self.u, self.X, self.Z, self.S = u, X, Z, S
        self.length_m = S[-1]
        # 曲率（地面坐标）
        dX, dZ = np.gradient(X, S), np.gradient(Z, S); ddX, ddZ = np.gradient(dX, S), np.gradient(dZ, S)
        k = (dX * ddZ - dZ * ddX) / np.maximum((dX ** 2 + dZ ** 2) ** 1.5, 1e-9)
        k = np.convolve(k, np.ones(81) / 81, mode='same')                 # 平滑，避免压弯抖动
        self.kappa, self.dX, self.dZ = k, dX, dZ
        self.v = spec.get('speed', 150) / 3.6
        # 可选：手动压弯关键帧 lean=[[u, 度], ...] 和弯道方向 turn（-1 右弯 / +1 左弯），比由曲率推算更稳
        self.lean_k = PchipInterpolator(*np.array(spec['lean'], float).T) if 'lean' in spec else None
        self.turn_fix = spec.get('turn')
        # 可选：速度曲线 speed_k=[[u, km/h], ...]（刹车入弯、弯心最慢、出弯加速）。时间 = ∫ ds / v
        if 'speed_k' in spec:
            sk = np.array(spec['speed_k'], float); vv = np.interp(self.u, sk[:, 0], sk[:, 1]) / 3.6
            dt = np.diff(self.S) / ((vv[1:] + vv[:-1]) / 2); self.T = np.r_[0, np.cumsum(dt)]; self.vv = vv
        else:
            self.T = None

    def yaw_track(self, max_rate=7.0, sigma=3.0):
        """整段镜头的车头朝向：先展开角度、高斯平滑，再限制每帧最多转 max_rate 度——车头只能顺着弯道连续转，不能掉头"""
        from scipy.ndimage import gaussian_filter1d
        F = np.arange(self.spec['enter'], self.spec['exit'] + 1)
        y = np.unwrap(np.radians([self._raw(i)['yaw'] for i in F])); y = gaussian_filter1d(y, sigma, mode='nearest')
        y = np.degrees(y); out = [y[0]]
        for v in y[1:]: out.append(out[-1] + float(np.clip(v - out[-1], -max_rate, max_rate)))
        self._yaw = dict(zip(F.tolist(), out))

    def at(self, i):
        a = self._raw(i)
        if getattr(self, '_yaw', None) is None: self.yaw_track()
        ii = min(max(i, self.spec['enter']), self.spec['exit']); k0 = int(math.floor(ii)); k1 = min(self.spec['exit'], k0 + 1); f = ii - k0
        a['yaw'] = (((1 - f) * self._yaw[k0] + f * self._yaw[k1] + 180) % 360) - 180   # 子帧之间也连续
        return a

    def _raw(self, i):
        """第 i 帧：返回 dict(x, y, h, yaw, lean, dir, visible)；dir 是画面上的行进方向单位矢量"""
        e, x_ = self.spec['enter'], self.spec['exit']
        p = (i - e) / max(1e-6, x_ - e)
        vis = 0 <= p <= 1
        p = min(1.0, max(0.0, p))
        if self.T is not None: s = float(np.interp(p * self.T[-1], self.T, self.S))   # 按速度曲线走
        else: s = p * self.length_m                                       # 按真实距离匀速
        u = float(np.interp(s, self.S, self.u))
        x, y, h = float(self.sx(u)), float(self.sy(u)), float(np.exp(self.sh(u)))
        dX, dZ = float(np.interp(s, self.S, self.dX)), float(np.interp(s, self.S, self.dZ))
        yaw = math.degrees(math.atan2(dX, -dZ))                           # 0 朝镜头来，+90 向右横穿，±180 远离
        k = float(np.interp(s, self.S, self.kappa))
        v = float(np.interp(s, self.S, self.vv)) if self.T is not None else self.v
        lean = math.degrees(math.atan(v ** 2 * abs(k) / 9.81))            # 压弯角（只取大小）
        lean = min(lean, 55.0)
        if self.lean_k is not None: lean = float(np.clip(self.lean_k(u), 0, 60))
        turn = self.turn_fix if self.turn_fix is not None else float(np.sign(k))
        du = 1e-3; x2, y2 = float(self.sx(min(1, u + du))), float(self.sy(min(1, u + du)))
        dv = np.array([x2 - x, y2 - y]); dv = dv / (np.linalg.norm(dv) + 1e-9)
        return dict(x=x, y=y, h=h, yaw=yaw, lean=lean, turn=turn, dir=dv, visible=vis, u=u)

def view_for(yaw):
    """按方向选视图：('front'|'side'|'rear', mirror)。素材基准方向：front 朝镜头偏左，side 向右，rear 远离偏右。"""
    a = abs(yaw)
    if a < 50: return 'front', yaw > 0          # 朝镜头来：素材本身偏向画面左侧，向右来时镜像
    if a < 130: return 'side', yaw < 0          # 横穿：素材向右，向左时镜像
    return 'rear', yaw < 0                       # 远离：素材偏右，向左远去时镜像

# ---------- 素材登记：每套 sprite 的基准方向 ----------
# yaw：素材里车头朝向（0=朝镜头，+90=向画面右，180=远离）；turn：-1 右弯，+1 左弯（素材压弯的方向）；max_lean：第 8 帧的压弯角
# 镜像后 yaw 取反、turn 取反（右弯变左弯）
def choose(sets, yaw, lean, turn, prev=None):
    """sets: {name: dict(yaw, turn, max_lean)}；返回 (name, mirror, frame_float)。压弯方向必须一致，再选朝向最接近的。"""
    best = None
    for name, s in sets.items():
        for mir in (False, True):
            by, bt = (-s['yaw'], -s['turn']) if mir else (s['yaw'], s['turn'])
            d = abs((yaw - by + 180) % 360 - 180)
            if lean > 8 and bt != turn: d += 1000                     # 压弯方向不对：除非没得选
            if prev is not None and (name, mir) == prev[:2]: d -= 12      # 迟滞，避免来回跳
            if best is None or d < best[0]: best = (d, name, mir, s)
    d, name, mir, s = best
    f = min(7.0, lean / s['max_lean'] * 7)
    return name, mir, f, d >= 1000

def overlay(plate_bgr, tr, frames, path_pts=None):
    """把轨迹画在背景上检查：黄线=路线，箭头=行进方向，数字=帧号，方框=车的大小"""
    import cv2
    im = plate_bgr.copy()
    u = np.linspace(0, 1, 400); pts = np.stack([tr.sx(u), tr.sy(u)], 1).astype(int)
    cv2.polylines(im, [pts], False, (0, 255, 255), 2)
    if path_pts is not None:
        for p in path_pts: cv2.circle(im, (int(p[0]), int(p[1])), 5, (0, 0, 255), -1)
    for i in frames:
        a = tr.at(i); x, y, h = int(a['x']), int(a['y']), a['h']; d = a['dir']
        cv2.rectangle(im, (int(x - 0.75 * h), int(y - h)), (int(x + 0.75 * h), y), (255, 255, 255), 1)
        cv2.arrowedLine(im, (x, y), (int(x + d[0] * 40), int(y + d[1] * 40)), (0, 0, 255), 2, tipLength=0.35)
        cv2.putText(im, f'{i} y{a["yaw"]:.0f} L{a["lean"]:.0f}', (x + 6, y - int(h) - 4), 0, 0.42, (255, 255, 255), 1)
    return im

# ---------- 赛道约束：轨迹放在路面中间，可以压边，不能越线 ----------
def asphalt_mask(plate_bgr, y_top=0):
    """识别沥青：低饱和、中等亮度、中性灰；取最大连通块并填小洞（轮胎印、反光）"""
    import cv2
    hsv = cv2.cvtColor(plate_bgr, cv2.COLOR_BGR2HSV).astype(np.float32)
    lab = cv2.cvtColor(plate_bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
    s, v, a, b = hsv[..., 1], hsv[..., 2], lab[..., 1] - 128, lab[..., 2] - 128
    m = ((s < 40) & (v > 60) & (v < 175) & (np.abs(a) < 8) & (np.abs(b) < 10)).astype(np.uint8) * 255
    m[:y_top] = 0
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    n, lb, st, _ = cv2.connectedComponentsWithStats(m); k = 1 + np.argmax(st[1:, cv2.CC_STAT_AREA])
    m = ((lb == k) * 255).astype(np.uint8)
    inv = cv2.bitwise_not(m); n2, lb2, st2, _ = cv2.connectedComponentsWithStats(inv)
    for j in range(1, n2):
        if st2[j, cv2.CC_STAT_AREA] < 4000: m[lb2 == j] = 255
    return m > 0

def _edges(mask, x, y, nx, ny, lim=900):
    """沿法线两侧走到路面边缘；碰到画面边界记为 None（路面延伸到画外）"""
    H, W = mask.shape; out = []
    for sgn in (-1, 1):
        e = None
        for d in range(1, lim):
            px, py = int(round(x + sgn * nx * d)), int(round(y + sgn * ny * d))
            if not (0 <= px < W and 0 <= py < H): break
            if not mask[py, px]: e = d - 1; break
        out.append(e)
    return out   # [左侧距离, 右侧距离]（沿 -n / +n）

def fit_to_track(spec, mask, lane=0.5, margin_k=0.45, iters=4):
    """把 spec['path'] 推到路面中间：lane=0.5 正中；margin = margin_k × 车高（车身半宽 + 余量）。返回新 path 和每点余量报告"""
    sp = dict(spec)
    for _ in range(iters):
        tr = Trajectory(sp); u = np.linspace(0, 1, 40); pts = []
        for uu in u:
            x, y = float(tr.sx(uu)), float(tr.sy(uu)); h = float(np.exp(tr.sh(uu)))
            dx, dy = float(tr.sx(min(1, uu + 1e-3)) - tr.sx(max(0, uu - 1e-3))), float(tr.sy(min(1, uu + 1e-3)) - tr.sy(max(0, uu - 1e-3)))
            L = math.hypot(dx, dy) + 1e-9; nx, ny = -dy / L, dx / L
            if not mask[min(mask.shape[0] - 1, max(0, int(y))), min(mask.shape[1] - 1, max(0, int(x)))]:
                ys, xs = np.nonzero(mask); j = np.argmin((xs - x) ** 2 + (ys - y) ** 2); x, y = float(xs[j]), float(ys[j])
            el, er = _edges(mask, x, y, nx, ny)
            mg = margin_k * h
            if el is not None and er is not None:
                w = el + er; t = -el + lane * w                   # 以当前点为 0，沿 +n 的目标偏移
                t = float(np.clip(t, -el + mg, er - mg)) if w > 2 * mg else (er - el) / 2
            elif el is not None: t = -el + max(mg, 5 * h * lane * 2) * 1.0; t = min(t, 400)
            elif er is not None: t = er - max(mg, 5 * h * (1 - lane) * 2); t = max(t, -400)
            else: t = 0.0
            pts.append([x + nx * t, y + ny * t])
        pts = np.array(pts)
        k = np.ones(5) / 5; sm = np.stack([np.convolve(np.pad(pts[:, i], 2, mode='edge'), k, 'valid') for i in range(2)], 1)
        sm[0], sm[-1] = pts[0], pts[-1]
        sp['path'] = sm[::3].round(1).tolist() + ([sm[-1].round(1).tolist()] if (len(sm) - 1) % 3 else [])
    return sp

def clearance_report(spec, mask, margin_k=0.3, frames=None):
    """逐帧检查：车身两侧（沿路面法线 ±margin_k×h）是否都在沥青上。返回最差余量和出界帧"""
    tr = Trajectory(spec); bad = []; worst = 1e9
    fr = frames or range(spec['enter'], spec['exit'] + 1)
    for i in fr:
        a = tr.at(i); d = a['dir']; nx, ny = -d[1], d[0]
        el, er = _edges(mask, a['x'], a['y'], nx, ny)
        need = margin_k * a['h']
        for e in (el, er):
            if e is None: continue
            worst = min(worst, e - need)
            if e < need: bad.append((i, round(e - need, 1)))
    return worst, bad

def route_on_track(mask, anchors, k=6.0, d0=40.0, step=4):
    """沿路面走"最远离边线"的路线：代价 = 1 + k·(d0/到边线距离)²，越线代价无穷大。
    anchors: 必经点（起点、弯心方向、终点…），按行驶方向排列。画面边界不算边线（路面延伸到画外）。返回稠密点列。"""
    from scipy import ndimage
    from skimage.graph import route_through_array
    m = mask[::step, ::step]
    pad = np.pad(m, 1, constant_values=True)                       # 画外视为路面延伸
    D = ndimage.distance_transform_edt(pad)[1:-1, 1:-1] * step
    cost = np.where(m, 1 + k * (d0 / np.maximum(D, 1)) ** 2, 1e6)
    pts = []
    for a, b in zip(anchors[:-1], anchors[1:]):
        s = (int(a[1] / step), int(a[0] / step)); e = (int(b[1] / step), int(b[0] / step))
        p, _ = route_through_array(cost, s, e, fully_connected=True, geometric=True)
        seg = [(c * step, r * step) for r, c in p]
        pts += seg if not pts else seg[1:]
    P = np.array(pts, float)
    for _ in range(3):                                             # 平滑锯齿
        P[1:-1] = (P[:-2] + 2 * P[1:-1] + P[2:]) / 4
    return P, D

def track_topology(mask, min_branch=60):
    """检查底图里的路面是不是"一条不分叉的带子"：骨架化后数分叉点和端点。
    合格：端点 2 个（进、出）、无分叉。Y 型/岔路会报出分叉点。"""
    from skimage.morphology import skeletonize
    from scipy import ndimage
    sk = skeletonize(ndimage.binary_opening(mask, iterations=6))
    # 去掉短毛刺
    for _ in range(min_branch):
        nb = ndimage.convolve(sk.astype(int), np.ones((3, 3), int), mode='constant') - sk
        ends = sk & (nb == 1); sk = sk & ~ends
    nb = ndimage.convolve(sk.astype(int), np.ones((3, 3), int), mode='constant') - sk
    junc = np.argwhere(sk & (nb >= 3)); ends = np.argwhere(sk & (nb == 1))
    lab, n = ndimage.label(ndimage.binary_dilation(sk & (nb >= 3), iterations=3))
    return dict(junctions=int(n), junction_pts=[tuple(map(int, p[::-1])) for p in junc[:: max(1, len(junc) // 6 or 1)]][:6], skeleton=sk)

def track_topology2(mask, border=8, spur_len=220):
    """改进版：路面被画框截断处会长出伸向边框的短骨架，这类"边框短刺"不算分叉。
    返回 dict(junctions, ends, skeleton)。合格 = 去掉边框短刺后 junctions == 0。"""
    from skimage.morphology import skeletonize
    from scipy import ndimage
    H, W = mask.shape
    sk = skeletonize(ndimage.binary_opening(mask, iterations=6)).copy()
    K = np.ones((3, 3), int)
    def nbr(s): return ndimage.convolve(s.astype(int), K, mode='constant') - s
    def near_border(y, x): return y < border or x < border or y >= H - border or x >= W - border
    changed = True
    while changed:
        changed = False
        nb = nbr(sk)
        for (y, x) in np.argwhere(sk & (nb == 1)):
            path = [(y, x)]; cy, cx = y, x; prev = None
            while True:
                ns = [(cy + dy, cx + dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if (dy or dx) and 0 <= cy + dy < H and 0 <= cx + dx < W and sk[cy + dy, cx + dx] and (cy + dy, cx + dx) != prev and (cy + dy, cx + dx) not in path[-3:]]
                if len(ns) != 1 or len(path) > spur_len: break
                prev = (cy, cx); cy, cx = ns[0]; path.append((cy, cx))
            hit_junction = len(ns) >= 2
            if hit_junction and len(path) <= spur_len and (near_border(y, x) or len(path) < 25):
                for p in path[:-1]: sk[p] = False
                changed = True
    nb = nbr(sk)
    lab, n = ndimage.label(ndimage.binary_dilation(sk & (nb >= 3), iterations=3))
    ends = [tuple(map(int, p[::-1])) for p in np.argwhere(sk & (nb == 1))]
    return dict(junctions=int(n), ends=ends, skeleton=sk)

def centerline(mask, start_hint, end_hint, border=50, short=120):
    """路面中线：骨架化 → 剪掉伸向画框或很短的毛刺 → 从起点附近的端点沿骨架走到终点附近的端点。
    返回按行驶方向排列的稠密点列（就在路面正中，天然不压线）。"""
    from skimage.morphology import skeletonize
    from skimage.graph import route_through_array
    from scipy import ndimage
    H, W = mask.shape
    sk = skeletonize(ndimage.binary_opening(mask, iterations=6))
    lab, n = ndimage.label(sk, structure=np.ones((3, 3)))
    sizes = ndimage.sum(sk, lab, range(1, n + 1)); sk = lab == (1 + int(np.argmax(sizes)))   # 只要主干
    cost = np.where(sk, 1.0, 1e6)
    def snap(p):
        ys, xs = np.nonzero(sk); j = np.argmin((xs - p[0]) ** 2 + (ys - p[1]) ** 2); return (ys[j], xs[j])
    path, _ = route_through_array(cost, snap(start_hint), snap(end_hint), fully_connected=True, geometric=True)
    P = np.array([(c, r) for r, c in path], float)
    for _ in range(6): P[1:-1] = (P[:-2] + 2 * P[1:-1] + P[2:]) / 4
    return P
