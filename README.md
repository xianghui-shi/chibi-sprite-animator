# chibi-sprite-animator

用 AI 生成 8 帧 sprite 表 + 代码换帧合成，做**任意画风**的 Q 版 / 动漫小人动画（走路、挥手、指向、说话、摊手……）。
适用于口播白板、穿越名画、科幻视频等。免费开源（MIT）。

核心思路：**人物用 AI 生帧，场景用代码画，代码只负责换帧、定位、加材质。**
（不要把写实照片切成骨骼图层做关节动画——弯肘会像"胳膊折断"。）

## 内容
- 角色锁定句 + sprite 表提示词模板
- 8 种画风配方（日系 Q 版、白板线稿、像素、赛博霓虹、浮世绘、水彩、黏土、美漫）
- 通用切帧脚本 `cut.py`（绿幕 / 白底，输出脚底锚点 meta.json）
- 合成规则、验收清单、常见问题
- **白板手绘分支**（`whiteboard-handdraw/`）：口播/SRT 字幕 → 一笔笔画出场景的手绘白板视频。含转写、逐句区域标注、渲染、合并脚本和无字画画手素材，附示例

## 安装
把本仓库整个文件夹（含 `SKILL.md` 和 `whiteboard-handdraw/`）放到 `~/.claude/skills/chibi-sprite-animator/`，
或在 claude.ai 的 Skills 里上传本文件夹。

## 许可
MIT。`whiteboard-handdraw/` 中的渲染代码改编自 [geeklee/srt-whiteboard-animation](https://github.com/geeklee/srt-whiteboard-animation)（MIT），许可文本见 `whiteboard-handdraw/UPSTREAM-LICENSE`。
