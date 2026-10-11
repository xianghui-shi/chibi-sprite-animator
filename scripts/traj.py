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
        ds = np.hypot(np.diff(X), np.diff(Z)); S = np.r_[0, np.cumsum(ds)]
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

    def at(self, i):
        """第 i 帧：返回 dict(x, y, h, yaw, lean, dir, visible)；dir 是画面上的行进方向单位矢量"""
        e, x_ = self.spec['enter'], self.spec['exit']
        p = (i - e) / max(1e-6, x_ - e)
        vis = 0 <= p <= 1
        p = min(1.0, max(0.0, p))
        s = p * self.length_m                                             # 按真实距离匀速
        u = float(np.interp(s, self.S, self.u))
        x, y, h = float(self.sx(u)), float(self.sy(u)), float(np.exp(self.sh(u)))
        dX, dZ = float(np.interp(s, self.S, self.dX)), float(np.interp(s, self.S, self.dZ))
        yaw = math.degrees(math.atan2(dX, -dZ))                           # 0 朝镜头来，+90 向右横穿，±180 远离
        k = float(np.interp(s, self.S, self.kappa))
        lean = math.degrees(math.atan(self.v ** 2 * abs(k) / 9.81))       # 压弯角（只取大小）
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
