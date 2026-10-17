#!/usr/bin/env python3
"""按"一句字幕一个区域"生成 annotation.json（让画面逐句对上口播）。

用法: python make_annotation.py 线稿.png 字幕.srt 区域.json 输出.annotation.json [--lead 100] [--breath 200]

区域.json 是列表，每项对应一个绘制区域，按绘制顺序排列：
  {"cue": 1 或 [1,2],  // 对应的字幕序号（可合并多句）
   "label": "森林", "role": "场景铺垫", "type": "structure|character",
   "x": 0, "y": 260, "w": 580, "h": 681}      // 原图整数像素坐标
时间: 区域 startMs = 所含首句开始 + lead；durationMs = 所含句子总跨度 - lead - breath（至少 800）。
规则: 一支笔串行作画；后面区域的矩形会从前面区域里"挖掉"，所以相邻区域的边界要落在空白处。
"""
import argparse, json, re
from PIL import Image

def parse_srt(path):
    txt = open(path, encoding="utf-8").read().replace("\r\n", "\n")
    cues = {}
    for blk in re.split(r"\n\s*\n", txt.strip()):
        ln = blk.strip().split("\n")
        if len(ln) < 3: continue
        m = re.match(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)", ln[1])
        g = list(map(int, m.groups()))
        st = ((g[0]*60+g[1])*60+g[2])*1000+g[3]; en = ((g[4]*60+g[5])*60+g[6])*1000+g[7]
        cues[int(ln[0])] = (st, en, " ".join(ln[2:]).strip())
    return cues

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image"); ap.add_argument("srt"); ap.add_argument("regions"); ap.add_argument("out")
    ap.add_argument("--lead", type=int, default=100); ap.add_argument("--breath", type=int, default=200)
    a = ap.parse_args()
    W, H = Image.open(a.image).size
    cues = parse_srt(a.srt); regions = json.load(open(a.regions, encoding="utf-8"))
    els = []
    for i, r in enumerate(regions, 1):
        ids = r["cue"] if isinstance(r["cue"], list) else [r["cue"]]
        st = min(cues[c][0] for c in ids); en = max(cues[c][1] for c in ids)
        sub = "".join(cues[c][2] for c in ids)
        x, y, w, h = r["x"], r["y"], r["w"], r["h"]
        assert 0 <= x and 0 <= y and x + w <= W and y + h <= H, f"区域{i}超出画布 {W}x{H}"
        els.append({"id": r.get("id", f"r{i}"), "label": r["label"], "sequence": i,
            "narrativeRole": r.get("role", ""), "subtitle": sub, "type": r.get("type", "structure"),
            "region": {"x": x, "y": y, "width": w, "height": h},
            "reveal": {"direction": "top_to_bottom", "startMs": st + a.lead,
                       "durationMs": max(800, en - st - a.lead - a.breath), "maskPaddingPx": 22, "protectedRegions": []},
            "handPath": {"start": [x + w // 2, y + 10], "end": [x + w // 2, y + h - 10], "easing": "easeInOut"}})
    total = max(c[1] for c in cues.values())
    data = {"sceneId": "scene-01", "canvas": {"width": W, "height": H}, "storyBasis": "", "sceneDurationMs": total, "elements": els}
    json.dump(data, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"已写入 {a.out}：{len(els)} 个区域，总时长 {total} ms")

if __name__ == "__main__":
    main()
