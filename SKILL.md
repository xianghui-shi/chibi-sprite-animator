---
name: "chibi-sprite-animator"
description: "用 AI 生成 8 帧 sprite 表 + 代码换帧合成，做任意画风的 Q 版/动漫小人动画（走路、挥手、指向、说话等），用于口播白板、穿越名画、科幻视频等。"
---

# Chibi Sprite Animator：AI 生帧 + 代码合成的动漫小人

## 核心原则（踩过坑得出的结论）
- **人用 AI 生帧，场景用代码画，代码只负责：换帧、定位、加材质。**
- **禁止**：把写实全身照切成骨骼图层再转关节（肘部像"折断"，已被用户否决）。
- 一个动作 = 一张 4×2 共 8 帧的 sprite 表。动画 = 按时间轮流显示这 8 帧。
- 画风的统一靠 **提示词里的"角色锁定句" + 同一张定稿图做参考**，不靠后期。

## 流程总览
1. **定角色**（一次性）：出 2–3 个画风变体设定图，用户选一个，写成「角色锁定句」。
2. **出 sprite 表**：每个动作一张，用同一个定稿图当参考图 + 锁定句。
3. **切帧**：用下面的 cut.py 抠背景、按格子切、统一身高、记录脚底锚点。
4. **看图验收**：逐张检查脸是否一致、手是否被画出格子、循环是否顺。
5. **合成**：场景层 → 脚底阴影 → 角色帧（按锚点对齐）→ 材质/调色 → 前景遮挡。
6. **渲染 + 抽帧检查**。

## 第 1 步：角色锁定句模板
```
[画风], [头身比: Q版2.5头身], [发型脸型特征], [服装: 颜色+款式+小标], [鞋], [一个最易认的特征, 如脸颊痣/眼镜]
```
已验证例子（日系 Q 版平涂）：2.5 头身、黑短寸、燕麦色 T 恤胸口小红标、深蓝牛仔裤、灰白运动鞋。
选定后把**定稿图 + 锁定句**一起作为后续所有 sprite 的输入。

## 第 2 步：sprite 表提示词模板（ChatGPT / 扣子 / 其他生图均可）
```
[参考图: 定稿角色]
8-frame sprite sheet, 4 columns x 2 rows, equal-size cells, same character in every cell,
action: [动作描述, 逐帧变化],
full body, same scale and same ground line in every cell, nothing crossing cell borders,
flat solid [#00B140 绿幕 | 纯白] background, no shadow on the ground, no text.
[角色锁定句]
```
动作描述写法：把动作拆成 8 个连续姿态（走路：接触→下沉→过渡→抬腿…循环首尾相接）。

常用动作库：walk（8 帧循环，朝右）、wave（挥手）、point（指向右侧）、shrug（摊手）、talk（说话手势）、think（托腮）、surprise（惊讶）、thumbs-up（竖拇指）、idle（站立呼吸）。

### 画风配方（换风格只换这一行，其余不变）
| 风格 | 画风描述词 | 背景建议 |
|---|---|---|
| 日系 Q 版平涂 | chibi anime, flat colors, clean thin outline | 绿幕 |
| 白板马克笔 | whiteboard marker line art, black outline, no hatching, no shading, flat oatmeal shirt | 纯白（不抠，multiply 贴入） |
| 8-bit 像素 | 16-bit pixel art character, limited palette, crisp pixels, no anti-aliasing | 绿幕 |
| 赛博霓虹 | cyberpunk anime chibi, neon rim light in magenta/cyan, dark outfit | **勿用绿幕**（霓虹边会染绿）→ 用纯黑或洋红幕，或关闭轮廓光后再用绿幕 |
| 浮世绘 | ukiyo-e woodblock print figure, bold ink outline, flat washes, paper texture | 纯白或绿幕 |
| 水彩/印象派 | soft watercolor chibi, visible paper grain | 纯白，合成时用 multiply |
| 黏土/3D | clay stop-motion figure, soft lighting | 绿幕 |
| 美漫/厚涂 | thick-paint comic figure, heavy ink lines | 绿幕 |

要点：**同一场景里的小人画风可以和背景不同**（如写实小人走进梵高星夜），穿越多幅画时每个世界重新出一张 walk 表即可；也可以保持小人画风不变、只让场景变。

## 第 3 步：切帧脚本（cut.py，通用版）
```python
import numpy as np, json, os, sys
from PIL import Image
from scipy import ndimage
# 用法: python cut.py 输入目录 输出目录 [green|white]
SRC, OUT = sys.argv[1], sys.argv[2]; MODE = sys.argv[3] if len(sys.argv) > 3 else 'green'
SHEETS = {  # 动作名: 文件名 —— 按实际改
  'walk': 'walk.png', 'wave': 'wave.png', 'point': 'point.png', 'shrug': 'shrug.png', 'talk': 'talk.png'}
TARGET = 480          # 站立身高（存储像素）
COLS, ROWS = 4, 2
def key(a):
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    if MODE == 'green':     # 去绿幕 + 去溢色
        spill = g - np.maximum(r, b); al = 1 - np.clip((spill - 28) / 60, 0, 1)
        g2 = np.where(spill > 0, np.minimum(g, np.maximum(r, b) + 0.2 * np.clip(spill, 0, 30)), g)
        return np.dstack([r, g2, b, al * 255])
    # white: 白底线稿只裁不抠；亮度越高越透明，合成时再配 multiply
    lum = (r + g + b) / 3; al = 1 - np.clip((lum - 235) / 20, 0, 1)
    return np.dstack([r, g, b, al * 255])
meta = {}
for name, f in SHEETS.items():
    im = np.asarray(Image.open(os.path.join(SRC, f)).convert('RGB')).astype(np.float32)
    H, W = im.shape[:2]; cw, ch = W / COLS, H / ROWS
    full = key(im); m = full[..., 3] > 128; cells = []
    for k in range(COLS * ROWS):
        cx, cy = k % COLS, k // COLS
        X0, Y0, X1, Y1 = int(cx*cw), int(cy*ch), int((cx+1)*cw), int((cy+1)*ch)
        ex, ey = int(cw * 0.3), int(ch * 0.08)          # 外扩边距，容纳出格的手/脚
        x0, y0, x1, y1 = max(0, X0-ex), max(0, Y0-ey), min(W, X1+ex), min(H, Y1+ey)
        sub = m[y0:y1, x0:x1]; lab, n = ndimage.label(sub)
        core = np.zeros_like(sub); core[Y0-y0:Y1-y0, X0-x0:X1-x0] = True
        inc = ndimage.sum(core, lab, range(1, n+1)); main = int(np.argmax(inc)) + 1
        keep = lab == main
        for L in range(1, n+1):                          # 连通块过滤：丢掉邻格串进来的部分
            if L == main: continue
            ys, xs = np.where(lab == L)
            if core[int(ys.mean()), int(xs.mean())] and len(ys) > 30: keep |= lab == L
        keep = ndimage.binary_dilation(keep, iterations=2)
        rgba = full[y0:y1, x0:x1].copy(); rgba[..., 3] *= keep
        ys, xs = np.where(rgba[..., 3] > 40)
        cells.append((rgba, (xs.min(), ys.min(), xs.max()+1, ys.max()+1)))
    ref = float(np.median([bb[3]-bb[1] for _, bb in cells])); s = TARGET / ref   # 统一站立身高
    os.makedirs(f'{OUT}/{name}', exist_ok=True); fm = []
    for k, (rgba, (a, b_, c, d)) in enumerate(cells):
        crop = rgba[b_:d, a:c].clip(0, 255).astype(np.uint8)
        al = crop[..., 3] > 100; rows = np.where(al.any(1))[0]; foot = rows.max()
        band = al[max(0, foot-int(0.06*ref)):foot+1]; fx = np.where(band.any(0))[0]
        ax = (fx.min() + fx.max()) / 2                    # 脚底中心 x
        img = Image.fromarray(crop, 'RGBA')
        img = img.resize((max(1, round(img.width*s)), max(1, round(img.height*s))), Image.LANCZOS)
        img.save(f'{OUT}/{name}/{k}.png')
        fm.append({'w': img.width, 'h': img.height, 'ax': round(ax*s, 1), 'ay': round((foot+1)*s, 1)})
    meta[name] = {'frames': fm, 'ref_h': TARGET}
json.dump(meta, open(f'{OUT}/meta.json', 'w'), indent=1)
```
依赖：numpy、Pillow、scipy。输出：`帧库/<动作>/0-7.png` + `meta.json`（每帧脚底锚点 ax/ay、统一身高 ref_h）。

## 第 4 步：验收清单（必做，逐张看图）
- 脸、发型、服装颜色是否与定稿一致（不一致的整张弃用，重出，不要硬用）。
- 手/脚是否画出格子被切掉（例：挥手第 0 帧手出格 → 只循环用 1–7 帧）。
- 走路表首尾能否接成循环；脚是否踩在同一地平线。
- 同一动作多张候选时，选与定稿最像的，不选"动作更好看但脸不像"的。

## 第 5 步：合成规则
- 位置：`x0 = 角色x - frame.ax * s`，`y0 = 地面y - frame.ay * s`，`s = DISP / ref_h`（DISP=屏幕显示高度，1080p 下约 290）。脚底对齐 ay，所以换帧不会跳。
- 脚底阴影：地面处画一个半透明扁椭圆（约 28% 透明、宽 ≈ 0.18×DISP）。
- 走路速度要和步频匹配，防滑步：已验证 V=220 px/s 配 9 帧/秒（8 帧循环）。
- 帧率：走路 ≈9 帧/秒；挥手 ≈10；说话 ≈6；一次性动作（指向/摊手）按 `min(7, floor(t/帧时长))` 播完停在末帧。
- 材质融合（让小人属于画面）：
  - 彩色背景：在角色层上用 `source-atop` 叠一层淡笔触 / 纸纹（透明度≈0.2），脸部区域排除；左暖右冷的淡渐变模拟光源。
  - 白板线稿：不抠图，用 `multiply` 贴到白底上。
  - 前景遮挡（栏杆、草、柱子）最后画，压在腿前，才有"站在景里"的感觉。
- 动作顺序写成数组 `ACTS = [[开始, 结束, 动作名, 取帧函数], ...]`，口播场景用配音 timeline.json 的句子起止秒对齐动作。

### 口播白板的动作对应（参考）
开场 → wave → 站立讲解；列点 → 竖食指 / 指向右侧；思考 → 托腮；转折 → 惊讶；结尾 → 竖大拇指。角色放画面一侧，不挡白板文字。

## 渲染环境（花叔 huashu-art-motion 引擎）
- 技能 huashu-art-motion 的 `scripts/engine/` 复制到工作目录；帧库放引擎根目录 `frames/`；场景文件放 `scenes/`；`meta.json` 通过同步 XHR 读入并把所有帧加入 `EXTRA_ASSETS` 预加载。
- 静帧快速试渲：`python3 render.py --film <名> --solo <场景> --stills 2,7.5 --out 试渲`
- 整片：`python3 render.py --film <名> --fps 30 --out 成片.mp4`（16 秒约 5 分钟）。
- 口播白板用 `render.py --spec clip.json`（y3_whiteboard 语法）。
- 写回用户电脑单文件上限 30MB，成片压缩 crf 20。
- 验收：抽帧看动作与口型/字幕同步，qa.py 检查，交付前独立审片。

## 常见问题
- 小人在画面里"飘"：锚点用了图片底边而不是脚底 → 用 meta 的 ay。
- 帧间忽大忽小：没统一身高 → 用 cut.py 的 ref 中位数缩放。
- 边缘绿边：绿幕溢色 → cut.py 去溢色已处理；仍有则提高 spill 阈值或换纯白底。
- 隔壁格的手串进来：加大外扩边距的同时保留连通块过滤。
- 多个画风风格不统一：把定稿图作为每次生图的参考图，并复用同一句锁定句。

## 进阶 A：一次性动作的"关键帧溶解 + 表情帧"（转身、亮相、特写）
适用于**不是循环**的动作。已在「Jon 舞台转身」上验证。
- **不要在定格姿态上用 2–3 帧循环**：会一直晃，脸一抖就有恐怖谷感。一个固定表情停 1–2 秒也会显得假。
- 做法：每个姿态 1 张高质量静帧（背面 → 回头 → 侧身 → 四分之三 → 正面 → 特写），按时间轴溶解 0.1–0.2s，镜头同步推近。
- **表情靠多张同构图的表情帧排节奏**：暖笑 → 眨眼（只闪 0.06–0.12s）→ 开怀笑（约 0.9s）→ 收成浅笑。每个表情 0.8–1.2s。
- **表情之间用光流变形（morph），不要淡入淡出**：淡入淡出会让嘴形、眼睛叠影，显得假。做法：`cv2.DISOpticalFlow` 算 A→B、B→A 光流，输出 = `(1-a)·warp(A, a·flow_BA) + a·warp(B, (1-a)·flow_AB)`，a 用 ease。过渡 0.16–0.3s（嘴张得大的过渡取长一些），每个表情只停 0.04–0.8s，节奏要紧，别每个都停 1 秒。
- 表情帧用生图工具的"编辑图片"出，提示词写 `Keep EVERYTHING identical ... Only change: <表情>`，保证构图不变。
- **对齐**：用 SIFT 只在头发/耳朵/外套区域匹配（避开嘴和眼），RANSAC 估计相似变换（`cv2.estimateAffinePartial2D`）。偏移 <1px 就能无缝溶解。
- 特写与全身正面也用同样方法估计缩放（实测 ≈0.367），推镜时脸不会跳位。
- 横向拖影（±12px 多层叠加）**只加在转身的身体帧**，不要加到脸部表情溶解上（会整张脸发糊）。
- 视频模型的首尾帧转身视频可抠绿取帧做**原型**，但脸会偏年轻、道具颜色会漂，成片用 AI 静帧。
- 呼吸感：整体以脚底为中心做 ±0.35% 缩放，周期约 3 秒即可。

## 进阶 A2：特写拉远回广角（和前后镜头衔接）
- 新镜头结束处不要硬切：多渲 ~24 帧（0.8s）的"拉远"，吃掉后一镜头开头的帧，与后一镜头（用原片逐帧）溶解，总帧数不变。
- 拉远时**追踪焦点（脸）**：`z` 按指数缩小，焦点的屏幕位置先留在中央、再用 `p^1.6` 滑向目标位置（别让 cx/cy 线性插值，脸会斜着飞出画面）。终点的 z 和位置对齐后一镜头里该角色的大小/位置（实测：广角里角色约 215px 高@720p）。
- 角色图层：特写半身 → 在拉远刚开始的 0.17s 后用 0.09s 溶成全身图（快速径向模糊盖住）；溶解前先把脸 morph 成全身图上的同一表情（如再笑一次），避免两张脸叠影。
- 溶解中点加一点泛光（≈16% 白），遮住前后两张背景的交叠；前一镜头角色和后一镜头角色在同位置同大小时，溶解读起来像"同一个人站在那里"。
- 后一镜头里如果角色是静态"纸片人"，衔接只能缓解，想彻底解决要把它也换成新角色并做细微动作。

## 进阶 B：把新镜头换进已有成片（不动音频）
1. 用 `ffmpeg -vf "select='gt(scene,0.1)',showinfo"` 找旧镜头精确起止帧（注意要 `-v info`）。
2. 新镜头帧数 = 旧镜头槽位帧数（按小节：2 小节 ≈ 3.9s @123BPM，30fps 即 116 帧）。
3. 拼接：`trim=end_frame=A` + 新镜头 + `trim=start_frame=B` → `concat`，`-map 0:a -c:a copy` 保持音画同步。
4. 画质不要刻意压：用 `-crf 15`（不设 maxrate），在用户电脑上的 shell 里直接合成，就不受 30MB 写回限制；检查总帧数与原片一致。注意 device shell 的后台进程会在调用结束时被杀，要在单次调用（≤180s）内跑完，用 `-preset fast`。
5. 换完抽帧看接缝（前后各 0.2s）。

## 额度/模型建议
切帧、出片等机械步骤用 Sonnet 即可；看图判断、设计新场景/新画风再用 Opus。生图本身消耗 ChatGPT/扣子额度，一次一个动作，先出 walk 验证风格再批量出其他动作。